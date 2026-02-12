"""
Test avec le PDF réel de Marmara Cam (28 produits)
"""
import asyncio
from services.email_matcher import get_email_matcher

async def test_marmara_pdf():
    matcher = get_email_matcher()
    await matcher.ensure_cache()

    # Contenu extrait du PDF Marmara Cam
    pdf_content = """
OFFER REQUEST FORM
Marmara Cam Sanayi ve Tic. A.Ş.
Sheppee International Ltd
Email: msezen@marmaracam.com.tr
Date : 1.07.2025
Form No : 26576

Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
Row 2: C233-50AT10-1940G3 - D5 SHEPPEE STAKER timing belt - 2 Adet
Row 3: C281-RV80 - Z-AXIS GEAR UNIT - 1 Adet
Row 4: C362-M035-SF - FLANGED BEARING UNIT - 2 Adet
Row 5: TRI-037 - LIFT ROLLER STUD - 2 Adet
Row 6: TRI-038 - LIFT ROLLER ECCENTRIC - 2 Adet
Row 7: TRI-066 - SUPPORT BLOCK - 2 Adet
Row 8: TRI-067 - LIFT ROLLER SPACER - 2 Adet
Row 9: TRI-075 - PIVOT PIN - 2 Adet
Row 10: P-0301L-SLT - VERTICAL CLAMP CARRIER LH - 1 Adet
Row 11: P-0301R-SLT - VERTICAL CLAMP CARRIER RH - 1 Adet
Row 12: C356-NUTD25 - CAM FOLLOWER - 2 Adet
Row 13: TRI-051 - GEAR UNIT CYCLO GEARBOX - 2 Adet
Row 14: C421-MET-020 - M20 NUT - 2 Adet
Row 15: C431M-020 - M20 PLAIN WASHER - 2 Adet
Row 16: TRI-011 - BEARING RETAINER - 1 Adet
Row 17: TRI-014 - BELT CLAMP BOTTOM - 1 Adet
Row 18: TRI-015 - BELT CLAMP UPPER - 1 Adet
Row 19: TRI-016 - BELT CLAMP COUPLING - 1 Adet
Row 20: TRI-018 - DRIVE SCREW - 1 Adet
Row 21: C315-6305RS - BALL BEARING - 2 Adet
Row 22: TRI-009 - DRIVE PULLEY 40T - 1 Adet
Row 23: TRI-010 - IDLE PULLEY 40T - 1 Adet
Row 24: C391-14-LM - LM GUIDE RAIL 1160 LG - 2 Adet
Row 25: C391-15-LM - LM RAIL 1480 LG - 2 Adet
Row 26: C361-NP25-MS44 - BEARING PILLOW BLOCK - 2 Adet
Row 27: TRI-036 - LIFT CAM - 2 Adet
Row 28: MRS-0005 - Z-AXIS DRIVE SHAFT - 1 Adet
"""

    print("="*70)
    print("TEST PDF MARMARA CAM - 28 PRODUITS")
    print("="*70)

    result = await matcher.match_email(
        body=pdf_content,
        sender_email="msezen@marmaracam.com.tr",
        subject="Offer Request Form No 26576"
    )

    # CLIENT
    print("\n[CLIENT]")
    if result.best_client:
        print(f"  Matche: {result.best_client.card_name} ({result.best_client.card_code})")
        print(f"  Score: {result.best_client.score}")
        print(f"  Raison: {result.best_client.match_reason}")
    else:
        print("  PAS DE MATCH")

    # PRODUITS
    print(f"\n[PRODUITS] {len(result.products)} produit(s) trouve(s) dans SAP")
    if result.products:
        for p in result.products[:10]:  # Afficher les 10 premiers
            status = "NON TROUVE SAP" if p.not_found_in_sap else "TROUVE SAP"
            print(f"  - {p.item_code}: {p.item_name} (qte: {p.quantity}) [{status}]")
        if len(result.products) > 10:
            print(f"  ... et {len(result.products) - 10} autres produits")

    # Statistiques
    found_count = sum(1 for p in result.products if not p.not_found_in_sap)
    not_found_count = sum(1 for p in result.products if p.not_found_in_sap)

    print(f"\n[STATISTIQUES]")
    print(f"  Total produits extraits du PDF: 28 attendus")
    print(f"  Produits matches dans SAP: {found_count}")
    print(f"  Produits NON trouves dans SAP: {not_found_count}")

    # Liste des codes non trouvés
    if not_found_count > 0:
        print(f"\n[CODES NON TROUVES DANS SAP]")
        not_found_codes = [p.item_code for p in result.products if p.not_found_in_sap]
        for code in not_found_codes[:15]:
            print(f"  - {code}")

if __name__ == "__main__":
    asyncio.run(test_marmara_pdf())
