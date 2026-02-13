"""Script pour vider le cache d'analyse des emails (force une réanalyse complète)"""
import requests

def clear_cache():
    """
    Vide le cache d'analyse en redémarrant simplement le backend.

    Pour une réanalyse immédiate sans redémarrage:
    - Le frontend doit passer force=true dans l'appel à analyzeGraphEmail()
    - Ou rafraîchir la page (F5) pour vider le cache frontend
    """

    print("=" * 70)
    print("NETTOYAGE DU CACHE D'ANALYSE")
    print("=" * 70)
    print()
    print("Le cache d'analyse est en mémoire et se vide automatiquement")
    print("au redémarrage du backend.")
    print()
    print("OPTIONS POUR FORCER UNE REANALYSE:")
    print()
    print("1. REDEMARRER LE BACKEND (recommandé)")
    print("   - Arrêter le backend (Ctrl+C)")
    print("   - Relancer: python main.py")
    print("   - Le cache sera vide au démarrage")
    print()
    print("2. RAFRAICHIR LE FRONTEND")
    print("   - Appuyer sur F5 dans le navigateur")
    print("   - Cela vide le cache frontend (analysisCache)")
    print()
    print("3. APPELER L'API AVEC force=true")
    print("   - POST /api/graph/emails/{id}/analyze?force=true")
    print("   - Bypass les deux caches (frontend + backend)")
    print()
    print("4. UTILISER LE SCRIPT DE TEST")
    print("   - python test_chiffrage_api_real.py")
    print("   - Appelle automatiquement avec force=true")
    print()
    print("=" * 70)
    print("VERIFICATION: Le backend a-t-il été redémarré après la correction?")
    print("=" * 70)
    print()

    # Tester si le backend est accessible
    try:
        r = requests.get("http://localhost:8001/health")
        if r.status_code == 200:
            print("[OK] Backend accessible sur http://localhost:8001")
            data = r.json()
            if 'uptime' in data:
                print(f"     Uptime: {data['uptime']}")
                print()
                print("Si uptime > 1 minute, le backend n'a pas été redémarré récemment.")
                print("Redémarrez-le pour charger le code corrigé.")
        else:
            print("[WARNING] Backend répond mais avec code", r.status_code)
    except Exception as e:
        print("[ERREUR] Backend non accessible:")
        print(f"         {e}")
        print()
        print("Vérifiez que le backend est lancé: python main.py")

    print()
    print("=" * 70)

if __name__ == "__main__":
    clear_cache()
