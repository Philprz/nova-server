"""
Catalogue de prix LLM (input/output) en USD par MILLION de tokens.

Source officielle :
  - Anthropic  : https://www.anthropic.com/pricing
  - OpenAI     : https://openai.com/api/pricing/
  - Mistral AI : https://mistral.ai/products/la-plateforme#pricing

Donnees indicatives — verifier les prix officiels avant tout calcul critique.
Verifie le 2026-05-28. A maintenir manuellement quand un provider modifie sa grille.

Pour un modele inconnu : get_pricing() renvoie None. Cela permet aux modeles
custom ou nouveaux d'apparaitre sans prix dans l'UI, sans casser le rendu.

Strategie de matching :
  1. Match exact sur le nom du modele
  2. Match exact sur l'alias "latest" (ex: claude-sonnet-latest -> claude-sonnet-4-6)
  3. Match sur la famille via PRICING_FAMILY (prefixe), pour les snapshots dates
     (ex: mistral-large-2411 -> famille "mistral-large")
"""

from typing import Dict, Optional, Any

CURRENCY = "USD"
UNIT = "per_million_tokens"
LAST_UPDATED = "2026-05-28"


# Prix exacts par modele : {input, output} en $/M tokens
PRICING: Dict[str, Dict[str, float]] = {
    # ── Anthropic Claude ───────────────────────────────────────────────────
    "claude-opus-4-7":          {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":        {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":         {"input":  1.00, "output":  5.00},
    "claude-haiku-4-5-20251001": {"input":  1.00, "output":  5.00},
    "claude-opus-4-5":          {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5":        {"input":  3.00, "output": 15.00},
    "claude-haiku-4-0":         {"input":  0.80, "output":  4.00},
    "claude-3-5-sonnet-latest": {"input":  3.00, "output": 15.00},
    "claude-3-5-haiku-latest":  {"input":  0.80, "output":  4.00},
    "claude-3-opus-latest":     {"input": 15.00, "output": 75.00},

    # ── OpenAI ─────────────────────────────────────────────────────────────
    "gpt-4.1":                  {"input":  2.00, "output":  8.00},
    "gpt-4.1-mini":             {"input":  0.40, "output":  1.60},
    "gpt-4.1-nano":             {"input":  0.10, "output":  0.40},
    "gpt-4o":                   {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":              {"input":  0.15, "output":  0.60},
    "gpt-4o-2024-08-06":        {"input":  2.50, "output": 10.00},
    "gpt-4-turbo":              {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo":            {"input":  0.50, "output":  1.50},
    "o1":                       {"input": 15.00, "output": 60.00},
    "o1-mini":                  {"input":  3.00, "output": 12.00},
    "o3":                       {"input": 10.00, "output": 40.00},
    "o3-mini":                  {"input":  1.10, "output":  4.40},
    "o4-mini":                  {"input":  1.10, "output":  4.40},

    # ── Mistral ────────────────────────────────────────────────────────────
    "mistral-large-2411":       {"input":  2.00, "output":  6.00},
    "mistral-large-2512":       {"input":  2.00, "output":  6.00},
    "mistral-medium-2505":      {"input":  0.40, "output":  2.00},
    "mistral-medium-2508":      {"input":  0.40, "output":  2.00},
    "mistral-medium-2604":      {"input":  0.40, "output":  2.00},
    "mistral-medium-3":         {"input":  0.40, "output":  2.00},
    "mistral-medium-3.5":       {"input":  0.40, "output":  2.00},
    "mistral-medium-3-5":       {"input":  0.40, "output":  2.00},
    "mistral-small-2506":       {"input":  0.20, "output":  0.60},
    "mistral-small-2603":       {"input":  0.20, "output":  0.60},
    "mistral-tiny-2407":        {"input":  0.25, "output":  0.25},
    "ministral-3b-2512":        {"input":  0.04, "output":  0.04},
    "ministral-8b-2512":        {"input":  0.10, "output":  0.10},
    "ministral-14b-2512":       {"input":  0.20, "output":  0.20},
    "codestral-2508":           {"input":  0.20, "output":  0.60},
    "codestral-latest":         {"input":  0.20, "output":  0.60},
    "magistral-medium-2509":    {"input":  2.00, "output":  5.00},
    "magistral-small-2509":     {"input":  0.50, "output":  1.50},
    "pixtral-large-2411":       {"input":  2.00, "output":  6.00},
    "open-mistral-nemo":        {"input":  0.15, "output":  0.15},
    "open-mistral-nemo-2407":   {"input":  0.15, "output":  0.15},
}


# Alias "latest" → modele actuel (les providers renvoient deux fois la meme entree
# dans /v1/models, l'une datee et l'autre "latest", on les rattache au meme prix)
ALIASES: Dict[str, str] = {
    "claude-sonnet-latest":    "claude-sonnet-4-6",
    "claude-opus-latest":      "claude-opus-4-7",
    "claude-haiku-latest":     "claude-haiku-4-5",

    "mistral-large-latest":    "mistral-large-2512",
    "mistral-medium-latest":   "mistral-medium-2604",
    "mistral-small-latest":    "mistral-small-2603",
    "mistral-tiny-latest":     "mistral-tiny-2407",
    "ministral-3b-latest":     "ministral-3b-2512",
    "ministral-8b-latest":     "ministral-8b-2512",
    "ministral-14b-latest":    "ministral-14b-2512",
    "magistral-medium-latest": "magistral-medium-2509",
    "magistral-small-latest":  "magistral-small-2509",
    "pixtral-large-latest":    "pixtral-large-2411",
    "devstral-latest":         "codestral-latest",  # approximatif
    "devstral-medium-latest":  "codestral-latest",
    "devstral-small-latest":   "codestral-latest",
}


# Familles : prefixe -> prix approximatif (fallback pour snapshots inconnus)
# Itere dans l'ordre, premier match prefixe gagne. Ordre = du plus specifique
# au plus generique.
PRICING_FAMILY = [
    ("claude-opus",          {"input": 15.00, "output": 75.00}),
    ("claude-sonnet",        {"input":  3.00, "output": 15.00}),
    ("claude-haiku",         {"input":  1.00, "output":  5.00}),
    ("gpt-4o-mini",          {"input":  0.15, "output":  0.60}),
    ("gpt-4.1-mini",         {"input":  0.40, "output":  1.60}),
    ("gpt-4.1-nano",         {"input":  0.10, "output":  0.40}),
    ("gpt-4o",               {"input":  2.50, "output": 10.00}),
    ("gpt-4.1",              {"input":  2.00, "output":  8.00}),
    ("gpt-4",                {"input": 10.00, "output": 30.00}),
    ("o1-mini",              {"input":  3.00, "output": 12.00}),
    ("o3-mini",              {"input":  1.10, "output":  4.40}),
    ("o4-mini",              {"input":  1.10, "output":  4.40}),
    ("mistral-large",        {"input":  2.00, "output":  6.00}),
    ("mistral-medium",       {"input":  0.40, "output":  2.00}),
    ("mistral-small",        {"input":  0.20, "output":  0.60}),
    ("ministral-3b",         {"input":  0.04, "output":  0.04}),
    ("ministral-8b",         {"input":  0.10, "output":  0.10}),
    ("ministral-14b",        {"input":  0.20, "output":  0.20}),
    ("magistral-medium",     {"input":  2.00, "output":  5.00}),
    ("magistral-small",      {"input":  0.50, "output":  1.50}),
    ("codestral",            {"input":  0.20, "output":  0.60}),
    ("pixtral-large",        {"input":  2.00, "output":  6.00}),
]


def get_pricing(model_name: str) -> Optional[Dict[str, float]]:
    """
    Retourne {"input": float, "output": float} en $/M tokens, ou None si inconnu.
    """
    if not model_name:
        return None
    name = model_name.strip()

    # 1. Match exact
    if name in PRICING:
        return PRICING[name]

    # 2. Alias "latest"
    aliased = ALIASES.get(name)
    if aliased and aliased in PRICING:
        return PRICING[aliased]

    # 3. Famille par prefixe
    name_lower = name.lower()
    for prefix, price in PRICING_FAMILY:
        if name_lower.startswith(prefix.lower()):
            return price

    return None


def get_all_pricing() -> Dict[str, Any]:
    """Retourne le catalogue complet (utilise par l'endpoint admin)."""
    return {
        "currency": CURRENCY,
        "unit": UNIT,
        "last_updated": LAST_UPDATED,
        "models": dict(PRICING),
        "aliases": dict(ALIASES),
    }
