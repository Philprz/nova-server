"""Constantes de configuration pour les sessions SAP B1 (port BILLING/apps/api/src/config.ts)."""

from __future__ import annotations

import os

COOKIE_NAME = os.getenv("PA_COOKIE_NAME", "pa_session")

# Timeouts NOVA — indépendants du SessionTimeout SAP. Si le B1SESSION expire
# côté SAP avant l'idle NOVA, l'helper d'appel renverra 401 et la session sera
# purgée proactivement.
IDLE_TIMEOUT_MINUTES = max(5, int(os.getenv("SESSION_IDLE_MINUTES", "30")))
ABSOLUTE_TIMEOUT_MINUTES = max(
    IDLE_TIMEOUT_MINUTES,
    int(os.getenv("SESSION_ABSOLUTE_MINUTES", str(8 * 60))),
)

# Cookie sécurisé en production (HTTPS). Aligné sur la convention NOVA_MODE
# déjà utilisée par routes_auth.py.
SECURE_COOKIES = os.getenv("NOVA_MODE", "development").lower() == "production"
