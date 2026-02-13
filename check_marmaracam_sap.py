"""Vérifier si MarmaraCam existe dans le cache SAP"""
import sqlite3

def check_marmaracam():
    """Cherche MarmaraCam dans le cache SAP"""

    db_path = r"C:\Users\PPZ\NOVA-SERVER\supplier_tariffs.db"

    print("=" * 80)
    print("RECHERCHE MARMARACAM DANS SAP")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Rechercher MarmaraCam par nom
    print("\n1. Recherche par nom contenant 'marmara' ou 'marmaracam':")
    cursor.execute("""
        SELECT CardCode, CardName, EmailAddress, Phone1
        FROM sap_clients
        WHERE LOWER(CardName) LIKE '%marmara%'
           OR LOWER(CardName) LIKE '%marmaracam%'
        LIMIT 10
    """)

    results = cursor.fetchall()
    if results:
        print(f"   [TROUVE] {len(results)} client(s):")
        for row in results:
            print(f"     - {row[0]}: {row[1]}")
            print(f"       Email: {row[2] or 'N/A'}")
            print(f"       Phone: {row[3] or 'N/A'}")
            print()
    else:
        print("   [NON TROUVE] Aucun client avec 'marmara' dans le nom")

    # Rechercher par email
    print("\n2. Recherche par email contenant 'marmaracam.com.tr':")
    cursor.execute("""
        SELECT CardCode, CardName, EmailAddress
        FROM sap_clients
        WHERE LOWER(EmailAddress) LIKE '%marmaracam.com.tr%'
        LIMIT 10
    """)

    results = cursor.fetchall()
    if results:
        print(f"   [TROUVE] {len(results)} client(s):")
        for row in results:
            print(f"     - {row[0]}: {row[1]} ({row[2]})")
    else:
        print("   [NON TROUVE] Aucun client avec email marmaracam.com.tr")

    # Rechercher SHEPPEE
    print("\n3. Recherche SHEPPEE (client matché par erreur):")
    cursor.execute("""
        SELECT CardCode, CardName, EmailAddress
        FROM sap_clients
        WHERE CardCode = 'C0278' OR LOWER(CardName) LIKE '%sheppee%'
        LIMIT 5
    """)

    results = cursor.fetchall()
    if results:
        print(f"   [TROUVE] {len(results)} client(s):")
        for row in results:
            print(f"     - {row[0]}: {row[1]} ({row[2] or 'N/A'})")

    # Compter le total de clients
    cursor.execute("SELECT COUNT(*) FROM sap_clients")
    total = cursor.fetchone()[0]

    print()
    print("=" * 80)
    print(f"Total clients dans SAP: {total}")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    check_marmaracam()
