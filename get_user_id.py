"""
Script pour récupérer le User ID Microsoft 365
Nécessaire pour configurer le webhook
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.graph_service import get_graph_service


async def get_user_id():
    """Récupère le User ID de l'utilisateur configuré."""
    print("=" * 80)
    print("RÉCUPÉRATION USER ID MICROSOFT 365")
    print("=" * 80)
    print()

    graph_service = get_graph_service()

    try:
        # Récupérer le token d'accès
        access_token = await graph_service.get_access_token()
        print("[OK] Access token obtained")
        print()

        # Appeler Microsoft Graph pour lister les utilisateurs
        import httpx

        async with httpx.AsyncClient() as client:
            # Essayer d'abord avec /me (si auth déléguée)
            try:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )

                if response.status_code == 200:
                    user = response.json()
                    print("[OK] User found via /me endpoint")
                    print()
                    print(f"User ID: {user.get('id')}")
                    print(f"Email: {user.get('userPrincipalName')}")
                    print(f"Display Name: {user.get('displayName')}")
                    print()
                    print("Add to .env:")
                    print(f"GRAPH_USER_ID={user.get('id')}")
                    print()
                    return user.get('id')

            except Exception as e:
                print("[INFO] /me endpoint not available (application auth)")
                print()

            # Si /me échoue, lister les utilisateurs
            print("[INFO] Listing users (application auth)...")
            response = await client.get(
                "https://graph.microsoft.com/v1.0/users",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code != 200:
                error = response.json()
                raise Exception(f"Failed to list users: {error}")

            data = response.json()
            users = data.get('value', [])

            if not users:
                print("[ERREUR] No users found")
                return None

            print(f"[OK] Found {len(users)} user(s)")
            print()
            print("=" * 80)
            print("USERS")
            print("=" * 80)

            for idx, user in enumerate(users, 1):
                user_id = user.get('id')
                email = user.get('userPrincipalName')
                name = user.get('displayName')

                print(f"{idx}. {name} ({email})")
                print(f"   User ID: {user_id}")
                print()

            # Si un seul utilisateur, le retourner
            if len(users) == 1:
                user = users[0]
                print("[INFO] Only one user found, using it")
                print()
                print("Add to .env:")
                print(f"GRAPH_USER_ID={user.get('id')}")
                print()
                return user.get('id')

            # Sinon, demander à l'utilisateur de choisir
            print("Multiple users found. Please add the correct User ID to .env:")
            print("GRAPH_USER_ID=<user-id>")
            print()

            return None

    except Exception as e:
        print(f"[ERREUR] {e}")
        import traceback
        traceback.print_exc()
        print()
        return None


if __name__ == "__main__":
    asyncio.run(get_user_id())
