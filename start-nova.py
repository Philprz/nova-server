#!/usr/bin/env python3
"""
start-nova.py
Script de démarrage unifié pour NOVA-SERVER
Lance Backend FastAPI + Frontend React Dev (optionnel)
"""

import sys
import subprocess
import time
import os
import signal
import platform
from pathlib import Path
from typing import Optional, List
import threading

# Configuration
BACKEND_HOST = "0.0.0.0"
BACKEND_PORT = 8000
FRONTEND_PORT = 8080

# Couleurs pour terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_banner():
    """Affiche la bannière NOVA"""
    print()
    print("=" * 70)
    print("  NOVA-SERVER v2.3.0 - Mode Developpement")
    print("  Plateforme Intelligente de Gestion Commerciale")
    print("=" * 70)
    print()


def check_python():
    """Vérifie la version de Python"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f"{Colors.FAIL}[ERREUR] Python 3.9+ requis. Version actuelle : {version.major}.{version.minor}{Colors.ENDC}")
        return False
    print(f"{Colors.OKGREEN}[OK] Python {version.major}.{version.minor}.{version.micro}{Colors.ENDC}")
    return True


def check_node():
    """Vérifie si Node.js est installé"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        print(f"{Colors.OKGREEN}[OK] Node.js {version}{Colors.ENDC}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.WARNING}[INFO] Node.js non trouve - Frontend dev non disponible{Colors.ENDC}")
        return False


def check_frontend_source():
    """Vérifie si le frontend source existe"""
    frontend_src = Path("mail-to-biz/src")
    if frontend_src.exists():
        print(f"{Colors.OKGREEN}[OK] Frontend source disponible{Colors.ENDC}")
        return True
    print(f"{Colors.WARNING}[INFO] Frontend source non trouve{Colors.ENDC}")
    return False


def kill_port(port: int):
    """Tue le processus qui utilise le port spécifié"""
    if platform.system() == "Windows":
        try:
            # Trouver et tuer les processus sur le port
            result = subprocess.run(
                f'netstat -ano | findstr :{port}',
                shell=True,
                capture_output=True,
                text=True
            )
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                pids = set()
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 5:
                        pids.add(parts[-1])
                for pid in pids:
                    if pid.isdigit():
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
        except Exception:
            pass
    else:
        try:
            subprocess.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null", shell=True, capture_output=True)
        except Exception:
            pass


def stream_output(process, prefix, color):
    """Stream la sortie d'un processus en temps réel"""
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"{color}[{prefix}]{Colors.ENDC} {line.rstrip()}")
    except Exception:
        pass


def start_backend() -> Optional[subprocess.Popen]:
    """Démarre le backend FastAPI"""
    print(f"\n{Colors.OKBLUE}Demarrage Backend FastAPI sur port {BACKEND_PORT}...{Colors.ENDC}")

    kill_port(BACKEND_PORT)
    time.sleep(1)

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )

        # Thread pour afficher la sortie
        thread = threading.Thread(
            target=stream_output,
            args=(process, "BACKEND", Colors.OKCYAN),
            daemon=True
        )
        thread.start()

        # Attendre que le backend démarre
        time.sleep(3)

        if process.poll() is not None:
            print(f"{Colors.FAIL}[ERREUR] Backend n'a pas pu demarrer{Colors.ENDC}")
            return None

        print(f"{Colors.OKGREEN}[OK] Backend demarre{Colors.ENDC}")
        return process

    except Exception as e:
        print(f"{Colors.FAIL}[ERREUR] {e}{Colors.ENDC}")
        return None


def start_frontend() -> Optional[subprocess.Popen]:
    """Démarre le frontend React Dev Server"""
    print(f"\n{Colors.OKBLUE}Demarrage Frontend Dev sur port {FRONTEND_PORT}...{Colors.ENDC}")

    kill_port(FRONTEND_PORT)
    time.sleep(1)

    try:
        env = os.environ.copy()
        env["FORCE_COLOR"] = "1"

        # Utiliser npx vite pour plus de fiabilité
        if platform.system() == "Windows":
            process = subprocess.Popen(
                ["npm.cmd", "run", "dev"],
                cwd="mail-to-biz",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
        else:
            process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd="mail-to-biz",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )

        # Thread pour afficher la sortie
        thread = threading.Thread(
            target=stream_output,
            args=(process, "FRONTEND", Colors.WARNING),
            daemon=True
        )
        thread.start()

        time.sleep(3)

        if process.poll() is not None:
            print(f"{Colors.FAIL}[ERREUR] Frontend n'a pas pu demarrer{Colors.ENDC}")
            return None

        print(f"{Colors.OKGREEN}[OK] Frontend demarre{Colors.ENDC}")
        return process

    except Exception as e:
        print(f"{Colors.FAIL}[ERREUR] {e}{Colors.ENDC}")
        return None


def print_urls(has_frontend_dev: bool = False):
    """Affiche les URLs d'accès"""
    print()
    print("=" * 70)
    print(f"  {Colors.OKGREEN}NOVA PRET !{Colors.ENDC}")
    print("=" * 70)
    print()

    if has_frontend_dev:
        print(f"  {Colors.BOLD}>>> Frontend Dev (hot reload): http://localhost:{FRONTEND_PORT}/mail-to-biz/{Colors.ENDC}")
        print()

    print(f"  Backend API:      http://localhost:{BACKEND_PORT}")
    print(f"  Frontend compile: http://localhost:{BACKEND_PORT}/mail-to-biz")
    print(f"  NOVA Assistant:   http://localhost:{BACKEND_PORT}/interface/itspirit")
    print(f"  API Docs:         http://localhost:{BACKEND_PORT}/docs")
    print()
    print("=" * 70)
    print(f"  {Colors.WARNING}CTRL+C pour arreter{Colors.ENDC}")
    print("=" * 70)
    print()


def cleanup(processes: List[subprocess.Popen]):
    """Arrête proprement tous les processus"""
    print(f"\n{Colors.WARNING}Arret des services...{Colors.ENDC}")

    for process in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    # Nettoyer les ports
    kill_port(BACKEND_PORT)
    kill_port(FRONTEND_PORT)

    print(f"{Colors.OKGREEN}Services arretes.{Colors.ENDC}\n")


def main():
    """Point d'entrée principal"""
    print_banner()

    if not check_python():
        sys.exit(1)

    has_node = check_node()
    has_frontend_src = check_frontend_source()

    processes = []

    # Démarrer backend
    backend_process = start_backend()
    if not backend_process:
        print(f"{Colors.FAIL}Impossible de demarrer NOVA.{Colors.ENDC}")
        sys.exit(1)
    processes.append(backend_process)

    # Démarrer frontend dev si disponible
    frontend_process = None
    if has_node and has_frontend_src:
        frontend_process = start_frontend()
        if frontend_process:
            processes.append(frontend_process)

    # Afficher les URLs
    print_urls(has_frontend_dev=frontend_process is not None)

    # Gestion du CTRL+C
    def signal_handler(sig, frame):
        cleanup(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, signal_handler)

    # Boucle principale - surveiller les processus
    try:
        while True:
            # Vérifier si un processus s'est arrêté
            for i, process in enumerate(processes):
                if process and process.poll() is not None:
                    name = "Backend" if i == 0 else "Frontend"
                    print(f"\n{Colors.FAIL}[ERREUR] {name} s'est arrete!{Colors.ENDC}")
                    cleanup(processes)
                    sys.exit(1)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(processes)


if __name__ == "__main__":
    main()
