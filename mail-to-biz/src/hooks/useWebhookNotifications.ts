/**
 * Hook pour notifications toast des emails traités automatiquement
 *
 * Fonctionnalités:
 * - Polling périodique des nouvelles analyses
 * - Toast quand email traité en background
 * - Évite les duplications avec Set des IDs notifiés
 * - Auto-désactivation si utilisateur inactif
 */

import { useEffect, useRef, useState } from 'react';
import { getGraphEmailAnalysis } from '@/lib/graphApi';
import { notifyQuoteProcessed, notifyEmailAnalyzed, notifyPricingCalculated } from '@/lib/notifications';

interface WebhookNotificationOptions {
  /**
   * Intervalle de vérification en millisecondes
   * @default 10000 (10 secondes)
   */
  pollInterval?: number;

  /**
   * Activer les notifications
   * @default true
   */
  enabled?: boolean;

  /**
   * Liste des emails à surveiller
   * Si vide, ne surveille rien
   */
  emailIds?: string[];
}

interface NotificationState {
  notifiedIds: Set<string>;
  lastCheck: number;
}

export function useWebhookNotifications(options: WebhookNotificationOptions = {}) {
  const {
    pollInterval = 10000, // 10 secondes par défaut
    enabled = true,
    emailIds = []
  } = options;

  const [state, setState] = useState<NotificationState>({
    notifiedIds: new Set(),
    lastCheck: Date.now()
  });

  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Ne rien faire si désactivé ou pas d'emails à surveiller
    if (!enabled || emailIds.length === 0) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    // Fonction de vérification
    const checkForNewAnalyses = async () => {
      try {
        // Vérifier chaque email non encore notifié
        for (const emailId of emailIds) {
          // Skip si déjà notifié
          if (state.notifiedIds.has(emailId)) {
            continue;
          }

          // Vérifier si analyse existe
          const result = await getGraphEmailAnalysis(emailId);

          if (result.success && result.data) {
            const analysis = result.data;

            // Marquer comme notifié
            setState(prev => ({
              ...prev,
              notifiedIds: new Set(prev.notifiedIds).add(emailId),
              lastCheck: Date.now()
            }));

            // Afficher toast selon type
            if (analysis.is_quote_request) {
              // Toast succès pour devis
              notifyQuoteProcessed({
                clientName: analysis.client_match?.matched_client?.CardName,
                productCount: analysis.products?.length || 0,
                emailSubject: analysis.subject,
                caseType: analysis.pricing_decisions?.[0]?.case_type
              });

              // Si pricing calculé, notification supplémentaire
              if (analysis.pricing_decisions && analysis.pricing_decisions.length > 0) {
                const firstDecision = analysis.pricing_decisions[0];
                notifyPricingCalculated({
                  caseType: firstDecision.case_type,
                  productCount: analysis.pricing_decisions.length,
                  totalHT: analysis.pricing_decisions.reduce(
                    (sum, d) => sum + (d.calculated_price || 0),
                    0
                  )
                });
              }
            } else {
              // Toast info pour non-devis
              notifyEmailAnalyzed({
                emailSubject: analysis.subject,
                classification: analysis.classification
              });
            }
          }
        }
      } catch (error) {
        console.error('[WebhookNotifications] Error checking analyses:', error);
        // Ne pas afficher de toast d'erreur pour éviter le spam
      }
    };

    // Vérification initiale après 2 secondes
    const initialTimeout = setTimeout(checkForNewAnalyses, 2000);

    // Polling périodique
    intervalRef.current = setInterval(checkForNewAnalyses, pollInterval);

    // Cleanup
    return () => {
      clearTimeout(initialTimeout);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [enabled, emailIds.join(','), pollInterval]);

  return {
    notifiedCount: state.notifiedIds.size,
    lastCheck: state.lastCheck,
    reset: () => setState({ notifiedIds: new Set(), lastCheck: Date.now() })
  };
}
