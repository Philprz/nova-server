"""Test de la nouvelle fonction _clean_html qui préserve les emails"""
from services.email_analyzer import get_email_analyzer

# Email HTML typique de Microsoft Graph avec email dans le corps
html_test = """
<html>
<head>
<style type="text/css">
.font-family: Arial, sans-serif;
.text-align: left;
</style>
</head>
<body>
<div style="font-size: 12pt; font-family: Calibri, sans-serif;">
<p>De : Quesnel, Christophe &lt;chq@saverglass.com&gt;</p>
<p>Objet : demande de prix</p>
<p>Bonjour Manu</p>
<p>Pourrais-tu me faire un devis pour l'article suivant</p>
<p>2323060165 qté : 1</p>
<p>Merci</p>
<div data-bit="1234" class="signature">
Christophe QUESNEL<br/>
MAGASINIER I.S.<br/>
Atelier I.S. Mécaniciens SGL<br/>
+33344464269
</div>
</div>
</body>
</html>
"""

print("="*60)
print("TEST NOUVELLE FONCTION _clean_html()")
print("="*60)

analyzer = get_email_analyzer()
clean_text = analyzer._clean_html(html_test)

print("\nRésultat nettoyé:")
print("-"*60)
print(clean_text)
print("-"*60)

# Vérifications
checks = {
    "Email préservé (chq@saverglass.com)": "chq@saverglass.com" in clean_text,
    "Balises HTML supprimées (<div>, <p>)": "<div" not in clean_text and "<p>" not in clean_text,
    "Attributs CSS supprimés (font-family)": "font-family" not in clean_text,
    "Attributs data supprimés (data-bit)": "data-bit" not in clean_text,
    "Produit préservé (2323060165)": "2323060165" in clean_text,
    "Style blocks supprimés": "<style" not in clean_text and "text-align" not in clean_text,
}

print("\nVerifications:")
print("-"*60)
for check_name, result in checks.items():
    status = "[OK]" if result else "[ECHEC]"
    print(f"{status} - {check_name}")

# Resume
all_ok = all(checks.values())
print("-"*60)
if all_ok:
    print("[OK] TOUS LES TESTS PASSENT - La fonction fonctionne correctement !")
else:
    print("[ECHEC] CERTAINS TESTS ECHOUENT - Correction necessaire")
    failed = [name for name, result in checks.items() if not result]
    print(f"Echecs: {', '.join(failed)}")
