# Décision d'Architecture : RabbitMQ pour le POC NOVA

## 📋 Contexte
- **Date** : 2025-06-03
- **Version** : POC NOVA LLM-Salesforce-SAP
- **Durée du projet** : 10 semaines
- **Ressources** : 2 développeurs à temps partiel

## 🎯 Question Évaluée
Faut-il utiliser RabbitMQ (aio-pika) pour le messaging asynchrone dans le POC ?

## 📊 Analyse des Performances Actuelles

### Métriques Mesurées
- **Workflow simple** : 1,09s de bout en bout
- **Charge concurrente (5 requêtes)** : 1,10s total
- **Efficacité du parallélisme** : ~99% (excellent)

### Architecture Actuelle
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   FastAPI   │───▶│ DevisWorkflow│───▶│  MCP Servers│
│             │    │   (asyncio)  │    │ (subprocess)│
└─────────────┘    └──────────────┘    └─────────────┘
                           │
                           ▼
                   ┌──────────────┐
                   │httpx.AsyncClient│
                   │ Claude/SF/SAP  │
                   └──────────────┘
```

## 🏆 Décision : **NON RECOMMANDÉ**

### Score d'Évaluation : 0/6

#### ✅ Arguments CONTRE RabbitMQ
1. **Performances suffisantes** : 1,09s < 10s (seuil acceptable)
2. **Complexité non justifiée** : Installation + configuration + maintenance
3. **Scope POC** : Mono-utilisateur, tolérance aux échecs acceptable
4. **Ressources limitées** : Temps mieux investi dans les fonctionnalités métier
5. **Infrastructure** : Éviter la dépendance à un service externe

#### ⚠️ Bénéfices RabbitMQ (non critiques pour POC)
- **Reliability** : Persistance (POC peut tolérer quelques échecs)
- **Scalability** : Distribution (POC mono-utilisateur)
- **Monitoring** : Queues avancées (besoins simples dans POC)

## 📋 Actions Appliquées

### 1. Nettoyage des Dépendances
```bash
# Avant
aio-pika>=3.0.0

# Après (supprimé)
# SUPPRIMÉ : aio-pika (RabbitMQ non requis pour le POC)
```

### 2. Conservation de l'Architecture Async Actuelle
- ✅ **httpx.AsyncClient** pour les appels HTTP
- ✅ **asyncio** pour l'orchestration
- ✅ **subprocess** pour la communication MCP
- ✅ **FastAPI** pour l'API REST

## 🔮 Recommandations Futures

### Pour la Version Production
Si les métriques suivantes sont atteintes :
- **Volume** : >100 demandes/minute
- **Complexité** : Workflows multi-étapes avec retry
- **Fiabilité** : Tolérance zéro aux pertes de données
- **Monitoring** : Observabilité avancée requise

**Alors** : Réévaluer l'implémentation de RabbitMQ

### Alternatives à Considérer
1. **Redis + Celery** : Plus simple que RabbitMQ
2. **AWS SQS/Azure Service Bus** : Solutions cloud managées
3. **Kafka** : Si besoins de streaming de données

## 📈 Métriques de Surveillance

### Seuils de Réévaluation
- **Temps de traitement** : >10s par workflow
- **Taux d'échec** : >5% des demandes
- **Charge concurrente** : >20 utilisateurs simultanés
- **Complexité workflow** : >10 étapes séquentielles

### KPIs à Monitorer
```python
# Métriques clés à suivre
workflow_processing_time = 1.09  # secondes
concurrent_efficiency = 0.99     # ratio
error_rate = 0.01               # pourcentage
user_satisfaction = 0.95        # score
```

## ✅ Validation de la Décision

Cette décision d'architecture est validée par :
- ✅ **Analyse quantitative** des performances
- ✅ **Évaluation cost/benefit** pour le scope POC
- ✅ **Contraintes temporelles** du projet (10 semaines)
- ✅ **Simplicité opérationnelle** (moins de dépendances)

---

**Auteur** : Équipe NOVA POC  
**Validé par** : Philippe PEREZ  
**Prochaine révision** : Fin de POC ou si métriques dégradées