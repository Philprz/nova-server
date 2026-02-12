"""Debug extraction dans match_email"""
import asyncio
from services.email_matcher import get_email_matcher
import re

async def test():
    email_text = """
SHEPPEE CODE: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
SHEPPEE CODE: TRI-037 - LIFT ROLLER STUD - 2 Adet
SHEPPEE CODE: C315-6305RS - BALL BEARING - 2 Adet
"""

    # Test extraction manuelle (comme dans email_matcher.py)
    print("=== EXTRACTION MANUELLE ===\n")

    # Pattern 1
    p1 = set(re.findall(r'\b(\d{6,})\b', email_text))
    print(f"Pattern 1 (numeriques 6+): {p1}")

    # Pattern 2
    p2 = set(re.findall(r'\b([A-Z]{1,4}-[A-Z0-9-]+)\b', email_text, re.IGNORECASE))
    print(f"Pattern 2 (avec tirets): {p2}")

    # Pattern 3
    p3 = set(re.findall(r'\b([A-Z]{1,4}\d{3,}[A-Z0-9]*)\b', email_text, re.IGNORECASE))
    print(f"Pattern 3 (sans tirets): {p3}")

    # Pattern 4
    p4 = set(re.findall(r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]+)', email_text, re.IGNORECASE))
    print(f"Pattern 4 (CODE: XXX): {p4}")

    all_codes = p1 | p2 | p3 | p4
    print(f"\nTOUS: {all_codes}")

    # Filtrage
    excluded = {'SHEPPEE', 'CODE', 'DRAWING', 'PUSHER', 'BEARING', 'ROLLER', 'CARBON', 'BLADE'}
    filtered = {code for code in all_codes if code.upper() not in excluded}
    print(f"Apres filtrage mots exclus: {filtered}")

    # Filtrage doublons
    final = set()
    for code in sorted(filtered, key=len, reverse=True):
        if not any(code in longer and code != longer for longer in final):
            final.add(code)
    print(f"Apres filtrage doublons: {final}")

    # Test avec le matcher
    print("\n=== TEST MATCHER ===\n")
    matcher = get_email_matcher()
    await matcher.ensure_cache()

    result = await matcher.match_email(
        body=email_text,
        sender_email="test@example.com",
        subject=""
    )

    print(f"Produits trouves: {len(result.products)}")
    for p in result.products:
        print(f"  - {p.item_code}: score={p.score}, raison={p.match_reason}")

if __name__ == "__main__":
    asyncio.run(test())
