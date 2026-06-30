#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/generate_vault_key_module.py — Lot 2 / etape 2b : EMBARQUEMENT de la
cle maitre du coffre dans un module dedie, destine a etre compile en .pyd.

Role : lire la cle maitre Fernet depuis une source securisee fournie AU BUILD
(option --key-file <chemin> ou variable d'environnement NOVA_VAULT_KEY ; JAMAIS
commitee), puis generer le module `_vault_key.py` ou la cle n'apparait PLUS en
clair : elle est SPLITTEE en segments, chacun masque par XOR contre (un masque
aleatoire) XOR (un flux derive d'une graine). Une fonction `get_key()`
reconstruit la cle a l'execution.

GARANTIE : aucune occurrence du base64 complet de la cle dans le fichier genere
(verifiee avant ecriture). Le module `_vault_key.py` est GITIGNORE : il n'est
JAMAIS commite ni livre en source. Seul `_vault_key.pyd` (compile par la chaine
build_cython_full) est embarque dans la livraison.

Schema d'obfuscation (par octet i) :
    stocke_xored[i] = cle[i] XOR masque[i] XOR flux[i]
    flux[i]         = (SEED * (offset_global(i) + 1) + 131) & 0xFF
La reconstruction necessite SIMULTANEMENT les segments xored, les masques et le
flux derive de SEED : aucun des tableaux stockes ne revele la cle a lui seul.

LIMITE ASSUMEE : un module compile reste reversible par desassemblage. C'est une
mesure de DISSUASION contre une extraction triviale (strings/grep), PAS un
coffre inviolable. Cf. docs/COFFRE_CONFIG.md.

Usage (au build de livraison, cle reelle JAMAIS commitee) :
    # via fichier (le fichier ne doit pas etre commite) :
    .venv\\Scripts\\python.exe scripts\\generate_vault_key_module.py --key-file C:\\secure\\rondot.key
    # ou via l'environnement :
    set NOVA_VAULT_KEY=<cle-base64>
    .venv\\Scripts\\python.exe scripts\\generate_vault_key_module.py

Le module est ecrit a la racine du repo sous _vault_key.py (option --out pour
changer). En DEV, on genere une cle JETABLE pour valider le mecanisme.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_vault_key.py"
_ENV_VAR = "NOVA_VAULT_KEY"

# Taille des segments dans lesquels la cle est decoupee (lisibilite/scattering).
_SEG_LEN = 7


def _read_key(key_file: "str | None") -> bytes:
    """Lit la cle maitre depuis --key-file en priorite, sinon NOVA_VAULT_KEY.

    Retourne la cle en bytes ASCII. Erreur claire si aucune source disponible
    ou si la cle est vide.
    """
    if key_file:
        path = Path(key_file)
        if not path.is_file():
            raise SystemExit(f"ERREUR : --key-file introuvable : {key_file}")
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            raise SystemExit(f"ERREUR : --key-file vide : {key_file}")
        return raw.encode("ascii")

    env = os.getenv(_ENV_VAR)
    if env and env.strip():
        return env.strip().encode("ascii")

    raise SystemExit(
        "ERREUR : aucune cle maitre fournie.\n"
        f"  Indiquer --key-file <chemin> (non commite), ou exposer {_ENV_VAR} "
        "dans l'environnement.\n"
        "  En DEV, generer une cle jetable :\n"
        "    .venv\\Scripts\\python.exe scripts\\provision_secrets.py --genkey"
    )


def _stream_byte(seed: int, global_index: int) -> int:
    """Flux pseudo-aleatoire deterministe, derive de la graine et de la position."""
    return (seed * (global_index + 1) + 131) & 0xFF


def _build_segments(key: bytes, seed: int) -> "list[tuple[list[int], list[int]]]":
    """Decoupe la cle et produit la liste [(segment_xored, segment_masque), ...]."""
    masks = os.urandom(len(key))
    segments: "list[tuple[list[int], list[int]]]" = []
    for start in range(0, len(key), _SEG_LEN):
        seg_xored: "list[int]" = []
        seg_mask: "list[int]" = []
        for j in range(start, min(start + _SEG_LEN, len(key))):
            stream = _stream_byte(seed, j)
            seg_xored.append(key[j] ^ masks[j] ^ stream)
            seg_mask.append(masks[j])
        segments.append((seg_xored, seg_mask))
    return segments


def _render_module(seed: int, segments) -> str:
    """Genere le texte source de _vault_key.py (cle reconstruite par get_key())."""
    seg_lines = []
    for seg_xored, seg_mask in segments:
        seg_lines.append(f"    ({seg_xored!r}, {seg_mask!r}),")
    seg_block = "\n".join(seg_lines)
    return f'''\
# -*- coding: utf-8 -*-
"""
_vault_key.py — module GENERE par scripts/generate_vault_key_module.py (Lot 2/2b).

NE PAS COMMITTER. NE PAS LIVRER EN SOURCE.
Ce fichier est GITIGNORE ; seule sa version compilee `_vault_key.pyd` est
embarquee dans la livraison. La cle maitre du coffre n'apparait JAMAIS en clair
ici : elle est decoupee en segments masques (XOR masque aleatoire XOR flux
derive d'une graine) et reconstruite a l'execution par get_key().

Reversible par desassemblage : DISSUASION contre une extraction triviale, PAS
une protection inviolable. Cf. docs/COFFRE_CONFIG.md.
"""

# Graine du flux pseudo-aleatoire (cf. generateur). Combinee aux masques et aux
# segments xored : aucun de ces tableaux ne revele la cle a lui seul.
_SEED = {seed}

# Liste de (segment_xored, segment_masque). Reconstruction : voir get_key().
_SEGMENTS = [
{seg_block}
]


def _stream_byte(global_index):
    return (_SEED * (global_index + 1) + 131) & 0xFF


def get_key():
    """Reconstruit la cle maitre Fernet (bytes ASCII) a l'execution."""
    out = bytearray()
    pos = 0
    for seg_xored, seg_mask in _SEGMENTS:
        for k in range(len(seg_xored)):
            out.append(seg_xored[k] ^ seg_mask[k] ^ _stream_byte(pos))
            pos += 1
    return bytes(out)
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_vault_key_module",
        description="Genere _vault_key.py (cle maitre embarquee, obfusquee).",
    )
    parser.add_argument(
        "--key-file",
        metavar="CHEMIN",
        help="Fichier contenant la cle maitre base64 (non commite). "
             f"A defaut : variable d'environnement {_ENV_VAR}.",
    )
    parser.add_argument(
        "--out",
        metavar="CHEMIN",
        default=str(DEFAULT_OUT),
        help=f"Chemin du module a ecrire (defaut: {DEFAULT_OUT}).",
    )
    args = parser.parse_args(argv)

    key = _read_key(args.key_file)

    # Graine aleatoire 16 bits, propre a cette generation (l'obfuscation n'est
    # donc pas statique d'un build a l'autre).
    seed = int.from_bytes(os.urandom(2), "big") or 0x5BD1
    segments = _build_segments(key, seed)
    module_src = _render_module(seed, segments)

    # GARDE-FOU : le base64 complet de la cle ne doit JAMAIS apparaitre dans la
    # source generee (ni en ASCII, ni en repr). Echec dur sinon.
    key_str = key.decode("ascii")
    if key_str in module_src or repr(key_str) in module_src or repr(key) in module_src:
        raise SystemExit(
            "ERREUR FATALE : la cle en clair apparait dans le module genere. "
            "Generation avortee (aucun fichier ecrit)."
        )

    # Verification fonctionnelle AVANT ecriture : la reconstruction redonne la cle.
    ns: dict = {}
    exec(compile(module_src, "<_vault_key>", "exec"), ns)  # noqa: S102 - controle interne
    if ns["get_key"]() != key:
        raise SystemExit(
            "ERREUR FATALE : la reconstruction get_key() ne redonne pas la cle. "
            "Generation avortee (aucun fichier ecrit)."
        )

    out_path = Path(args.out)
    out_path.write_text(module_src, encoding="utf-8")

    print(f"Module embarque genere : {out_path}")
    print(f"Longueur cle : {len(key)} octets | segments : {len(segments)} | seed : {seed}")
    print("Base64 de la cle ABSENT du fichier (verifie) ; get_key() reconstruit OK.")
    print("RAPPEL : _vault_key.py est gitignore. Le compiler en .pyd ; ne JAMAIS "
          "le committer ni le livrer en source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
