"""
Script de test pour la démonstration du système 2FA
Permet de tester tous les endpoints MFA de manière interactive

Usage:
    python demo_2fa_test.py
"""

import requests
import json
import time
from typing import Optional
import pyotp
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Configuration
BASE_URL = "http://localhost:8200"
console = Console()


class MFADemoClient:
    """Client de démonstration pour le système 2FA"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.mfa_pending_token: Optional[str] = None
        self.access_token: Optional[str] = None
        self.totp_secret: Optional[str] = None

    def _headers(self, token: Optional[str] = None) -> dict:
        """Génère les headers HTTP avec le token d'authentification"""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _print_response(self, response: requests.Response, title: str = "Réponse"):
        """Affiche une réponse HTTP formatée"""
        console.rule(f"[bold blue]{title}[/bold blue]")

        # Status code avec couleur
        if response.status_code < 300:
            status_color = "green"
        elif response.status_code < 400:
            status_color = "yellow"
        else:
            status_color = "red"

        console.print(f"Status: [{status_color}]{response.status_code}[/{status_color}]")

        # Body JSON
        try:
            data = response.json()
            console.print_json(json.dumps(data, indent=2))
        except:
            console.print(response.text)

        console.print()

    def login(self, email: str, password: str) -> bool:
        """
        Étape 1 : Connexion avec email/password (1er facteur)
        Retourne un token mfa_pending
        """
        console.rule("[bold yellow]ÉTAPE 1: Connexion (1er facteur)[/bold yellow]")

        self.email = email
        self.password = password

        # Note: Cet endpoint pourrait ne pas exister encore
        # Dans ce cas, vous devez créer un token mfa_pending manuellement
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password}
            )
            self._print_response(response, "POST /auth/login")

            if response.status_code == 200:
                data = response.json()
                self.mfa_pending_token = data.get("access_token")
                console.print("[green]✓[/green] Token mfa_pending reçu!")
                return True
            else:
                console.print("[red]✗[/red] Échec de connexion")
                return False

        except requests.exceptions.RequestException as e:
            console.print(f"[red]Erreur:[/red] {e}")
            console.print("[yellow]Conseil:[/yellow] Créez un token mfa_pending manuellement pour continuer")
            return False

    def set_manual_token(self, token: str, token_type: str = "mfa_pending"):
        """Définir manuellement un token pour la démo"""
        if token_type == "mfa_pending":
            self.mfa_pending_token = token
            console.print(f"[green]✓[/green] Token mfa_pending défini: {token[:20]}...")
        else:
            self.access_token = token
            console.print(f"[green]✓[/green] Token completed défini: {token[:20]}...")

    def get_mfa_status(self) -> dict:
        """
        Récupère le statut MFA de l'utilisateur
        """
        console.rule("[bold cyan]Statut MFA[/bold cyan]")

        token = self.access_token or self.mfa_pending_token
        if not token:
            console.print("[red]Erreur:[/red] Aucun token disponible")
            return {}

        response = requests.get(
            f"{self.base_url}/api/mfa/status",
            headers=self._headers(token)
        )
        self._print_response(response, "GET /api/mfa/status")

        if response.status_code == 200:
            return response.json()
        return {}

    def enroll_totp_start(self) -> Optional[str]:
        """
        Démarre l'enrollment TOTP
        Retourne le secret TOTP et affiche le QR code
        """
        console.rule("[bold yellow]ÉTAPE 2: Enrollment TOTP - Démarrage[/bold yellow]")

        if not self.access_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'completed' (utilisateur déjà connecté)")
            return None

        response = requests.post(
            f"{self.base_url}/api/mfa/totp/enroll/start",
            headers=self._headers(self.access_token)
        )
        self._print_response(response, "POST /api/mfa/totp/enroll/start")

        if response.status_code == 200:
            data = response.json()
            self.totp_secret = data.get("secret")

            console.print(Panel.fit(
                f"[bold green]Secret TOTP:[/bold green] {self.totp_secret}\n\n"
                f"[yellow]Scannez le QR code avec Google Authenticator[/yellow]\n"
                f"QR Code disponible dans la réponse (format base64)",
                title="Enrollment TOTP"
            ))

            return self.totp_secret

        return None

    def enroll_totp_verify(self, code: str) -> bool:
        """
        Vérifie le code TOTP pour terminer l'enrollment
        Retourne les codes de récupération
        """
        console.rule("[bold yellow]ÉTAPE 3: Enrollment TOTP - Vérification[/bold yellow]")

        if not self.access_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'completed'")
            return False

        response = requests.post(
            f"{self.base_url}/api/mfa/totp/enroll/verify",
            headers=self._headers(self.access_token),
            json={"code": code}
        )
        self._print_response(response, "POST /api/mfa/totp/enroll/verify")

        if response.status_code == 200:
            data = response.json()
            recovery_codes = data.get("recovery_codes", [])

            console.print(Panel.fit(
                "[bold green]TOTP activé avec succès![/bold green]\n\n"
                "[yellow]Codes de récupération (à conserver en lieu sûr):[/yellow]\n" +
                "\n".join(f"  • {code}" for code in recovery_codes),
                title="Codes de récupération"
            ))

            return True

        return False

    def verify_totp(self, code: str) -> bool:
        """
        Vérifie un code TOTP lors de la connexion (2ème facteur)
        Retourne un token 'completed'
        """
        console.rule("[bold yellow]ÉTAPE 4: Vérification TOTP (2FA)[/bold yellow]")

        if not self.mfa_pending_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'mfa_pending'")
            return False

        response = requests.post(
            f"{self.base_url}/api/mfa/verify/totp",
            headers=self._headers(self.mfa_pending_token),
            json={"code": code}
        )
        self._print_response(response, "POST /api/mfa/verify/totp")

        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            console.print("[green]✓[/green] Authentification 2FA réussie!")
            console.print(f"[green]✓[/green] Token completed reçu: {self.access_token[:20]}...")
            return True

        return False

    def send_sms_otp(self) -> bool:
        """
        Envoie un code OTP par SMS
        """
        console.rule("[bold cyan]Envoi SMS OTP[/bold cyan]")

        if not self.mfa_pending_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'mfa_pending'")
            return False

        response = requests.post(
            f"{self.base_url}/api/mfa/sms/send",
            headers=self._headers(self.mfa_pending_token)
        )
        self._print_response(response, "POST /api/mfa/sms/send")

        return response.status_code == 200

    def verify_sms(self, code: str) -> bool:
        """
        Vérifie un code SMS lors de la connexion (2ème facteur)
        """
        console.rule("[bold yellow]Vérification SMS OTP[/bold yellow]")

        if not self.mfa_pending_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'mfa_pending'")
            return False

        response = requests.post(
            f"{self.base_url}/api/mfa/verify/sms",
            headers=self._headers(self.mfa_pending_token),
            json={"code": code}
        )
        self._print_response(response, "POST /api/mfa/verify/sms")

        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            console.print("[green]✓[/green] Authentification SMS réussie!")
            return True

        return False

    def verify_recovery(self, code: str) -> bool:
        """
        Vérifie un code de récupération lors de la connexion
        """
        console.rule("[bold yellow]Vérification Code de Récupération[/bold yellow]")

        if not self.mfa_pending_token:
            console.print("[red]Erreur:[/red] Nécessite un token 'mfa_pending'")
            return False

        response = requests.post(
            f"{self.base_url}/api/mfa/verify/recovery",
            headers=self._headers(self.mfa_pending_token),
            json={"code": code}
        )
        self._print_response(response, "POST /api/mfa/verify/recovery")

        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            remaining = data.get("remaining_codes", 0)
            console.print(f"[green]✓[/green] Code de récupération valide! ({remaining} codes restants)")
            return True

        return False

    def generate_current_totp_code(self) -> Optional[str]:
        """
        Génère le code TOTP actuel à partir du secret
        Utile pour les tests automatisés
        """
        if not self.totp_secret:
            console.print("[red]Erreur:[/red] Aucun secret TOTP disponible")
            return None

        totp = pyotp.TOTP(self.totp_secret)
        code = totp.now()
        console.print(f"[cyan]Code TOTP actuel:[/cyan] {code}")
        return code

    def test_bruteforce_protection(self):
        """
        Test de la protection anti-bruteforce
        Envoie 10 codes invalides pour déclencher le blocage
        """
        console.rule("[bold red]Test Protection Anti-Bruteforce[/bold red]")
        console.print("[yellow]Envoi de 10 codes invalides...[/yellow]\n")

        for i in range(10):
            console.print(f"Tentative {i+1}/10...", end=" ")
            response = requests.post(
                f"{self.base_url}/api/mfa/verify/totp",
                headers=self._headers(self.mfa_pending_token),
                json={"code": "000000"}  # Code invalide
            )

            if response.status_code == 429 or "verrouillé" in response.text.lower():
                console.print("[red]BLOQUÉ![/red]")
                self._print_response(response, f"Tentative {i+1}")
                console.print("[green]✓[/green] Protection anti-bruteforce activée!")
                return
            else:
                console.print(f"[yellow]{response.status_code}[/yellow]")

            time.sleep(0.5)

        console.print("[yellow]Aucun blocage détecté après 10 tentatives[/yellow]")


def demo_complete_flow():
    """
    Démonstration complète du flux 2FA
    """
    client = MFADemoClient()

    console.print(Panel.fit(
        "[bold blue]Démonstration Système 2FA - NOVA SERVER[/bold blue]\n\n"
        "Ce script va tester tous les endpoints MFA",
        title="Démarrage de la démo"
    ))

    # 1. Connexion
    email = input("\nEmail de test: ") or "demo@itspirit.fr"
    password = input("Mot de passe: ") or "test123"

    client.login(email, password)

    # Si pas de token, demander manuellement
    if not client.mfa_pending_token:
        console.print("\n[yellow]L'endpoint /auth/login n'existe pas encore.[/yellow]")
        use_manual = input("Voulez-vous entrer un token manuellement ? (o/n): ")
        if use_manual.lower() == 'o':
            token = input("Token mfa_pending: ")
            client.set_manual_token(token, "mfa_pending")

    # 2. Statut MFA
    if client.mfa_pending_token:
        input("\nAppuyez sur Entrée pour vérifier le statut MFA...")
        status = client.get_mfa_status()

    # 3. Choix du test
    console.print("\n[bold cyan]Quel scénario voulez-vous tester ?[/bold cyan]")
    console.print("1. Enrollment TOTP (nouveau compte)")
    console.print("2. Vérification TOTP (connexion 2FA)")
    console.print("3. SMS OTP (méthode de secours)")
    console.print("4. Code de récupération")
    console.print("5. Test anti-bruteforce")
    console.print("6. Quitter")

    choice = input("\nChoix (1-6): ")

    if choice == "1":
        # Enrollment TOTP
        completed_token = input("\nToken 'completed' (utilisateur connecté): ")
        client.set_manual_token(completed_token, "completed")

        input("\nAppuyez sur Entrée pour démarrer l'enrollment...")
        secret = client.enroll_totp_start()

        if secret:
            console.print(f"\n[cyan]Secret TOTP:[/cyan] {secret}")
            console.print("[yellow]Scannez le QR code ou entrez le secret dans Google Authenticator[/yellow]")

            code = input("\nEntrez le code à 6 chiffres: ")
            client.enroll_totp_verify(code)

    elif choice == "2":
        # Vérification TOTP
        if client.totp_secret:
            console.print("\n[cyan]Génération automatique du code...[/cyan]")
            code = client.generate_current_totp_code()
        else:
            code = input("\nEntrez le code TOTP à 6 chiffres: ")

        input("\nAppuyez sur Entrée pour vérifier le code TOTP...")
        client.verify_totp(code)

    elif choice == "3":
        # SMS OTP
        input("\nAppuyez sur Entrée pour envoyer le SMS...")
        if client.send_sms_otp():
            code = input("\nEntrez le code SMS reçu: ")
            client.verify_sms(code)

    elif choice == "4":
        # Code de récupération
        code = input("\nEntrez un code de récupération (format XXXX-XXXX): ")
        client.verify_recovery(code)

    elif choice == "5":
        # Test anti-bruteforce
        input("\nAppuyez sur Entrée pour démarrer le test anti-bruteforce...")
        client.test_bruteforce_protection()

    console.print("\n[bold green]Démonstration terminée![/bold green]")


def demo_quick_status():
    """
    Démo rapide - affiche juste le statut MFA
    """
    client = MFADemoClient()

    token = input("Token (mfa_pending ou completed): ")
    client.set_manual_token(token, "completed")

    client.get_mfa_status()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        demo_quick_status()
    else:
        demo_complete_flow()
