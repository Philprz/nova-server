/**
 * Système de notifications toast personnalisées
 *
 * Fonctions prédéfinies pour différents événements
 */

import { toast } from 'sonner';

/**
 * Notification quand email devis est traité automatiquement
 */
export function notifyQuoteProcessed(data: {
  clientName?: string;
  productCount: number;
  emailSubject?: string;
  caseType?: string;
}) {
  const { clientName, productCount, emailSubject, caseType } = data;

  const clientInfo = clientName || 'Client inconnu';
  const subject = emailSubject ? ` - ${emailSubject}` : '';

  const description = [
    `👤 ${clientInfo}`,
    `📦 ${productCount} produit${productCount > 1 ? 's' : ''}`,
    caseType && `💰 ${caseType}`
  ].filter(Boolean).join(' • ');

  toast.success('✅ Email devis traité automatiquement', {
    description,
    duration: 6000,
    action: {
      label: '👁️ Voir',
      onClick: () => {
        // Le clic sera géré par le composant parent
        console.log('[Toast] Voir synthèse demandé');
      }
    }
  });
}

/**
 * Notification email non-devis
 */
export function notifyEmailAnalyzed(data: {
  emailSubject?: string;
  classification?: string;
}) {
  const { emailSubject, classification } = data;

  toast.info('📧 Email analysé', {
    description: `${classification || 'Non-devis'}${emailSubject ? ` - ${emailSubject.slice(0, 40)}...` : ''}`,
    duration: 4000
  });
}

/**
 * Notification erreur traitement
 */
export function notifyProcessingError(error: string) {
  toast.error('❌ Erreur de traitement', {
    description: error,
    duration: 5000,
    action: {
      label: '🔄 Réessayer',
      onClick: () => {
        window.location.reload();
      }
    }
  });
}

/**
 * Notification webhook expirant bientôt
 */
export function notifyWebhookExpiring(expiresIn: string) {
  toast.warning('⚠️ Webhook expirant bientôt', {
    description: `Le webhook Microsoft Graph expire ${expiresIn}`,
    duration: 10000,
    action: {
      label: '🔧 Gérer',
      onClick: () => {
        window.location.href = '/mail-to-biz/webhooks';
      }
    }
  });
}

/**
 * Notification pricing calculé
 */
export function notifyPricingCalculated(data: {
  caseType: string;
  productCount: number;
  totalHT?: number;
}) {
  const { caseType, productCount, totalHT } = data;

  const caseLabels: Record<string, string> = {
    'CAS_1_HC': '📊 Historique Client',
    'CAS_2_HCM': '⚠️ Prix Modifié',
    'CAS_3_HA': '📈 Historique Autres',
    'CAS_4_NP': '🆕 Nouveau Produit'
  };

  const caseLabel = caseLabels[caseType] || caseType;

  toast.success('💰 Pricing calculé automatiquement', {
    description: `${caseLabel} • ${productCount} produit(s)${totalHT ? ` • ${totalHT.toFixed(2)} € HT` : ''}`,
    duration: 5000
  });
}

/**
 * Notification validation requise
 */
export function notifyValidationRequired(data: {
  reason: string;
  priority: 'URGENT' | 'HIGH' | 'MEDIUM' | 'LOW';
}) {
  const { reason, priority } = data;

  const priorityEmojis = {
    URGENT: '🚨',
    HIGH: '⚠️',
    MEDIUM: '🔔',
    LOW: 'ℹ️'
  };

  const emoji = priorityEmojis[priority];

  toast.warning(`${emoji} Validation commerciale requise`, {
    description: reason,
    duration: 8000,
    action: {
      label: '✅ Valider',
      onClick: () => {
        // Navigation vers page validation
        console.log('[Toast] Navigation validation');
      }
    }
  });
}

/**
 * Notification produit créé dans SAP
 */
export function notifyProductCreated(data: {
  itemCode: string;
  itemName: string;
}) {
  const { itemCode, itemName } = data;

  toast.success('🎉 Produit créé dans SAP', {
    description: `${itemCode} - ${itemName}`,
    duration: 5000
  });
}

/**
 * Notification client créé dans SAP
 */
export function notifyClientCreated(data: {
  cardCode: string;
  cardName: string;
}) {
  const { cardCode, cardName } = data;

  toast.success('🎉 Client créé dans SAP', {
    description: `${cardCode} - ${cardName}`,
    duration: 5000
  });
}

/**
 * Notification succès synchronisation
 */
export function notifySyncSuccess(itemsSynced: number) {
  toast.success('✅ Synchronisation réussie', {
    description: `${itemsSynced} élément(s) synchronisé(s)`,
    duration: 4000
  });
}

/**
 * Notification chargement
 */
export function notifyLoading(message: string) {
  return toast.loading(message, {
    duration: Infinity // Reste jusqu'à dismiss manuel
  });
}

/**
 * Dismiss un toast spécifique
 */
export function dismissToast(toastId: string | number) {
  toast.dismiss(toastId);
}

/**
 * Dismiss tous les toasts
 */
export function dismissAllToasts() {
  toast.dismiss();
}
