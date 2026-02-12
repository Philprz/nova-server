"""Test extraction descriptions"""
import re

text = """
SHEPPEE CODE: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
SHEPPEE CODE: TRI-037 - LIFT ROLLER STUD - 2 Adet
SHEPPEE CODE: C315-6305RS - BALL BEARING - 2 Adet
"""

# Pattern utilisé dans email_matcher.py
pattern1 = re.findall(
    r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]{3,})\s*[-–]\s*([^-\n]+?)(?:\s*[-–]|\n|SHEPPEE|DRAWING)',
    text,
    re.IGNORECASE
)

print("Descriptions extraites:")
for code, desc in pattern1:
    print(f"  {code.strip()}: {desc.strip()}")

if not pattern1:
    print("  AUCUNE DESCRIPTION EXTRAITE!")
