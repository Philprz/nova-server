"""
LLMRouter : routeur dynamique pour les appels LLM.

Lit la configuration active (provider principal + chaine fallback) depuis
PostgreSQL, et bascule automatiquement sur les fallbacks en cas d'echec
du provider courant.

Compatibilite descendante : si aucune configuration en base, retombe sur
ANTHROPIC_API_KEY / OPENAI_API_KEY du .env pour ne pas casser l'existant.
"""

import os
import re
import json
import time
import asyncio
import logging
from typing import List, Dict, Optional, Tuple, Any

import httpx
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models.database_models import SessionLocal, LLMProvider, LLMConfiguration
from services.encryption_service import decrypt

load_dotenv()
logger = logging.getLogger(__name__)


# Cache TTL : la config est rechargee toutes les CACHE_TTL secondes,
# ou immediatement via reload() apres une modification admin.
CACHE_TTL_SECONDS = 60

# Timeouts par defaut (peuvent etre depasses si gros prompts)
HTTP_TIMEOUT_SECONDS = 30.0


class _Entry:
    """Une entree resolue de la chaine fallback (provider + modele decrypted)."""

    def __init__(self, name: str, base_url: str, api_format: str,
                 api_key: str, model: str, priority: int):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_format = api_format  # "anthropic" | "openai"
        self.api_key = api_key
        self.model = model
        self.priority = priority

    def __repr__(self) -> str:
        return f"<{self.name}:{self.model} prio={self.priority}>"


class LLMRouter:
    """
    Singleton. Charge la chaine principal->fallback depuis la base, la cache,
    et expose call() qui essaie chaque entree dans l'ordre.
    """

    def __init__(self):
        self._chain: List[_Entry] = []
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    # -----------------------------------------------------------------------
    # Chargement de la chaine
    # -----------------------------------------------------------------------

    def _load_chain_from_db(self) -> List[_Entry]:
        """Lit llm_configuration + llm_providers et reconstitue la chaine ordonnee."""
        chain: List[_Entry] = []
        db: Session = SessionLocal()
        try:
            rows = (
                db.query(LLMConfiguration, LLMProvider)
                .join(LLMProvider, LLMConfiguration.provider_id == LLMProvider.id)
                .filter(LLMConfiguration.is_enabled.is_(True))
                .filter(LLMProvider.is_active.is_(True))
                .order_by(LLMConfiguration.priority.asc())
                .all()
            )
            for cfg, prov in rows:
                try:
                    api_key = decrypt(prov.api_key_encrypted)
                except ValueError as exc:
                    logger.error("LLMRouter: provider %s cle indechiffrable, ignore : %s",
                                 prov.name, exc)
                    continue
                chain.append(_Entry(
                    name=prov.name,
                    base_url=prov.base_url,
                    api_format=prov.api_format,
                    api_key=api_key,
                    model=cfg.model_name,
                    priority=cfg.priority,
                ))
        finally:
            db.close()
        return chain

    def _load_chain_from_env(self) -> List[_Entry]:
        """Fallback si la base est vide : reproduit l'ancien comportement (Claude > GPT)."""
        chain: List[_Entry] = []
        anth_key = os.getenv("ANTHROPIC_API_KEY")
        anth_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        if anth_key:
            chain.append(_Entry(
                name="Anthropic (env)",
                base_url="https://api.anthropic.com",
                api_format="anthropic",
                api_key=anth_key,
                model=anth_model,
                priority=0,
            ))
        oai_key = os.getenv("OPENAI_API_KEY")
        oai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        if oai_key:
            chain.append(_Entry(
                name="OpenAI (env)",
                base_url="https://api.openai.com",
                api_format="openai",
                api_key=oai_key,
                model=oai_model,
                priority=1,
            ))
        return chain

    async def _ensure_loaded(self) -> List[_Entry]:
        now = time.monotonic()
        if self._chain and (now - self._loaded_at) < CACHE_TTL_SECONDS:
            return self._chain

        async with self._lock:
            # Double-check apres acquisition du lock
            now = time.monotonic()
            if self._chain and (now - self._loaded_at) < CACHE_TTL_SECONDS:
                return self._chain

            chain = await asyncio.to_thread(self._load_chain_from_db)
            if not chain:
                logger.info("LLMRouter: configuration DB vide, fallback sur .env")
                chain = self._load_chain_from_env()
            if not chain:
                logger.error("LLMRouter: aucune source de cle LLM (ni DB ni .env)")
            self._chain = chain
            self._loaded_at = time.monotonic()
            logger.info("LLMRouter: chaine chargee : %s", chain)
            return self._chain

    def reload(self) -> None:
        """Force le rechargement au prochain appel (a appeler apres modif admin)."""
        self._chain = []
        self._loaded_at = 0.0

    # -----------------------------------------------------------------------
    # Appels HTTP par format
    # -----------------------------------------------------------------------

    @staticmethod
    async def _call_anthropic(entry: _Entry, system_prompt: str, user_message: str,
                              max_tokens: int, temperature: float) -> str:
        url = f"{entry.base_url}/v1/messages"
        headers = {
            "x-api-key": entry.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": entry.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_message}],
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""

    @staticmethod
    async def _call_openai_compat(entry: _Entry, system_prompt: str, user_message: str,
                                  max_tokens: int, temperature: float) -> str:
        url = f"{entry.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {entry.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        payload = {
            "model": entry.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "") or ""
        return ""

    async def _call_entry(self, entry: _Entry, system_prompt: str, user_message: str,
                          max_tokens: int, temperature: float) -> str:
        if entry.api_format == "anthropic":
            return await self._call_anthropic(entry, system_prompt, user_message,
                                              max_tokens, temperature)
        if entry.api_format == "openai":
            return await self._call_openai_compat(entry, system_prompt, user_message,
                                                  max_tokens, temperature)
        raise ValueError(f"Format API inconnu pour {entry.name}: {entry.api_format}")

    # -----------------------------------------------------------------------
    # Normalisation reponse LLM
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_response(raw: str, provider_name: str = "?") -> str:
        """
        Nettoie la reponse brute d'un LLM pour en extraire un JSON valide.
        Applique systematiquement avant tout retour de la methode call().
        """
        text = raw.strip()

        # Etape 1 : supprimer les balises Markdown ```json ... ``` ou ``` ... ```
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        # Etape 2 : tenter json.loads direct
        try:
            json.loads(text)
            return text
        except (json.JSONDecodeError, ValueError):
            pass

        # Etape 3 : extraire le premier objet JSON {...}
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                pass

        # Etape 4 : extraire le premier tableau JSON [...]
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                pass

        # Etape 5 : aucun JSON recuperable — retourner le texte brut
        logger.debug(
            "LLMRouter._normalize_response : JSON non extrait pour fournisseur %s — "
            "reponse brute retournee telle quelle (longueur : %d chars)",
            provider_name, len(raw)
        )
        return text

    # -----------------------------------------------------------------------
    # API publique
    # -----------------------------------------------------------------------

    async def call(self, system_prompt: str, user_message: str,
                   max_tokens: int = 1024, temperature: float = 0.0) -> str:
        """
        Appelle le LLM principal puis chaque fallback en cas d'echec.
        Leve la derniere exception rencontree si toute la chaine echoue.
        """
        chain = await self._ensure_loaded()
        if not chain:
            raise RuntimeError(
                "LLMRouter: aucune configuration LLM disponible "
                "(verifier admin LLM ou ANTHROPIC_API_KEY/OPENAI_API_KEY dans .env)"
            )

        last_exc: Optional[BaseException] = None
        for idx, entry in enumerate(chain):
            role = "primary" if idx == 0 else f"fallback#{idx}"
            try:
                logger.info("LLMRouter: tentative %s -> %s", role, entry)
                raw_response = await self._call_entry(entry, system_prompt, user_message,
                                                      max_tokens, temperature)
                if idx > 0:
                    logger.warning("LLMRouter: succes via %s apres %d echec(s)",
                                   entry, idx)
                return self._normalize_response(raw_response, provider_name=entry.name)
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else "?"
                logger.warning("LLMRouter: %s %s a echoue (HTTP %s), bascule fallback",
                               role, entry.name, status_code)
                last_exc = exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                logger.warning("LLMRouter: %s %s a echoue (%s: %s), bascule fallback",
                               role, entry.name, type(exc).__name__, exc)
                last_exc = exc
            except Exception as exc:
                logger.warning("LLMRouter: %s %s erreur inattendue (%s: %s), bascule fallback",
                               role, entry.name, type(exc).__name__, exc)
                last_exc = exc

        assert last_exc is not None
        logger.error("LLMRouter: toute la chaine a echoue (%d providers tentes)", len(chain))
        raise last_exc

    async def test_chain(self) -> List[Dict[str, Any]]:
        """
        Teste chaque entree de la chaine active independamment et retourne
        un rapport ordonne. Utilise pour l'endpoint admin /test-chain.

        Chaque entree est testee avec son modele specifique configure (pas le
        modele par defaut du provider), pour valider exactement ce qui sera
        utilise en production.
        """
        chain = await self._ensure_loaded()
        if not chain:
            return []

        report: List[Dict[str, Any]] = []
        for entry in chain:
            t0 = time.monotonic()
            ok = False
            message = ""
            try:
                text = await self._call_entry(
                    entry,
                    system_prompt="You are a test bot. Reply with the single word OK.",
                    user_message="ping",
                    max_tokens=8,
                    temperature=0.0,
                )
                ok = True
                message = (text or "").strip()[:80] or "(reponse vide)"
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else "?"
                body_excerpt = (exc.response.text[:200] if exc.response is not None else "")
                message = f"HTTP {status_code}: {body_excerpt}"
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                message = f"{type(exc).__name__}: {exc}"
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            report.append({
                "priority": entry.priority,
                "role": "primary" if entry.priority == 0 else f"fallback-{entry.priority}",
                "provider_name": entry.name,
                "model_name": entry.model,
                "api_format": entry.api_format,
                "ok": ok,
                "latency_ms": elapsed_ms,
                "message": message,
            })

        return report

    async def test_entry(self, provider_id: int,
                         model_name: str) -> Tuple[bool, str, int]:
        """
        Teste le couple exact (provider, modele) — utilise pour un bouton de
        test par entree de chaine, indifferemment de l'etat de la chaine active.
        Retourne (ok, message, latency_ms).
        """
        db: Session = SessionLocal()
        try:
            prov = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
            if not prov:
                return False, f"Provider id={provider_id} introuvable", 0
            try:
                api_key = decrypt(prov.api_key_encrypted)
            except ValueError as exc:
                return False, f"Cle indechiffrable : {exc}", 0
            if model_name not in (prov.available_models or []):
                return (False,
                        f"Modele '{model_name}' non declare pour {prov.name}",
                        0)
            entry = _Entry(
                name=prov.name, base_url=prov.base_url, api_format=prov.api_format,
                api_key=api_key, model=model_name, priority=0,
            )
        finally:
            db.close()

        t0 = time.monotonic()
        try:
            text = await self._call_entry(
                entry,
                system_prompt="You are a test bot. Reply with the single word OK.",
                user_message="ping",
                max_tokens=8,
                temperature=0.0,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return True, (text or "").strip()[:80] or "(reponse vide)", elapsed_ms
        except httpx.HTTPStatusError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            sc = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:200] if exc.response is not None else ""
            return False, f"HTTP {sc}: {body}", elapsed_ms
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return False, f"{type(exc).__name__}: {exc}", elapsed_ms

    async def call_for_benchmark(
        self,
        provider_id: int,
        model_name: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict:
        """
        Appelle un LLM précis (provider_id + model_name) pour un benchmark.
        Retourne un dict avec : raw_response, latency_ms, error (None si succès).
        N'utilise pas la chaîne fallback — appel direct et isolé.
        """
        db: Session = SessionLocal()
        try:
            prov = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
            if not prov:
                return {
                    "raw_response": None,
                    "latency_ms": 0,
                    "error": f"Provider id={provider_id} introuvable",
                }
            try:
                api_key = decrypt(prov.api_key_encrypted)
            except ValueError as exc:
                return {
                    "raw_response": None,
                    "latency_ms": 0,
                    "error": f"Cle indechiffrable : {exc}",
                }
            entry = _Entry(
                name=prov.name,
                base_url=prov.base_url,
                api_format=prov.api_format,
                api_key=api_key,
                model=model_name,
                priority=0,
            )
        finally:
            db.close()

        t0 = time.monotonic()
        try:
            raw = await self._call_entry(
                entry, system_prompt, user_message, max_tokens, temperature
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            normalized = self._normalize_response(raw, provider_name=prov.name)
            return {"raw_response": normalized, "latency_ms": elapsed_ms, "error": None}
        except httpx.HTTPStatusError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            sc = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:300] if exc.response is not None else ""
            return {"raw_response": None, "latency_ms": elapsed_ms,
                    "error": f"HTTP {sc}: {body}"}
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return {"raw_response": None, "latency_ms": elapsed_ms,
                    "error": f"{type(exc).__name__}: {exc}"}

    async def test_provider(self, provider_id: int) -> Tuple[bool, str]:
        """
        Test minimal d'un provider precis (utilise par l'endpoint admin).
        Retourne (ok, message).
        """
        db: Session = SessionLocal()
        try:
            prov = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
            if not prov:
                return False, f"Provider id={provider_id} introuvable"
            try:
                api_key = decrypt(prov.api_key_encrypted)
            except ValueError as exc:
                return False, f"Cle indechiffrable : {exc}"
            models = prov.available_models or []
            if not models:
                return False, "Aucun modele configure pour ce provider"
            entry = _Entry(
                name=prov.name, base_url=prov.base_url, api_format=prov.api_format,
                api_key=api_key, model=models[0], priority=0,
            )
        finally:
            db.close()

        try:
            text = await self._call_entry(
                entry,
                system_prompt="You are a test bot. Reply with the single word OK.",
                user_message="ping",
                max_tokens=8,
                temperature=0.0,
            )
            return True, f"OK ({entry.model}) -> {text[:50]!r}"
        except httpx.HTTPStatusError as exc:
            return False, f"HTTP {exc.response.status_code} : {exc.response.text[:200]}"
        except Exception as exc:
            return False, f"{type(exc).__name__} : {exc}"


# Singleton
_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
        logger.info("LLMRouter singleton cree")
    return _router
