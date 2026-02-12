import sqlite3

conn = sqlite3.connect('C:/Users/PPZ/NOVA-SERVER/supplier_tariffs.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM sap_clients')
print(f'Clients: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM sap_items')
print(f'Articles: {cursor.fetchone()[0]}')

cursor.execute('SELECT * FROM sap_sync_metadata')
print('\nSync metadata:')
for row in cursor.fetchall():
    print(f'  {row[0]}: last_sync={row[1]}, total={row[2]}, status={row[3]}')

# Rechercher SAVERGLASS
cursor.execute("SELECT CardCode, CardName, EmailAddress FROM sap_clients WHERE CardName LIKE '%SAVERGLASS%' OR CardName LIKE '%Saverglass%'")
print('\nRecherche SAVERGLASS:')
for row in cursor.fetchall():
    print(f'  {row[0]} - {row[1]} ({row[2]})')

conn.close()
