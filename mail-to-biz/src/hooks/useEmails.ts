// Hook pour récupérer et gérer les emails réels depuis Microsoft Graph
import { useState, useCallback, useEffect } from 'react';
import { ProcessedEmail, EmailMessage } from '@/types/email';
import {
  fetchGraphEmails,
  fetchGraphEmail,
  analyzeGraphEmail,
  graphEmailToEmailMessage,
  EmailAnalysisResult,
  GraphEmail,
} from '@/lib/graphApi';
import { detectQuoteRequest } from '@/lib/quoteDetector';

interface UseEmailsOptions {
  enabled?: boolean; // false en mode démo
  autoFetch?: boolean; // fetch automatique au montage
}

interface UseEmailsReturn {
  emails: ProcessedEmail[];
  loading: boolean;
  error: string | null;
  refreshEmails: () => Promise<void>;
  analyzeEmail: (emailId: string) => Promise<EmailAnalysisResult | null>;
  getEmailAnalysis: (emailId: string) => EmailAnalysisResult | undefined;
}

export function useEmails(options: UseEmailsOptions = {}): UseEmailsReturn {
  const { enabled = true, autoFetch = true } = options;

  const [emails, setEmails] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisCache, setAnalysisCache] = useState<Map<string, EmailAnalysisResult>>(new Map());

  // Convertir un GraphEmail + analyse en ProcessedEmail
  const toProcessedEmail = useCallback(
    (graphEmail: GraphEmail, analysis?: EmailAnalysisResult): ProcessedEmail => {
      const emailMessage = graphEmailToEmailMessage(graphEmail);

      // Si pas d'analyse IA, utiliser le détecteur par règles
      if (!analysis) {
        const detection = detectQuoteRequest(
          emailMessage.subject,
          emailMessage.body.content,
          []
        );

        return {
          email: emailMessage,
          isQuote: detection.isQuote,
          detection: {
            confidence: detection.confidence,
            matchedRules: detection.matchedRules,
            sources: detection.sources,
          },
          pdfContents: [],
        };
      }

      // Utiliser les résultats de l'analyse IA
      return {
        email: emailMessage,
        isQuote: analysis.is_quote_request,
        detection: {
          confidence: analysis.confidence,
          matchedRules: [analysis.reasoning],
          sources: ['subject', 'body'] as const,
        },
        preSapDocument: analysis.extracted_data
          ? {
              sapDocumentType: 'SalesQuotation' as const,
              businessPartner: {
                CardCode: analysis.extracted_data.client_card_code || null,
                CardName: analysis.extracted_data.client_name || graphEmail.from_name || 'Client inconnu',
                ContactEmail: analysis.extracted_data.client_email || graphEmail.from_address,
                ToBeCreated: !analysis.extracted_data.client_card_code,
              },
              documentLines: analysis.extracted_data.products.map((p, idx) => ({
                LineNum: idx + 1,
                ItemCode: p.reference || null,
                ItemDescription: p.description,
                Quantity: p.quantity || 1,
                UnitOfMeasure: p.unit || 'pcs',
                RequestedDeliveryDate: null,
                ToBeCreated: true,
                SourceType: 'email' as const,
              })),
              requestedDeliveryDate: null,
              deliveryLeadTimeDays: analysis.extracted_data.delivery_requirement
                ? parseInt(analysis.extracted_data.delivery_requirement) || null
                : null,
              meta: {
                source: 'office365' as const,
                emailId: emailMessage.id,
                receivedDate: emailMessage.receivedDateTime,
                confidenceLevel: analysis.confidence,
                manualValidationRequired: true,
                detectionRules: [analysis.reasoning],
                sourceConflicts: [],
                validationStatus: 'pending' as const,
                validatedAt: null,
                validatedBy: null,
              },
            }
          : undefined,
        pdfContents: [],
        analysisResult: analysis,
      };
    },
    []
  );

  // Récupérer les emails depuis l'API Graph
  const refreshEmails = useCallback(async () => {
    if (!enabled) return;

    setLoading(true);
    setError(null);

    try {
      const result = await fetchGraphEmails({ top: 50 });

      if (!result.success || !result.data) {
        throw new Error(result.error || 'Erreur lors de la récupération des emails');
      }

      // Convertir les emails Graph en ProcessedEmail
      const processedEmails = result.data.emails.map((graphEmail) => {
        // Vérifier si on a déjà une analyse en cache
        const cachedAnalysis = analysisCache.get(graphEmail.id);
        return toProcessedEmail(graphEmail, cachedAnalysis);
      });

      setEmails(processedEmails);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Erreur inconnue';
      setError(errorMessage);
      console.error('Error fetching emails:', err);
    } finally {
      setLoading(false);
    }
  }, [enabled, analysisCache, toProcessedEmail]);

  // Analyser un email spécifique avec l'IA
  const analyzeEmail = useCallback(
    async (emailId: string): Promise<EmailAnalysisResult | null> => {
      try {
        // Vérifier le cache local
        if (analysisCache.has(emailId)) {
          return analysisCache.get(emailId)!;
        }

        // Appeler l'API d'analyse
        const result = await analyzeGraphEmail(emailId);

        if (!result.success || !result.data) {
          console.error('Analysis failed:', result.error);
          return null;
        }

        const analysis = result.data;

        // Mettre en cache
        setAnalysisCache((prev) => {
          const newCache = new Map(prev);
          newCache.set(emailId, analysis);
          return newCache;
        });

        // Mettre à jour l'email dans la liste
        setEmails((prevEmails) =>
          prevEmails.map((processedEmail) => {
            if (processedEmail.email.id === emailId) {
              // Récupérer l'email complet pour la conversion
              const graphEmail: GraphEmail = {
                id: processedEmail.email.id,
                subject: processedEmail.email.subject,
                from_name: processedEmail.email.from.emailAddress.name,
                from_address: processedEmail.email.from.emailAddress.address,
                received_datetime: processedEmail.email.receivedDateTime,
                body_preview: processedEmail.email.bodyPreview,
                body_content: processedEmail.email.body.content,
                body_content_type: processedEmail.email.body.contentType,
                has_attachments: processedEmail.email.hasAttachments,
                is_read: processedEmail.email.isRead,
                attachments: processedEmail.email.attachments.map((a) => ({
                  id: a.id,
                  name: a.name,
                  content_type: a.contentType,
                  size: a.size,
                })),
              };
              return toProcessedEmail(graphEmail, analysis);
            }
            return processedEmail;
          })
        );

        return analysis;
      } catch (err) {
        console.error('Error analyzing email:', err);
        return null;
      }
    },
    [analysisCache, toProcessedEmail]
  );

  // Récupérer l'analyse d'un email depuis le cache
  const getEmailAnalysis = useCallback(
    (emailId: string): EmailAnalysisResult | undefined => {
      return analysisCache.get(emailId);
    },
    [analysisCache]
  );

  // Fetch automatique au montage
  useEffect(() => {
    if (enabled && autoFetch) {
      refreshEmails();
    }
  }, [enabled, autoFetch]); // Ne pas inclure refreshEmails pour éviter les boucles

  return {
    emails,
    loading,
    error,
    refreshEmails,
    analyzeEmail,
    getEmailAnalysis,
  };
}

// Type étendu pour ProcessedEmail avec résultat d'analyse
declare module '@/types/email' {
  interface ProcessedEmail {
    analysisResult?: EmailAnalysisResult;
  }
}
