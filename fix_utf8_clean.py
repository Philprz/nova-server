#!/usr/bin/env python3
"""
Script de correction automatique pour forcer UTF-8 sur tous les HTMLResponse
Projet NOVA - Correction des problèmes d'accents
"""

import os
import re
import glob
from pathlib import Path

def fix_html_response_encoding(file_path):
    """Corrige les HTMLResponse pour forcer charset=utf-8"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    fixes_applied = []
    
    # Pattern 1: HTMLResponse avec media_type sans charset
    pattern1 = r'HTMLResponse\(([^)]*?)media_type=["\']text/html["\']([^)]*?)\)'
    def replace1(match):
        before = match.group(1)
        after = match.group(2)
        fixes_applied.append(f"Ajout charset=utf-8 dans media_type")
        return f'HTMLResponse({before}media_type="text/html; charset=utf-8"{after})'
    
    content = re.sub(pattern1, replace1, content)
    
    # Pattern 2: HTMLResponse sans media_type du tout
    pattern2 = r'HTMLResponse\(([^)]*?)content=([^,)]+)([^)]*?)\)'
    def replace2(match):
        before = match.group(1)
        content_part = match.group(2)
        after = match.group(3)
        
        # Vérifier si media_type est déjà présent
        if 'media_type' not in match.group(0):
            fixes_applied.append(f"Ajout media_type avec charset=utf-8")
            if after.strip():
                return f'HTMLResponse({before}content={content_part}, media_type="text/html; charset=utf-8"{after})'
            else:
                return f'HTMLResponse({before}content={content_part}, media_type="text/html; charset=utf-8")'
        return match.group(0)
    
    content = re.sub(pattern2, replace2, content)
    
    if content != original_content:
        # Backup du fichier original
        backup_path = f"{file_path}.backup"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Écriture du fichier corrigé
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return fixes_applied
    
    return []

def scan_and_fix_project(project_root="."):
    """Scanne tout le projet et corrige les HTMLResponse"""
    
    python_files = []
    
    # Chercher tous les fichiers Python
    for pattern in ["*.py", "**/*.py"]:
        python_files.extend(glob.glob(os.path.join(project_root, pattern), recursive=True))
    
    total_fixes = 0
    files_modified = []
    
    print("🔍 Scan des fichiers Python pour HTMLResponse...")
    print("=" * 60)
    
    for file_path in python_files:
        # Ignorer les fichiers de backup et venv
        if '.backup' in file_path or 'venv' in file_path or '__pycache__' in file_path:
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Vérifier si le fichier contient HTMLResponse
            if 'HTMLResponse' in content:
                print(f"📄 Analyse: {file_path}")
                fixes = fix_html_response_encoding(file_path)
                
                if fixes:
                    files_modified.append(file_path)
                    total_fixes += len(fixes)
                    print(f"   ✅ {len(fixes)} corrections appliquées:")
                    for fix in fixes:
                        print(f"      - {fix}")
                else:
                    print(f"   ℹ️  Aucune correction nécessaire")
                    
        except Exception as e:
            print(f"   ❌ Erreur lors du traitement de {file_path}: {e}")
    
    print("=" * 60)
    print(f"🎯 RÉSUMÉ:")
    print(f"   Fichiers modifiés: {len(files_modified)}")
    print(f"   Total corrections: {total_fixes}")
    
    if files_modified:
        print(f"\n📋 Fichiers modifiés:")
        for file_path in files_modified:
            print(f"   - {file_path} (backup: {file_path}.backup)")
    
    return files_modified, total_fixes

def create_utf8_middleware():
    """Crée un middleware FastAPI pour forcer UTF-8 sur toutes les réponses HTML"""
    
    middleware_code = '''# Middleware UTF-8 pour NOVA
# À ajouter dans main.py après la création de l'app FastAPI

from fastapi import Request
from fastapi.responses import HTMLResponse

@app.middleware("http")
async def force_utf8_html_middleware(request: Request, call_next):
    """Middleware pour forcer UTF-8 sur toutes les réponses HTML"""
    response = await call_next(request)
    
    # Si c'est une réponse HTML, s'assurer que charset=utf-8 est présent
    if isinstance(response, HTMLResponse) or (
        hasattr(response, 'media_type') and 
        response.media_type and 
        'text/html' in response.media_type
    ):
        # Forcer le charset UTF-8
        if 'charset' not in response.media_type:
            response.media_type = "text/html; charset=utf-8"
        
        # S'assurer que l'en-tête Content-Type est correct
        response.headers["Content-Type"] = "text/html; charset=utf-8"
    
    return response
'''
    
    with open('utf8_middleware.py', 'w', encoding='utf-8') as f:
        f.write(middleware_code)
    
    return 'utf8_middleware.py'

if __name__ == "__main__":
    print("🚀 NOVA - Script de correction UTF-8 pour HTMLResponse")
    print("=" * 60)
    
    # 1. Scanner et corriger les fichiers existants
    modified_files, total_fixes = scan_and_fix_project()
    
    # 2. Créer le middleware de sécurité
    middleware_file = create_utf8_middleware()
    print(f"\n🛡️  Middleware UTF-8 créé: {middleware_file}")
    
    print("\n" + "=" * 60)
    print("✅ CORRECTION TERMINÉE")
    
    if total_fixes > 0:
        print("\n🔧 ACTIONS RECOMMANDÉES:")
        print("1. Vérifier les fichiers modifiés")
        print("2. Tester l'application")
        print("3. Si OK, supprimer les fichiers .backup")
        print("4. Optionnel: Ajouter le middleware UTF-8 dans main.py")
    else:
        print("\nℹ️  Aucune correction nécessaire - les HTMLResponse semblent déjà corrects")