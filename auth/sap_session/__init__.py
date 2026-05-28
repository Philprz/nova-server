"""Port Python du système de session SAP B1 du projet BILLING.

Architecture en miroir de apps/api/src/{services,session,middleware,routes} :
- sap_auth_service : transport SAP pur (Login/Logout/Ping, extraction cookies)
- store           : état in-memory indexé par UUID, sliding + absolute expiry
- cookie_signing  : HMAC-SHA256 stdlib pour signer/vérifier le cookie pa_session
- require_session : dépendance FastAPI qui valide et glisse l'idle expiry

────────────────────────────────────────────────────────────────────────────
COEXISTENCE AVEC L'AUTH JWT NOVA HISTORIQUE
────────────────────────────────────────────────────────────────────────────

Deux systèmes d'authentification cohabitent dans ce serveur :

1. **JWT NOVA** (historique, propriétaire des routes métier) :
   - Routes : POST/GET /api/auth/{login,refresh,logout,me}
              (voir routes/routes_auth.py)
   - Cookies : `nova_session` (access JWT) + `nova_refresh` (rotation)
   - Dépendance : auth.dependencies.get_current_user
   - Périmètre : protège **toutes** les routes métier NOVA (devis, clients,
     pricing, sap_business, admin, etc. — ~18 routers).
   - Stratégie SAP : valide les credentials au login via auth.sap_validator
     mais **ne conserve pas** le B1SESSION ; chaque service métier ouvre sa
     propre session SAP via services.sap_business_service (singleton serveur).

2. **SAP B1 Session** (ce module, port du projet BILLING) :
   - Routes : POST/GET /api/sapauth/{login,logout,me,keepalive,ping}
              (voir routes/routes_sap_session.py)
   - Cookie : `pa_session` (sessionId UUID signé HMAC-SHA256, B1SESSION
     jamais exposé au front)
   - Dépendance : auth.sap_session.require_session.require_sap_session
   - Périmètre actuel : **uniquement** les 5 endpoints /api/sapauth/*.
     Aucun handler métier NOVA ne dépend de require_sap_session aujourd'hui.

────────────────────────────────────────────────────────────────────────────
STRATÉGIE CIBLE
────────────────────────────────────────────────────────────────────────────

Les deux systèmes restent **durablement coexistants** à ce stade :

- Le JWT NOVA reste le **système principal** pour les routes applicatives :
  il gère le RBAC fin (mailbox permissions, require_role), le refresh sliding,
  l'historique sessions et la majorité de la surface API.

- Le module sap_session apporte une capacité **complémentaire** :
  conserver un B1SESSION SAP côté serveur, ré-injecté de façon transparente
  dans des appels SAP B1 où la session **applicative SAP de l'utilisateur**
  (et non la session technique partagée du service singleton) doit être
  utilisée — par ex. pour respecter la traçabilité utilisateur côté SAP, ou
  pour exposer certaines routes "directes" qui réinjectent le sap_cookie_header
  vers SAP sans passer par le singleton.

Règle de routage **lequel l'emporte** :
- Routes existantes /api/auth/* + toutes routes métier → JWT NOVA (inchangé).
- Routes /api/sapauth/* + tout nouvel endpoint qui doit réinjecter
  explicitement le B1SESSION de l'utilisateur courant → require_sap_session.
- **Ne pas faire dépendre une même route des deux systèmes** : choisir l'un
  ou l'autre selon le besoin. Si une route métier doit accéder à la
  SapSessionContext (B1SESSION user), exposer require_sap_session en
  Depends additionnel, mais garder get_current_user pour le RBAC.

Tant qu'aucune route métier ne dépend de /api/sapauth/*, le module est
isolable : suppression sans régression possible si la stratégie évolue.

B1SESSION n'est **jamais** envoyé au navigateur — c'est la garantie
non négociable de ce module, à préserver en cas d'évolution.
"""
