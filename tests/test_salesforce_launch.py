# test_salesforce_launch.py
import os
import sys
import json
from dotenv import load_dotenv

# Configurer la sortie pour capturer tous les messages
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

print("=== TEST DE DÉMARRAGE SALESFORCE MCP ===")
print(f"Working directory: {os.getcwd()}")
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Environnement
print("\n=== VARIABLES D'ENVIRONNEMENT ===")
load_dotenv('.env')
required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN", "SALESFORCE_DOMAIN"]
for var in required_vars:
    value = os.getenv(var)
    masked_value = value[:3] + "****" if value else None
    print(f"{var}: {'OK' if value else 'MANQUANT'} - {masked_value}")

# Imports MCP
print("\n=== TEST IMPORTS MCP ===")
try:
    from mcp.server.fastmcp import FastMCP
    print("✅ Import FastMCP réussi")
except Exception as e:
    print(f"❌ Erreur FastMCP: {str(e)}")

# Import Salesforce
print("\n=== TEST IMPORT SALESFORCE ===")
try:
    from simple_salesforce import Salesforce
    print("✅ Import Salesforce réussi")
except Exception as e:
    print(f"❌ Erreur Salesforce: {str(e)}")

# Test connexion Salesforce
print("\n=== TEST CONNEXION SALESFORCE ===")
try:
    username = os.getenv("SALESFORCE_USERNAME")
    password = os.getenv("SALESFORCE_PASSWORD")
    security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
    domain = os.getenv("SALESFORCE_DOMAIN", "login")
    
    if all([username, password, security_token]):
        print(f"Tentative de connexion avec {username} sur {domain}...")
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        result = sf.query("SELECT Id FROM Account LIMIT 1")
        print(f"✅ Connexion Salesforce réussie - {result.get('totalSize')} résultats")
    else:
        print("❌ Informations de connexion Salesforce incomplètes")
except Exception as e:
    print(f"❌ Erreur connexion Salesforce: {str(e)}")

print("\n=== TEST TERMINÉ ===")