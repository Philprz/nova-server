Plan d'Action pour Finaliser le POC NOVA Middleware
Priorité 1 : Stabilisation des Fondations (Essentiel)
Fiabiliser la Gestion de la Base de Données avec Alembic (MID-2)
Pourquoi : C'est crucial. Alembic doit être le maître de votre schéma de base de données pour éviter les incohérences et faciliter les évolutions futures.
Actions Concrètes :
Vérifiez l'état actuel : Les tables définies dans db/models.py existent-elles déjà dans votre base PostgreSQL nova_mcp_local ? Sont-elles identiques ?
Scénario A : Les tables n'existent pas ou ne sont pas à jour.
Supprimez le fichier de migration vide existant (alembic/versions/19025397a60c_initial_local_setup.py).
Générez une nouvelle migration : python -m alembic revision --autogenerate -m "create_initial_tables"
Vérifiez le script généré. Il doit contenir les instructions op.create_table(...) pour vos modèles.
Appliquez la migration : python -m alembic upgrade head
Scénario B : Les tables existent déjà et sont conformes aux modèles.
Supprimez le fichier de migration vide existant.
Générez une nouvelle migration (qui sera probablement vide ou reflétera l'état actuel) : python -m alembic revision --autogenerate -m "baseline_existing_schema"
"Tamponnez" cette version pour dire à Alembic que la base est déjà à ce niveau : python -m alembic stamp head
Résultat Attendu : Alembic est synchronisé avec votre base de données et prêt pour les futures migrations.
Clarifier la Stratégie pour RabbitMQ (MID-3)
Pourquoi : Une dépendance (aio-pika) est présente mais non utilisée. Il faut prendre une décision.
Actions Concrètes :
Évaluez le besoin réel : Les fonctionnalités asynchrones actuelles (via asyncio, httpx, subprocess) sont-elles suffisantes pour les objectifs finaux de ce POC ?
Si RabbitMQ est indispensable (pour des tâches de fond complexes, une meilleure résilience, etc.) : Planifiez son intégration (importer aio_pika, développer les producteurs/consommateurs).
Si RabbitMQ n'est pas requis pour ce POC : Documentez cette décision et envisagez de retirer aio-pika de requirements.txt pour simplifier.
Résultat Attendu : Une architecture claire concernant la gestion des tâches asynchrones.
Priorité 2 : Amélioration de la Robustesse et de la Maintenabilité
Mettre à Jour le README.md
Pourquoi : La documentation d'accueil doit être exacte.
Actions Concrètes (je peux vous aider avec ça immédiatement) :
Mettre à jour la section "Équipe de développement" pour refléter que vous êtes le seul responsable (conformément à la mémoire 81d2f609-5898-4452-a57f-2db8479eb4f8).
Après avoir traité le point sur Alembic, vérifiez que les instructions d'installation/démarrage concernant la base de données sont correctes.
Relisez la section "Statut global" et ajustez-la si nécessaire.
Résultat Attendu : Un README.md à jour et fiable.
Renforcer les Tests Unitaires (MID-8)
Pourquoi : Augmenter la confiance dans chaque composant et faciliter les évolutions.
Actions Concrètes :
Identifiez les modules clés qui manquent de tests unitaires (ex: LLMExtractor, ClientValidator, fonctions spécifiques dans sap_mcp.py et salesforce_mcp.py).
Rédigez des tests unitaires pour ces composants, couvrant les cas d'usage principaux et les cas limites.
Optionnel mais recommandé : Adoptez pytest pour une meilleure organisation et exécution de tous vos tests.
Résultat Attendu : Une meilleure couverture de test et une plus grande stabilité du code.
Compléter la Documentation Technique (CONNECT-8, LLM-5)
Pourquoi : Essentiel pour la compréhension à long terme et la maintenance.
Actions Concrètes :
CONNECT-8: Créez un document simple (par ex. dans le dossier docs/) qui liste les principaux champs/objets SAP et Salesforce utilisés, leur mapping éventuel, et leur rôle.
LLM-5: Documentez les prompts clés utilisés avec Claude et la structure des données attendues/reçues.
Résultat Attendu : Une documentation technique minimale mais suffisante pour comprendre les intégrations clés.
Priorité 3 : Finalisation et Perspectives
Homogénéiser la Gestion des Erreurs (MID-7)
Pourquoi : Une gestion d'erreurs cohérente simplifie le débogage et améliore l'expérience utilisateur (même si l'utilisateur est une API).
Actions Concrètes :
Revoyez comment les erreurs sont actuellement gérées dans les différentes parties du middleware.
Standardisez les réponses d'erreur des API et la manière dont les exceptions sont loguées.
Résultat Attendu : Une gestion des erreurs plus robuste et prévisible.
Planifier les Aspects Infrastructure (INFRA-3, INFRA-5, INFRA-6)
Pourquoi : Si le POC doit vivre ou évoluer, ces aspects deviennent importants.
Actions Concrètes (à planifier pour plus tard si le temps manque) :
INFRA-3: Documentez clairement les étapes de déploiement sur le serveur OVH.
INFRA-5 & INFRA-6: Réfléchissez à des stratégies de base pour le monitoring et la sécurité.
Résultat Attendu : Une vision claire des prochaines étapes si le POC passe à une phase plus opérationnelle.