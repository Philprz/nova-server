"""
Configuration TLS pour les appels HTTPS vers SAP B1.

SAP_VERIFY est passé tel quel à httpx.AsyncClient(verify=...) :
- Si SAP_CA_BUNDLE_PATH est défini dans .env, c'est le chemin vers le bundle CA
  utilisé pour vérifier le certificat du serveur SAP (recommandé en production).
- Sinon, vaut False — la vérification du certificat est DÉSACTIVÉE (acceptable
  en dev pour les serveurs SAP à certificat auto-signé, dangereux en prod).
"""

import os

SAP_VERIFY = os.getenv("SAP_CA_BUNDLE_PATH") or False
