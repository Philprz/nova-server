# core/rate_limit.py - Rate limiting pour endpoints MFA (in-memory + Redis)

import time
from typing import Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from functools import wraps
import os

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class InMemoryRateLimiter:
    """
    Rate limiter simple en mémoire (adapté pour dev/petit trafic).
    Format: {key: [(timestamp, count), ...]}
    """

    def __init__(self):
        self._store: Dict[str, list] = defaultdict(list)

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Vérifie si la clé dépasse le rate limit.

        Args:
            key: Identifiant unique (ex: "mfa_verify:user_42:192.168.1.1")
            max_requests: Nombre max de requêtes autorisées
            window_seconds: Fenêtre de temps en secondes

        Returns:
            (is_limited, remaining_requests)
        """
        now = time.time()
        cutoff = now - window_seconds

        # Nettoyer les anciennes entrées
        self._store[key] = [ts for ts in self._store[key] if ts > cutoff]

        current_count = len(self._store[key])

        if current_count >= max_requests:
            return True, 0

        # Enregistrer la nouvelle requête
        self._store[key].append(now)
        remaining = max_requests - (current_count + 1)
        return False, remaining

    def reset(self, key: str) -> None:
        """Réinitialise le compteur pour une clé."""
        if key in self._store:
            del self._store[key]


class RedisRateLimiter:
    """
    Rate limiter basé sur Redis (production-ready, distribué).
    Utilise Redis INCR + EXPIRE pour gérer les compteurs.
    """

    def __init__(self, redis_url: Optional[str] = None):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package required for RedisRateLimiter")

        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/1")
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Vérifie le rate limit avec Redis.

        Args:
            key: Clé Redis (ex: "mfa:verify:user_42:192.168.1.1")
            max_requests: Nombre max de requêtes
            window_seconds: Fenêtre en secondes

        Returns:
            (is_limited, remaining_requests)
        """
        redis_key = f"rate_limit:{key}"

        try:
            # Utiliser pipeline pour atomicité
            pipe = self.client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            results = pipe.execute()

            current_count = results[0]

            if current_count > max_requests:
                remaining = 0
                return True, remaining

            remaining = max_requests - current_count
            return False, remaining

        except redis.RedisError as e:
            # Fallback: si Redis indisponible, laisser passer (fail open)
            print(f"Redis error in rate limiter: {e}")
            return False, max_requests

    def reset(self, key: str) -> None:
        """Supprime le compteur Redis."""
        redis_key = f"rate_limit:{key}"
        self.client.delete(redis_key)


# Instance globale (auto-détection Redis)
def get_rate_limiter():
    """
    Factory pour obtenir le rate limiter approprié.
    Utilise Redis si disponible et configuré, sinon in-memory.
    """
    redis_url = os.getenv("REDIS_URL")

    if REDIS_AVAILABLE and redis_url:
        try:
            return RedisRateLimiter(redis_url)
        except Exception as e:
            print(f"Failed to initialize Redis rate limiter: {e}, falling back to in-memory")
            return InMemoryRateLimiter()
    else:
        return InMemoryRateLimiter()


_rate_limiter = get_rate_limiter()


def check_rate_limit(
    key: str,
    max_requests: int = 10,
    window_seconds: int = 60,
    error_message: str = "Too many requests, please try again later"
) -> None:
    """
    Fonction helper pour vérifier le rate limit et raise HTTPException si dépassé.

    Args:
        key: Clé unique pour identifier la limite
        max_requests: Nombre max de requêtes
        window_seconds: Fenêtre de temps
        error_message: Message d'erreur personnalisé

    Raises:
        HTTPException 429 si limite dépassée

    Usage:
        check_rate_limit(f"mfa_verify:user_{user_id}:{client_ip}", max_requests=5, window_seconds=60)
    """
    is_limited, remaining = _rate_limiter.is_rate_limited(key, max_requests, window_seconds)

    if is_limited:
        from core.logging import log_mfa_event
        log_mfa_event("rate_limit_exceeded", result="rate_limited", extra_data={"key": key})

        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": error_message,
                "retry_after": window_seconds,
            },
            headers={"Retry-After": str(window_seconds)}
        )


def reset_rate_limit(key: str) -> None:
    """Réinitialise le rate limit pour une clé (ex: après succès MFA)."""
    _rate_limiter.reset(key)


def rate_limit_dependency(
    max_requests: int = 10,
    window_seconds: int = 60,
    key_prefix: str = "api"
):
    """
    Dépendance FastAPI pour rate limiting sur une route.

    Usage:
        @router.post("/mfa/verify/totp")
        async def verify_totp(
            request: Request,
            rate_limit: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=60, key_prefix="mfa_totp"))
        ):
            ...
    """
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{client_ip}"

        check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
            error_message=f"Too many requests. Max {max_requests} per {window_seconds}s."
        )

    return dependency
