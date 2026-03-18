# NOVA — Architecture Auth / RBAC / Multi-tenant

## Principe général

| Couche | Rôle |
|---|---|
| **SAP B1** | Source d'**authentification** — vérifie l'identité |
| **NOVA** | Source d'**autorisation** — gère les rôles, sociétés, boîtes mail |

NOVA ne stocke jamais le mot de passe SAP. Il valide les credentials contre SAP à chaque login, puis émet son propre JWT.

---

## Flux d'authentification

```
POST /api/auth/login  {sap_company_db, sap_username, sap_password}
          │
          ▼
1. Société connue dans nova_auth.db ?  ──NON──► 401
          │ OUI
          ▼
2. Utilisateur NOVA enregistré ?        ──NON──► 401
          │ OUI
          ▼
3. POST SAP /Login (httpx, stateless)   ──NON──► 401
          │ 200 OK — session SAP discardée
          ▼
4. Charger mailbox_ids de l'utilisateur
          │
          ▼
5. Émettre JWT NOVA (HS256, 60 min)
   + Refresh token opaque (7 jours, haché SHA-256 en DB)
          │
          ▼
200  {access_token, refresh_token, token_type:"bearer", expires_in:3600}
```

---

## JWT Access Token

```json
{
  "sub":         "1",
  "sap_user":    "manager",
  "society_id":  1,
  "sap_company": "RON_20260109",
  "role":        "ADMIN",
  "mailbox_ids": [1],
  "iat":         ...,
  "exp":         ...,
  "jti":         "uuid4"
}
```

**Algorithme** : HS256
**Secret** : `NOVA_JWT_SECRET` dans `.env`
**Durée** : `NOVA_JWT_ACCESS_TTL_MINUTES` (défaut 60 min)

---

## Modèle RBAC

### Rôles

| Rôle | Droits |
|---|---|
| `ADMIN` | Accès complet — toutes routes, bypass mailbox check, CRUD admin |
| `MANAGER` | Peut approuver/rejeter des décisions, accès à ses boîtes |
| `ADV` | Accès en lecture/traitement sur ses boîtes assignées |

### Hiérarchie des dépendances FastAPI

```python
require_role("ADMIN")           # ADMIN seulement
require_role("ADMIN","MANAGER") # ADMIN ou MANAGER
get_current_user                # n'importe quel rôle authentifié
require_mailbox_access("mailbox_id")  # vérifie user_mailbox_permissions (ADMIN bypass)
```

---

## Modèle multi-société

```
Society (tenant logique)
    │── sap_company_db  → identifie la base SAP
    │── sap_base_url    → URL de l'API SAP du client
    │
    ├── nova_users (1..N)
    │       │── sap_username  → login SAP
    │       │── role          → ADMIN | MANAGER | ADV
    │       └── permissions   → boîtes autorisées (via user_mailbox_permissions)
    │
    └── mailboxes (1..N)
            │── address       → adresse email
            └── ms_tenant_id  → tenant Azure AD de la boîte
```

Chaque société a sa propre configuration SAP (`sap_company_db`, `sap_base_url`). L'isolation est assurée par `society_id` sur toutes les tables.

---

## Base de données — nova_auth.db

Fichier : `data/nova_auth.db` (créé automatiquement au démarrage).

```
societies                   → tenants logiques
nova_users                  → utilisateurs NOVA (adossés à SAP)
mailboxes                   → boîtes mail gérées par NOVA
user_mailbox_permissions    → mapping user ↔ boîte (can_read, can_write)
refresh_tokens              → tokens de renouvellement (hachés SHA-256)
```

---

## Endpoints

### Auth publics
| Méthode | Route | Description |
|---|---|---|
| POST | `/api/auth/login` | SAP credentials → JWT NOVA |
| POST | `/api/auth/refresh` | Rotation refresh token |
| POST | `/api/auth/logout` | Révocation refresh token |
| GET  | `/api/auth/me` | Profil utilisateur courant |

### Admin (ADMIN uniquement)
| Méthode | Route |
|---|---|
| GET/POST | `/api/admin/societies` |
| PATCH | `/api/admin/societies/{id}` |
| GET/POST | `/api/admin/users` |
| PATCH/DELETE | `/api/admin/users/{id}` |
| GET/POST | `/api/admin/mailboxes` |
| PATCH | `/api/admin/mailboxes/{id}` |
| GET/POST | `/api/admin/users/{id}/permissions` |
| DELETE | `/api/admin/users/{id}/permissions/{mailbox_id}` |

---

## Rollout progressif

Les routes existantes ne sont **pas touchées** tant qu'on n'y ajoute pas de `Depends`.

```python
# Phase 1 — routes sensibles
@router.post("/validations/{id}/approve")
async def approve(user = Depends(require_role("ADMIN", "MANAGER"))):

# Phase 2 — routes mail/graph
@router.get("/emails")
async def list_emails(user = Depends(require_mailbox_access("mailbox_id"))):

# Phase 3 — reste
@router.get("/items")
async def items(user: AuthenticatedUser = Depends(get_current_user)):
```

---

## Initialisation RONDOT

```bash
.venv\Scripts\python.exe scripts/seed_rondot.py
```

Crée : société RONDOT SAS, user `manager` (ADMIN), boîte `devis@rondot-poc.itspirit.ovh`.

---

## Points d'extension futurs

- **Rate limiting** `/api/auth/login` : compteur IP en mémoire (pas de Redis nécessaire)
- **Multi-SAP** : chaque société a sa propre `sap_base_url` en DB — prêt
- **MS Graph multi-tenant** : `mailboxes.ms_tenant_id` prévu pour configurer Graph par société
- **Rotation `NOVA_JWT_SECRET`** : changer la variable force tous les users à se re-logger
- **Audit log** : logger toutes les actions admin dans une table `audit_log`
