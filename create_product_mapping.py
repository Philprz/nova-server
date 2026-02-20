"""
Script pour créer un mapping entre référence externe et code SAP interne
"""

import sqlite3

def create_mapping(external_code: str, sap_code: str):
    """
    Crée un mapping entre une référence externe (client) et un code SAP interne
    """
    conn = sqlite3.connect('supplier_tariffs.db')
    cursor = conn.cursor()

    # Créer la table product_mappings si elle n'existe pas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_mappings (
            external_code TEXT PRIMARY KEY,
            sap_code TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            confidence REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insérer le mapping
    cursor.execute("""
        INSERT OR REPLACE INTO product_mappings
        (external_code, sap_code, source, confidence)
        VALUES (?, ?, 'manual', 1.0)
    """, (external_code, sap_code))

    conn.commit()
    conn.close()

    print(f"[OK] Mapping cree:")
    print(f"     Reference externe: {external_code}")
    print(f"     Code SAP interne: {sap_code}")

if __name__ == "__main__":
    # EXEMPLE : Si 2323060165 correspond au code SAP A02509
    # Décommentez et modifiez selon vos besoins

    # create_mapping("2323060165", "A02509")

    print("[INFO] Modifiez ce script pour creer vos mappings")
    print("       Exemple: create_mapping('2323060165', 'A02509')")
