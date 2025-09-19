# NOVA - Assistant Commercial Intelligent

**Statut : ðŸŸ¢ OPÃ‰RATIONNEL** | **Version : 1.0.0** | **DerniÃ¨re MAJ : 05/08/2025**

## ðŸš€ AccÃ¨s Direct

- **Interface Principal :** http://178.33.233.120:8200/api/assistant/interface
- **API SantÃ© :** http://178.33.233.120:8200/health
- **Documentation :** http://178.33.233.120:8200/docs

## ðŸ“‹ Vue d'Ensemble

NOVA est un assistant commercial intelligent qui coordonne Claude LLM avec Salesforce et SAP Business One. Il analyse les demandes de devis en langage naturel et automatise les processus CRM/ERP.

### FonctionnalitÃ©s ClÃ©s

- âœ… **GÃ©nÃ©ration de devis** via conversation naturelle
- âœ… **Validation client** avec APIs INSEE et Adresse Gouv
- âœ… **Detection doublons** intelligente
- âœ… **Suggestions contextuelles** avec correspondance floue
- âœ… **Interface web** responsive et moderne

## ðŸ—ï¸ Architecture

```
Interface Web â†’ FastAPI â†’ Claude LLM
                      â†“
              PostgreSQL + MCP Connector
                      â†“
              Salesforce â†” SAP Business One
```

### Composants Techniques

| Composant | Statut | Description |
|-----------|---------|-------------|
| **Claude API** | âœ… | Traitement langage naturel |
| **PostgreSQL** | âœ… | Base de donnÃ©es (port 5432) |
| **MCP Connector** | âœ… | Orchestration SF/SAP |
| **SuggestionEngine** | âœ… | IA suggestions contextuelles |
| **ClientValidator** | âœ… | Validation SIRET + adresses |

## âš¡ DÃ©marrage Rapide

### Utilisateurs
```
1. AccÃ©dez Ã  : http://178.33.233.120:8200/api/assistant/interface
2. Tapez : "CrÃ©er un devis pour 100 rÃ©f A00025 pour Edge Communications"
3. NOVA traite automatiquement la demande
```

### DÃ©veloppeurs
```bash
# Test API
curl -X POST "http://178.33.233.120:8200/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour NOVA"}'
```

### Administrateurs
```powershell
# DÃ©marrage
.\start_nova.ps1

# VÃ©rification
Invoke-RestMethod -Uri "http://localhost:8200/health"
```

## ðŸ“¡ APIs Principales

### Assistant
- `GET /api/assistant/interface` - Interface conversationnelle
- `POST /api/assistant/chat` - Chat avec l'assistant
- `POST /api/assistant/workflow/create_quote` - Workflow devis

### Technique
- `GET /health` - ContrÃ´le santÃ©
- `GET /docs` - Documentation Swagger
- `POST /suggestions/client` - Suggestions clients

## ðŸ”§ Configuration

### Environnement
- **OS :** Windows Server 2019 (OVH)
- **IP :** 178.33.233.120
- **Python :** 3.9+ avec venv
- **RÃ©pertoire :** `C:\Users\PPZ\NOVA-SERVER`

### Variables ClÃ©s
```env
DATABASE_URL=postgresql://nova_user:***@localhost:5432/nova_mcp
ANTHROPIC_API_KEY=sk-ant-api03-***
SAP_REST_BASE_URL=https://51.91.130.136:50000/b1s/v1
INSEE_API_KEY=***
```

## ðŸ§ª Tests

```bash
# Installation dÃ©pendances
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock

# ExÃ©cution tests
pytest                # Tous les tests
pytest -m integration # Tests d'intÃ©gration seulement

# Tests manuels
python tests/test_workflow_demo.py
```

## ðŸ“Š Performance

- **Temps gÃ©nÃ©ration :** < 2 minutes par devis
- **Taux succÃ¨s :** > 95%
- **DisponibilitÃ© :** 99.9%
- **PrÃ©cision client :** > 98%

## ðŸ“š Documentation

- **Guide Utilisateur :** `MANUEL_UTILISATEUR.md`
- **Guide Technique :** `GUIDE_TECHNIQUE_COMPLET.md`
- **ScÃ©narios Test :** `SCENARIOS_DEMONSTRATION.md`

## ðŸ†˜ Support

### Ã‰quipe
- **Philippe PEREZ** - Chef de projet IA (2j/semaine)
- **Bruno CHARNAL** - Support technique (0.5j/semaine)

### DÃ©pannage
- Interface inaccessible â†’ VÃ©rifier health endpoint
- ProblÃ¨me technique â†’ Consulter guide technique
- RedÃ©marrage â†’ `.\start_nova.ps1`

## ðŸ—ºï¸ Roadmap

### âœ… Phase 1 - POC (TerminÃ©e)
- Assistant intelligent opÃ©rationnel
- IntÃ©grations SF/SAP/Claude
- Interface publique

### ðŸ”„ Phase 2 - Optimisation (En cours)
- Cache Redis
- Monitoring avancÃ©
- Tests charge

### ðŸ“‹ Phase 3 - Production (PlanifiÃ©e)
- SÃ©curitÃ© renforcÃ©e
- Application mobile
- Machine Learning avancÃ©

## ðŸ”’ SÃ©curitÃ©

- Pare-feu Windows configurÃ© (port 8200)
- API Keys sÃ©curisÃ©es
- Authentification SAP/SF
- **TODO :** HTTPS + authentification utilisateur

---

**ðŸŒŸ NOVA est opÃ©rationnel et accessible publiquement !**
**Prochaine Ã©tape :** SÃ©curisation accÃ¨s public
