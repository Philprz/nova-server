"""Vider la table product_code_mapping corrompue"""
import sqlite3

db_path = "C:/Users/PPZ/NOVA-SERVER/supplier_tariffs.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Compter avant
cursor.execute("SELECT COUNT(*) FROM product_code_mapping")
count_before = cursor.fetchone()[0]
print(f"Mappings avant suppression: {count_before}")

# Supprimer tous les mappings
cursor.execute("DELETE FROM product_code_mapping")
conn.commit()

# Compter après
cursor.execute("SELECT COUNT(*) FROM product_code_mapping")
count_after = cursor.fetchone()[0]
print(f"Mappings apres suppression: {count_after}")

conn.close()
print("\nTable product_code_mapping videe!")
