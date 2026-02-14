# Système de Notifications Toast - Mail-to-Biz

## 🎯 Objectif

Notifier l'utilisateur en temps réel quand des emails sont traités automatiquement en background via le webhook Microsoft Graph.

## ✨ Fonctionnalités Implémentées

### 1. Notifications Toast Automatiques

Les utilisateurs reçoivent des notifications toast lorsque :

- ✅ **Email devis traité** - Toast succès avec détails (client, produits)
- ✅ **Pricing calculé** - Toast avec CAS appliqué et montant total
- ✅ **Email analysé** - Toast info pour emails non-devis
- ✅ **Validation requise** - Toast warning pour CAS 2 & 4
- ✅ **Produit/Client créé** - Toast succès création dans SAP
- ✅ **Erreur traitement** - Toast erreur avec option réessayer

### 2. Badge de Statut Webhook

Badge animé dans le header affichant :

- 📊 **Nombre d'emails traités** automatiquement
- ⚡ **Animation pulse** quand actif
- 🕒 **Dernière vérification** (tooltip)
- ✨ **Auto-masquage** en mode démo

### 3. Hook de Notification Intelligent

`useWebhookNotifications` :

- 🔄 **Polling périodique** (10 secondes par défaut)
- 🎯 **Détection nouveaux traitements** (évite duplications)
- 📧 **Surveillance ciblée** (emails devis uniquement)
- 🛑 **Auto-désactivation** si utilisateur inactif

## 📁 Fichiers Créés

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `src/hooks/useWebhookNotifications.ts` | 130 | Hook polling & notifications |
| `src/lib/notifications.ts` | 220 | Fonctions toast prédéfinies |
| `src/components/WebhookStatusBadge.tsx` | 55 | Badge statut header |

**Total** : ~405 lignes

## 📁 Fichiers Modifiés

| Fichier | Modifications |
|---------|---------------|
| `src/pages/Index.tsx` | Import hook + badge (10 lignes) |
| `src/App.tsx` | Déjà configuré (Sonner) |

## 🎨 Exemples de Notifications

### Toast Email Devis Traité

```
✅ Email devis traité automatiquement
👤 SAVERGLASS • 📦 28 produits • 💰 CAS_1_HC
                                [👁️ Voir]
```

**Durée** : 6 secondes
**Action** : Bouton "Voir" pour naviguer vers la synthèse

### Toast Pricing Calculé

```
💰 Pricing calculé automatiquement
📊 Historique Client • 28 produit(s) • 12,450.00 € HT
```

**Durée** : 5 secondes

### Toast Validation Requise

```
⚠️ Validation commerciale requise
Variation prix fournisseur importante (+14.00%)
                                [✅ Valider]
```

**Durée** : 8 secondes
**Action** : Bouton "Valider" pour naviguer vers page validation

### Toast Webhook Expirant

```
⚠️ Webhook expirant bientôt
Le webhook Microsoft Graph expire dans 6 heures
                                [🔧 Gérer]
```

**Durée** : 10 secondes
**Action** : Bouton "Gérer" → Page gestion webhooks

## 🔧 Configuration

### Polling Interval

Par défaut : **10 secondes**

```typescript
useWebhookNotifications({
  pollInterval: 10000, // Personnalisable
  enabled: !isDemoMode && currentView === 'inbox',
  emailIds: quotes.map(q => q.email.id)
});
```

### Désactivation

Les notifications sont automatiquement désactivées :

- ❌ En mode **Démo**
- ❌ Hors de la vue **Inbox**
- ❌ Si **aucun email** à surveiller

## 🎯 Workflow Utilisateur

```
1. Utilisateur sur page Inbox (mode Live)
   ↓
2. Hook démarre polling (10s)
   ↓
3. Email traité en background (webhook)
   ↓
4. Hook détecte analyse complétée
   ↓
5. Toast apparaît automatiquement
   ├─ Succès : Email devis traité
   ├─ Info : Email analysé (non-devis)
   └─ Warning : Validation requise
   ↓
6. Badge mis à jour (compteur +1)
   ↓
7. Utilisateur clique "Voir" (optionnel)
   └─> Navigation vers synthèse
```

## 📊 Types de Toast

| Type | Événement | Durée | Action |
|------|-----------|-------|--------|
| **Success** | Email devis traité | 6s | Voir synthèse |
| **Success** | Pricing calculé | 5s | - |
| **Success** | Produit/Client créé | 5s | - |
| **Info** | Email analysé (non-devis) | 4s | - |
| **Warning** | Validation requise | 8s | Valider |
| **Warning** | Webhook expirant | 10s | Gérer |
| **Error** | Erreur traitement | 5s | Réessayer |
| **Loading** | Traitement en cours | ∞ | - |

## 🔔 API Notifications

### Fonctions Disponibles

```typescript
import {
  notifyQuoteProcessed,      // Email devis traité
  notifyEmailAnalyzed,        // Email non-devis
  notifyPricingCalculated,    // Pricing calculé
  notifyValidationRequired,   // Validation requise
  notifyWebhookExpiring,      // Webhook expire bientôt
  notifyProductCreated,       // Produit créé SAP
  notifyClientCreated,        // Client créé SAP
  notifySyncSuccess,          // Sync réussie
  notifyProcessingError,      // Erreur traitement
  notifyLoading,              // Toast chargement
  dismissToast,               // Fermer toast spécifique
  dismissAllToasts            // Fermer tous
} from '@/lib/notifications';
```

### Exemple d'Utilisation

```typescript
// Toast email devis traité
notifyQuoteProcessed({
  clientName: 'SAVERGLASS',
  productCount: 28,
  emailSubject: 'Demande devis 2026',
  caseType: 'CAS_1_HC'
});

// Toast pricing calculé
notifyPricingCalculated({
  caseType: 'CAS_1_HC',
  productCount: 28,
  totalHT: 12450.00
});

// Toast validation requise
notifyValidationRequired({
  reason: 'Variation prix fournisseur importante (+14%)',
  priority: 'HIGH'
});
```

## 🎨 Personnalisation Toast

### Couleurs (via shadcn-ui)

Les toasts utilisent le thème shadcn :

- **Success** : `bg-green-500/10 border-green-500/20`
- **Info** : `bg-blue-500/10 border-blue-500/20`
- **Warning** : `bg-orange-500/10 border-orange-500/20`
- **Error** : `bg-red-500/10 border-red-500/20`

### Positions

Par défaut : **Bottom-right**

Modifiable dans `src/components/ui/sonner.tsx` :

```typescript
<Toaster
  position="bottom-right" // top-left, top-right, bottom-left, bottom-right
  theme="system"
  richColors
/>
```

## 🔍 Éviter les Duplications

Le hook utilise un **Set des IDs notifiés** :

```typescript
const [state, setState] = useState<NotificationState>({
  notifiedIds: new Set(),  // ← Évite duplications
  lastCheck: Date.now()
});

// Vérification avant notification
if (state.notifiedIds.has(emailId)) {
  continue; // Skip déjà notifié
}

// Marquer comme notifié après toast
setState(prev => ({
  ...prev,
  notifiedIds: new Set(prev.notifiedIds).add(emailId)
}));
```

## ⚡ Performance

### Optimisations

1. **Polling intelligent** : Désactivé si pas nécessaire
2. **Cache IDs** : Évite requêtes API inutiles
3. **Throttling** : Max 1 toast par email
4. **Cleanup** : Arrêt automatique polling au unmount

### Charge Réseau

- **Polling** : 10 secondes → ~6 requêtes/min
- **Par email** : GET `/api/graph/emails/{id}/analysis`
- **Taille réponse** : ~2-5 KB par requête
- **Charge totale** : ~300-900 KB/min (acceptable)

## 🧪 Test Manuel

### 1. Démarrer NOVA

```bash
python main.py
```

### 2. Ouvrir Mail-to-Biz

```
http://localhost:8001/mail-to-biz
```

### 3. Passer en Mode Live

- Sélectionner compte
- Cliquer "Passer en Live"

### 4. Observer Notifications

- Badge webhook affiche "0 traité"
- Envoyer email test à `devis@rondot-poc.itspirit.ovh`
- Attendre ~30 secondes (webhook + polling)
- Toast apparaît automatiquement
- Badge passe à "1 traité"

### 5. Vérifier Tooltip Badge

- Hover sur badge webhook
- Tooltip affiche :
  - "Traitement automatique actif"
  - "X email(s) traité(s) en background"
  - "Dernière vérification il y a X secondes"

## 🐛 Dépannage

### Toast ne s'affiche pas

**Causes possibles** :

1. Mode **Démo** actif → Passer en **Live**
2. Vue != **Inbox** → Naviguer vers Inbox
3. Aucun email devis → Envoyer email test
4. Polling désactivé → Vérifier console erreurs

**Solution** :

```bash
# Ouvrir DevTools Console (F12)
# Vérifier logs hook
[WebhookNotifications] Checking for new analyses...
```

### Badge ne s'affiche pas

**Cause** : `isActive=false`

**Solution** :

```typescript
// Vérifier conditions
isActive={!isDemoMode && currentView === 'inbox'}
```

### Duplications de toast

**Cause** : State `notifiedIds` réinitialisé

**Solution** : Hook conserve state entre re-renders (useState)

## 📈 Métriques Disponibles

Le hook expose 3 métriques :

```typescript
const { notifiedCount, lastCheck, reset } = useWebhookNotifications();

// notifiedCount : Nombre total d'emails notifiés
// lastCheck : Timestamp dernière vérification
// reset : Fonction pour réinitialiser compteur
```

### Utilisation Métriques

```typescript
// Afficher compteur
<span>{notifiedCount} email(s) traité(s)</span>

// Afficher dernière vérif
<span>Dernière vérif: {formatDistanceToNow(lastCheck)}</span>

// Réinitialiser compteur (ex: fin de journée)
<Button onClick={reset}>Réinitialiser</Button>
```

## 🔮 Améliorations Futures

### 1. Notifications Navigateur (Web Notifications API)

```typescript
if ('Notification' in window && Notification.permission === 'granted') {
  new Notification('Email traité', {
    body: 'SAVERGLASS - 28 produits',
    icon: '/icon.png'
  });
}
```

### 2. Sons de Notification

```typescript
const audio = new Audio('/notification.mp3');
audio.play();
```

### 3. Groupement de Toast

```typescript
// Au lieu de 10 toasts séparés
toast.success(`${count} emails traités automatiquement`);
```

### 4. Persistance Historique

```typescript
// Sauvegarder historique en localStorage
localStorage.setItem('notification-history', JSON.stringify(history));
```

### 5. Filtres Notifications

```typescript
// Préférences utilisateur
const [preferences, setPreferences] = useState({
  enableQuoteNotifications: true,
  enablePricingNotifications: true,
  enableValidationNotifications: true
});
```

## 📚 Dépendances

- **sonner** : ^1.7.4 (déjà installé)
- **date-fns** : ^3.6.0 (déjà installé)
- **lucide-react** : ^0.462.0 (déjà installé)

Aucune nouvelle dépendance requise ✅

## ✅ Checklist de Vérification

- [x] Hook `useWebhookNotifications` créé
- [x] Fonctions toast prédéfinies créées
- [x] Badge statut webhook créé
- [x] Intégration dans Index.tsx
- [x] Build frontend réussi
- [x] Aucune erreur TypeScript
- [x] Documentation complète
- [x] Tests manuels prévus

---

**Version** : 2.6.0
**Date** : 13/02/2026
**Auteur** : Philippe PEREZ (ITSpirit)
**Temps d'implémentation** : ~30 minutes
