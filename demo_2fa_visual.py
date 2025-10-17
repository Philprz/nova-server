"""
Script de démonstration visuelle du système 2FA
Version améliorée avec flux complet et affichage clair
"""

import requests
import json
import time
import pyotp
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich import box

BASE_URL = "http://localhost:8200"
console = Console()


def print_banner():
    """Affiche la bannière de démarrage"""
    banner = """
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║      DÉMONSTRATION 2FA - NOVA SERVER                 ║
    ║      Authentification à Deux Facteurs                ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")


def print_step(step_num: int, title: str):
    """Affiche un titre d'étape"""
    console.print()
    console.rule(f"[bold cyan]ÉTAPE {step_num}: {title}[/bold cyan]", style="cyan")
    console.print()


def print_success(message: str):
    """Affiche un message de succès"""
    console.print(f"✅ [bold green]{message}[/bold green]")


def print_error(message: str):
    """Affiche un message d'erreur"""
    console.print(f"❌ [bold red]{message}[/bold red]")


def print_warning(message: str):
    """Affiche un avertissement"""
    console.print(f"⚠️  [bold yellow]{message}[/bold yellow]")


def print_info(message: str):
    """Affiche une information"""
    console.print(f"ℹ️  [cyan]{message}[/cyan]")


def print_response(response: requests.Response, title: str = "Réponse API"):
    """Affiche une réponse HTTP formatée"""
    # Status code avec couleur
    if response.status_code < 300:
        status_style = "bold green"
        status_icon = "✅"
    elif response.status_code < 400:
        status_style = "bold yellow"
        status_icon = "⚠️"
    else:
        status_style = "bold red"
        status_icon = "❌"

    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"{status_icon} Status: [{status_style}]{response.status_code}[/{status_style}]")

    # Body JSON
    try:
        data = response.json()
        console.print_json(json.dumps(data, indent=2))
    except:
        console.print(response.text)


def demo_complete_flow():
    """Flux complet de démonstration 2FA"""
    print_banner()

    # Variables pour stocker les tokens
    mfa_pending_token = None
    access_token = None
    totp_secret = None
    recovery_codes = []

    # ========================================
    # ÉTAPE 1 : CONNEXION (1ER FACTEUR)
    # ========================================
    print_step(1, "Connexion avec Email/Password (1er facteur)")

    print_info("Entrez vos identifiants:")
    email = Prompt.ask("📧 Email", default="p.perez@it-spirit.com")
    password = Prompt.ask("🔐 Mot de passe", password=True, default="31021225")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Connexion en cours...", total=None)

        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            progress.stop()

            print_response(response, "Réponse de connexion")

            if response.status_code == 200:
                data = response.json()
                mfa_pending_token = data.get("access_token")

                if data.get("mfa_required"):
                    print_success("Connexion réussie ! Token MFA_PENDING reçu")
                    print_info(f"Token valide pendant 5 minutes")
                    print_info(f"Token: {mfa_pending_token[:30]}...")

                    # Afficher un tableau récapitulatif
                    table = Table(title="Informations de connexion", box=box.ROUNDED)
                    table.add_column("Propriété", style="cyan")
                    table.add_column("Valeur", style="green")
                    table.add_row("User ID", str(data.get("user_id")))
                    table.add_row("Email", data.get("email"))
                    table.add_row("MFA Requis", "✅ OUI" if data.get("mfa_required") else "❌ NON")
                    table.add_row("Étape", data.get("mfa_stage", "N/A"))
                    console.print(table)
                else:
                    print_warning("2FA non activé pour ce compte")
                    access_token = mfa_pending_token
                    return
            else:
                print_error(f"Échec de connexion: {response.status_code}")
                return

        except requests.exceptions.ConnectionError:
            progress.stop()
            print_error("Impossible de se connecter au serveur")
            print_warning(f"Vérifiez que le serveur tourne sur {BASE_URL}")
            return
        except Exception as e:
            progress.stop()
            print_error(f"Erreur: {e}")
            return

    if not mfa_pending_token:
        return

    # ========================================
    # ÉTAPE 2 : VÉRIFIER LE STATUT MFA
    # ========================================
    print_step(2, "Vérification du statut MFA")

    Prompt.ask("Appuyez sur [Entrée] pour continuer", default="")

    try:
        response = requests.get(
            f"{BASE_URL}/api/mfa/status",
            headers={"Authorization": f"Bearer {mfa_pending_token}"}
        )

        print_response(response, "Statut MFA")

        if response.status_code == 200:
            status_data = response.json()

            # Afficher un tableau du statut
            table = Table(title="Statut 2FA de l'utilisateur", box=box.DOUBLE)
            table.add_column("Paramètre", style="cyan", no_wrap=True)
            table.add_column("État", style="green")

            table.add_row("TOTP Activé", "✅ OUI" if status_data.get("totp_enabled") else "❌ NON")
            table.add_row("Téléphone Vérifié", "✅ OUI" if status_data.get("phone_verified") else "❌ NON")

            if status_data.get("phone_number"):
                table.add_row("Numéro", status_data.get("phone_number"))

            table.add_row("Méthode Secours", status_data.get("backup_method", "none"))
            table.add_row("Codes Récupération", str(status_data.get("recovery_codes_count", 0)))
            table.add_row("MFA Obligatoire", "✅ OUI" if status_data.get("mfa_enforced") else "❌ NON")
            table.add_row("Compte Bloqué", "🔒 OUI" if status_data.get("is_locked") else "✅ NON")

            console.print(table)

    except Exception as e:
        print_error(f"Erreur: {e}")

    # ========================================
    # ÉTAPE 3 : CHOIX DU SCÉNARIO
    # ========================================
    print_step(3, "Choix du scénario de test")

    console.print("[bold cyan]Scénarios disponibles:[/bold cyan]")
    console.print("  1. 🔐 Vérifier un code TOTP (Google Authenticator)")
    console.print("  2. 📱 Demander un code SMS")
    console.print("  3. 🎫 Utiliser un code de récupération")
    console.print("  4. 🛡️  Tester la protection anti-bruteforce")
    console.print()

    choice = Prompt.ask("Votre choix", choices=["1", "2", "3", "4"], default="1")

    # ========================================
    # SCÉNARIO 1 : TOTP
    # ========================================
    if choice == "1":
        print_step(4, "Vérification du code TOTP")

        print_info("Ouvrez Google Authenticator ou Microsoft Authenticator")
        print_info("Scannez le QR code ou entrez le code manuellement")
        console.print()

        totp_code = Prompt.ask("🔢 Code TOTP (6 chiffres)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Vérification du code TOTP...", total=None)

            try:
                response = requests.post(
                    f"{BASE_URL}/api/mfa/verify/totp",
                    headers={"Authorization": f"Bearer {mfa_pending_token}"},
                    json={"code": totp_code}
                )
                progress.stop()

                print_response(response, "Vérification TOTP")

                if response.status_code == 200:
                    data = response.json()
                    access_token = data.get("access_token")

                    print_success("🎉 AUTHENTIFICATION 2FA RÉUSSIE !")
                    print_info(f"Token complet reçu (valide 60 minutes)")
                    print_info(f"Token: {access_token[:30]}...")

                    # Afficher un panel de succès
                    success_panel = Panel(
                        "[bold green]✅ Vous êtes maintenant authentifié ![/bold green]\n\n"
                        "Vous pouvez accéder à toutes les ressources protégées.\n"
                        f"Token valide pendant 60 minutes.",
                        title="🎉 Authentification Complète",
                        border_style="green",
                        box=box.DOUBLE
                    )
                    console.print(success_panel)

                elif response.status_code == 401:
                    print_error("Code TOTP invalide ou expiré")
                elif response.status_code == 423:
                    print_error("Compte verrouillé après trop de tentatives échouées")
                else:
                    print_error(f"Erreur: {response.status_code}")

            except Exception as e:
                progress.stop()
                print_error(f"Erreur: {e}")

    # ========================================
    # SCÉNARIO 2 : SMS
    # ========================================
    elif choice == "2":
        print_step(4, "Envoi d'un code SMS")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Envoi du SMS...", total=None)

            try:
                response = requests.post(
                    f"{BASE_URL}/api/mfa/sms/send",
                    headers={"Authorization": f"Bearer {mfa_pending_token}"}
                )
                progress.stop()

                print_response(response, "Envoi SMS")

                if response.status_code == 200:
                    data = response.json()
                    print_success("SMS envoyé avec succès !")
                    print_info(f"Message ID: {data.get('message_id')}")
                    print_info(f"Expire dans 5 minutes")

                    console.print()
                    sms_code = Prompt.ask("🔢 Code SMS reçu (6 chiffres)")

                    # Vérification du code SMS
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console
                    ) as progress2:
                        task2 = progress2.add_task("Vérification du code SMS...", total=None)

                        response2 = requests.post(
                            f"{BASE_URL}/api/mfa/verify/sms",
                            headers={"Authorization": f"Bearer {mfa_pending_token}"},
                            json={"code": sms_code}
                        )
                        progress2.stop()

                        print_response(response2, "Vérification SMS")

                        if response2.status_code == 200:
                            data2 = response2.json()
                            access_token = data2.get("access_token")
                            print_success("🎉 AUTHENTIFICATION SMS RÉUSSIE !")
                        else:
                            print_error("Code SMS invalide ou expiré")
                else:
                    print_error(f"Échec d'envoi du SMS: {response.status_code}")

            except Exception as e:
                progress.stop()
                print_error(f"Erreur: {e}")

    # ========================================
    # SCÉNARIO 3 : CODE DE RÉCUPÉRATION
    # ========================================
    elif choice == "3":
        print_step(4, "Utilisation d'un code de récupération")

        print_warning("Les codes de récupération sont à usage unique")
        print_info("Format: XXXX-XXXX (ex: ABCD-1234)")
        console.print()

        recovery_code = Prompt.ask("🎫 Code de récupération")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Vérification du code...", total=None)

            try:
                response = requests.post(
                    f"{BASE_URL}/api/mfa/verify/recovery",
                    headers={"Authorization": f"Bearer {mfa_pending_token}"},
                    json={"code": recovery_code}
                )
                progress.stop()

                print_response(response, "Vérification Code de Récupération")

                if response.status_code == 200:
                    data = response.json()
                    access_token = data.get("access_token")
                    remaining = data.get("remaining_codes", 0)

                    print_success("🎉 CODE DE RÉCUPÉRATION VALIDE !")
                    print_warning(f"Codes restants: {remaining}/10")

                    if remaining < 3:
                        print_warning("⚠️  ATTENTION: Moins de 3 codes restants!")
                        print_info("Pensez à régénérer de nouveaux codes")
                else:
                    print_error("Code de récupération invalide ou déjà utilisé")

            except Exception as e:
                progress.stop()
                print_error(f"Erreur: {e}")

    # ========================================
    # SCÉNARIO 4 : ANTI-BRUTEFORCE
    # ========================================
    elif choice == "4":
        print_step(4, "Test de la protection anti-bruteforce")

        print_warning("Ce test va envoyer 10 codes invalides pour déclencher le blocage")

        if not Confirm.ask("Voulez-vous continuer ?"):
            print_info("Test annulé")
            return

        console.print()

        with Progress(console=console) as progress:
            task = progress.add_task("[cyan]Envoi de codes invalides...", total=10)

            for i in range(10):
                try:
                    response = requests.post(
                        f"{BASE_URL}/api/mfa/verify/totp",
                        headers={"Authorization": f"Bearer {mfa_pending_token}"},
                        json={"code": "000000"}
                    )

                    progress.update(task, advance=1)

                    if response.status_code == 423:
                        progress.stop()
                        console.print()
                        print_success("🛡️  PROTECTION ANTI-BRUTEFORCE ACTIVÉE !")
                        print_response(response, f"Blocage détecté à la tentative {i+1}")

                        # Afficher un panel d'information
                        info_panel = Panel(
                            "[bold red]🔒 Compte verrouillé ![/bold red]\n\n"
                            "Le système a détecté des tentatives répétées de connexion.\n"
                            f"Nombre de tentatives: {i+1}/10\n"
                            "Durée de verrouillage: 15 minutes\n\n"
                            "[cyan]Cette protection empêche les attaques par force brute.[/cyan]",
                            title="Protection Anti-Bruteforce",
                            border_style="red",
                            box=box.HEAVY
                        )
                        console.print(info_panel)
                        break

                    time.sleep(0.3)

                except Exception as e:
                    progress.stop()
                    print_error(f"Erreur: {e}")
                    break

    # ========================================
    # RÉCAPITULATIF FINAL
    # ========================================
    console.print()
    console.rule("[bold green]FIN DE LA DÉMONSTRATION[/bold green]", style="green")
    console.print()

    # Tableau récapitulatif
    summary_table = Table(title="Récapitulatif de la session", box=box.DOUBLE, border_style="green")
    summary_table.add_column("Élément", style="cyan", no_wrap=True)
    summary_table.add_column("Valeur", style="green")

    summary_table.add_row("Email utilisateur", email)
    summary_table.add_row("Méthode 2FA utilisée",
                         "TOTP" if choice == "1" else
                         "SMS" if choice == "2" else
                         "Code récupération" if choice == "3" else
                         "Test bruteforce")
    summary_table.add_row("Authentification", "✅ Réussie" if access_token else "❌ Échouée")

    if access_token:
        summary_table.add_row("Token reçu", f"{access_token[:40]}...")
        summary_table.add_row("Validité", "60 minutes")

    console.print(summary_table)

    # Message final
    console.print()
    final_message = Panel(
        "[bold cyan]Merci d'avoir testé le système 2FA de NOVA ![/bold cyan]\n\n"
        "Points clés démontrés:\n"
        "  ✅ Authentification en deux étapes\n"
        "  ✅ Tokens JWT avec expiration\n"
        "  ✅ Protection anti-bruteforce\n"
        "  ✅ Méthodes de secours multiples\n\n"
        "[yellow]Pour plus d'informations, consultez DEMO_2FA_GUIDE.md[/yellow]",
        title="🎉 Démonstration Terminée",
        border_style="blue",
        box=box.DOUBLE
    )
    console.print(final_message)


if __name__ == "__main__":
    try:
        demo_complete_flow()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Démonstration interrompue par l'utilisateur[/yellow]")
    except Exception as e:
        console.print(f"\n\n[red]Erreur inattendue: {e}[/red]")
