#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test simple du workflow de devis
===============================
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_workflow():
    """Test simple du workflow"""
    print("Test du workflow de devis...")
    
    url = f"{BASE_URL}/api/assistant/workflow/create_quote"
    data = {"message": "Creer un devis pour Edge Communications"}
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Succes: {result.get('success', False)}")
            print(f"Message: {result.get('message', 'N/A')}")
            print(f"Status workflow: {result.get('workflow_status', 'N/A')}")
        else:
            print(f"Erreur HTTP: {response.status_code}")
            print(f"Reponse: {response.text}")
            
    except Exception as e:
        print(f"Erreur: {e}")

def test_chat():
    """Test simple du chat"""
    print("\nTest du chat...")
    
    url = f"{BASE_URL}/api/assistant/chat"
    data = {"message": "Creer un devis"}
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Succes: {result.get('success', False)}")
            if result.get('success'):
                print(f"Type: {result['response'].get('type', 'N/A')}")
                print(f"Message: {result['response']['message'][:100]}...")
        else:
            print(f"Erreur HTTP: {response.status_code}")
            
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    test_workflow()
    test_chat()
