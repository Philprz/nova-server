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
   * Liste des emails à surveiller avec leurs métadonnées
   * Si vide, ne surveille rien
   */
  emails?: Array<{ id: string; subject?: string; clientName?: string }>;

  /**
   * Callback déclenché quand l'utilisateur clique "Voir" sur le toast
   */
  onViewEmail?: (emailId: string) => void;
}

interface NotificationState {
  notifiedIds: Set<string>;
  lastCheck: number;
}

export function useWebhookNotifications(options: WebhookNotificationOptions = {}) {
  const {
    pollInterval = 10000, // 10 secondes par défaut
    enabled = true,
    emails = [],
    onViewEmail
  } = options;

  const emailIds = emails.map(e => e.id);

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

            // Récupérer les métadonnées de l'email (subject, clientName)
            const emailMeta = emails.find(e => e.id === emailId);

            // Afficher toast selon type
            if (analysis.is_quote_request) {
              // Toast succès pour devis
              notifyQuoteProcessed({
                clientName: emailMeta?.clientName || analysis.client_matches?.[0]?.card_name,
                productCount: analysis.product_matches?.length || analysis.extracted_data?.products?.length || 0,
                emailSubject: emailMeta?.subject,
                caseType: analysis.product_matches?.[0]?.pricing_case,
                onView: onViewEmail ? () => onViewEmail(emailId) : undefined
              });

              // Si pricing calculé via product_matches, notification supplémentaire
              const pricedMatches = analysis.product_matches?.filter(m => m.unit_price != null) ?? [];
              if (pricedMatches.length > 0) {
                const firstCase = pricedMatches[0].pricing_case ?? '';
                const totalHT = pricedMatches.reduce((sum, m) => sum + (m.line_total ?? 0), 0);
                notifyPricingCalculated({
                  caseType: firstCase,
                  productCount: pricedMatches.length,
                  totalHT: totalHT > 0 ? totalHT : undefined
                });
              }
            } else {
              // Toast info pour non-devis
              notifyEmailAnalyzed({
                emailSubject: emailMeta?.subject,
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
  }, [enabled, emails.map(e => e.id).join(','), pollInterval]);

  return {
    notifiedCount: state.notifiedIds.size,
    lastCheck: state.lastCheck,
    reset: () => setState({ notifiedIds: new Set(), lastCheck: Date.now() })
  };
}
