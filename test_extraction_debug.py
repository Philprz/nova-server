"""Debug de l'extraction des codes produits"""
import re

text = """
SHEPPEE CODE: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
SHEPPEE CODE: TRI-037 - LIFT ROLLER STUD - 2 Adet
SHEPPEE CODE: C315-6305RS - BALL BEARING - 2 Adet
"""

print("=== TEST EXTRACTION CODES ===\n")
print(f"Texte:\n{text}\n")

# Pattern 1: Codes numériques longs
p1 = set(re.findall(r'\b(\d{6,})\b', text))
print(f"Pattern 1 (numériques 6+): {p1}")

# Pattern 2: Codes avec tirets
p2 = set(re.findall(r'\b([A-Z]{1,4}-[A-Z0-9-]+)\b', text, re.IGNORECASE))
print(f"Pattern 2 (alphanumériques avec tirets): {p2}")

# Pattern 3: Codes sans tirets
p3 = set(re.findall(r'\b([A-Z]{1,4}\d{3,}[A-Z0-9]*)\b', text, re.IGNORECASE))
print(f"Pattern 3 (alphanumériques sans tirets): {p3}")

# Pattern 4: SHEPPEE CODE: XXX
p4 = set(re.findall(r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]+)', text, re.IGNORECASE))
print(f"Pattern 4 (CODE: XXX): {p4}")

# Union
all_codes = p1 | p2 | p3 | p4
print(f"\nTOUS CODES EXTRAITS: {all_codes}")

print("\n=== TEST EXTRACTION DESCRIPTIONS ===\n")

# Pattern descriptions
desc_pattern = re.findall(
    r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]{3,})\s*[-–]\s*([^-\n]+?)(?:\s*[-–]|\n|SHEPPEE|DRAWING)',
    text,
    re.IGNORECASE
)

print(f"Descriptions extraites:")
for code, desc in desc_pattern:
    print(f"  {code.strip()}: {desc.strip()}")
