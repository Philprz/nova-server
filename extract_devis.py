"""Extraction texte du devis PDF"""
import fitz
import sys

pdf_path = r"C:\Users\PPZ\NOVA-SERVER\Devis-RONDOT SAS-IT SPIRIT-D-2025-635.pdf"

try:
    doc = fitz.open(pdf_path)
    full_text = []

    for page_num, page in enumerate(doc[:20], 1):
        text = page.get_text()
        full_text.append(f"\n{'='*60}\nPAGE {page_num}\n{'='*60}\n")
        full_text.append(text)

    # Écrire dans un fichier texte
    output_path = r"C:\Users\PPZ\NOVA-SERVER\devis_extracted.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(''.join(full_text))

    print(f"OK - Texte extrait dans: {output_path}")
    print(f"Pages traitees: {len(doc[:20])}")

except Exception as e:
    print(f"ERREUR: {e}")
    sys.exit(1)
