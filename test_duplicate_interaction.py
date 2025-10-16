#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour verifier l'envoi des interactions de doublons
"""
import requests
import time
import json
import sys
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TASK_ID = "quote_20251016_162538_b04ec8cd"
BASE_URL = "http://localhost:8200"

def check_task_status():
    """Verifie le statut de la tache"""
    try:
        response = requests.get(f"{BASE_URL}/progress/quote_status/{TASK_ID}")
        if response.status_code == 200:
            data = response.json()
            print(f"\n{'='*80}")
            print(f"[{time.strftime('%H:%M:%S')}]")
            print(f"Statut: {data.get('status')}")
            print(f"Etape: {data.get('current_step')} - {data.get('current_step_title')}")
            print(f"Progression: {data.get('overall_progress')}% ({data.get('completed_steps')}/{data.get('total_steps')})")

            # Verifier si interaction requise
            if data.get('status') == 'user_interaction_required':
                print(f"\n*** INTERACTION REQUISE DETECTEE! ***")
                if data.get('result'):
                    result = data.get('result')
                    interaction_type = result.get('interaction_type') or result.get('type')
                    print(f"   Type: {interaction_type}")
                    print(f"   Message: {result.get('message')}")
                    if 'interaction_data' in result:
                        print(f"   Donnees: {json.dumps(result['interaction_data'], indent=2)}")
                return True

            if data.get('error'):
                print(f"\nERREUR: {data.get('error')}")
                return True

            if data.get('completed'):
                print(f"\nTACHE COMPLETEE")
                return True

        else:
            print(f"Erreur HTTP: {response.status_code}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

def main():
    """Surveille la tache en boucle"""
    print(f"Surveillance de la tache: {TASK_ID}")
    print(f"URL: {BASE_URL}")

    for i in range(60):  # Max 60 secondes
        if check_task_status():
            break
        time.sleep(1)

    print(f"\n{'='*80}")
    print("Surveillance terminee")

if __name__ == "__main__":
    main()
