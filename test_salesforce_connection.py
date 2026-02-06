import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("DIAGNOSTIC DE CONNEXION SALESFORCE")
print("=" * 60)

print("\n1. Verification des variables d'environnement:")
print("-" * 60)

sf_username = os.getenv("SALESFORCE_USERNAME")
sf_password = os.getenv("SALESFORCE_PASSWORD")
sf_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
sf_domain = os.getenv("SALESFORCE_DOMAIN", "login")
sf_url = os.getenv("SALESFORCE_URL")

print(f"SALESFORCE_USERNAME: {'OK' if sf_username else 'MANQUANT'}")
if sf_username:
    print(f"  Valeur: {sf_username}")

print(f"SALESFORCE_PASSWORD: {'OK' if sf_password else 'MANQUANT'}")
if sf_password:
    print(f"  Longueur: {len(sf_password)} caracteres")

print(f"SALESFORCE_SECURITY_TOKEN: {'OK' if sf_token else 'MANQUANT'}")
if sf_token:
    print(f"  Longueur: {len(sf_token)} caracteres")

print(f"SALESFORCE_DOMAIN: {sf_domain}")
print(f"SALESFORCE_URL: {sf_url}")

print("\n2. Verification du module simple_salesforce:")
print("-" * 60)

try:
    from simple_salesforce import Salesforce
    print("OK - Module simple_salesforce importe avec succes")
except ImportError as e:
    print(f"ERREUR: Module simple_salesforce non trouve")
    print(f"  Details: {e}")
    print("\n  Solution: Installez le module avec:")
    print("  pip install simple-salesforce")
    sys.exit(1)

print("\n3. Test de connexion Salesforce:")
print("-" * 60)

if not all([sf_username, sf_password, sf_token]):
    print("ERREUR: Configuration incomplete")
    missing = []
    if not sf_username:
        missing.append("SALESFORCE_USERNAME")
    if not sf_password:
        missing.append("SALESFORCE_PASSWORD")
    if not sf_token:
        missing.append("SALESFORCE_SECURITY_TOKEN")
    print(f"  Variables manquantes: {', '.join(missing)}")
    sys.exit(1)

try:
    print(f"Tentative de connexion avec:")
    print(f"  - Username: {sf_username}")
    print(f"  - Domain: {sf_domain}")
    print(f"  - API Version: 55.0")
    print()
    
    sf = Salesforce(
        username=sf_username,
        password=sf_password,
        security_token=sf_token,
        domain=sf_domain,
        version="55.0"
    )
    
    print("OK - Connexion Salesforce reussie!")
    print(f"  Instance URL: {sf.sf_instance}")
    print(f"  Session ID: {sf.session_id[:20]}...")
    
    print("\n4. Test de requete simple:")
    print("-" * 60)
    
    result = sf.query("SELECT Id, Name FROM Account LIMIT 1")
    print(f"OK - Requete executee avec succes")
    print(f"  Nombre de resultats: {result['totalSize']}")
    
    if result['totalSize'] > 0:
        account = result['records'][0]
        print(f"  Premier compte: {account['Name']} (ID: {account['Id']})")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC TERMINE: CONNEXION OK")
    print("=" * 60)
    
except Exception as e:
    print(f"ERREUR DE CONNEXION")
    print(f"  Type d'erreur: {type(e).__name__}")
    print(f"  Message: {str(e)}")
    
    error_msg = str(e).lower()
    
    print("\n5. Analyse de l'erreur:")
    print("-" * 60)
    
    if "invalid_login" in error_msg or "invalid login" in error_msg:
        print("ERREUR D'AUTHENTIFICATION")
        print("\nCauses possibles:")
        print("  1. Nom d'utilisateur ou mot de passe incorrect")
        print("  2. Security Token invalide ou expire")
        print("  3. Compte Salesforce verrouille ou desactive")
        print("  4. IP non autorisee (verifier les restrictions IP)")
        print("\nSolutions:")
        print("  1. Verifiez vos identifiants dans Salesforce")
        print("  2. Reinitialisez votre Security Token:")
        print("     - Allez dans Setup > My Personal Information > Reset Security Token")
        print("  3. Verifiez que votre compte n'est pas verrouille")
        print("  4. Ajoutez votre IP aux plages autorisees dans Salesforce")
        
    elif "unauthorized" in error_msg:
        print("ACCES NON AUTORISE")
        print("\nCauses possibles:")
        print("  1. Permissions insuffisantes")
        print("  2. Profil utilisateur restreint")
        print("\nSolutions:")
        print("  1. Verifiez les permissions de votre profil utilisateur")
        print("  2. Contactez votre administrateur Salesforce")
        
    elif "timeout" in error_msg or "timed out" in error_msg:
        print("TIMEOUT DE CONNEXION")
        print("\nCauses possibles:")
        print("  1. Probleme de reseau")
        print("  2. Firewall bloquant la connexion")
        print("\nSolutions:")
        print("  1. Verifiez votre connexion internet")
        print("  2. Verifiez les parametres du firewall")
        
    elif "domain" in error_msg:
        print("PROBLEME DE DOMAINE")
        print(f"\nDomaine actuel: {sf_domain}")
        print("\nSolutions:")
        print("  1. Pour un environnement sandbox, utilisez: SALESFORCE_DOMAIN=test")
        print("  2. Pour la production, utilisez: SALESFORCE_DOMAIN=login")
        print("  3. Pour un domaine personnalise, utilisez votre domaine My Domain")
        
    else:
        print("ERREUR INCONNUE")
        print("\nVeuillez verifier:")
        print("  1. Tous les identifiants sont corrects")
        print("  2. Le compte Salesforce est actif")
        print("  3. L'acces API est active")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC TERMINE: CONNEXION ECHOUEE")
    print("=" * 60)
    
    sys.exit(1)
