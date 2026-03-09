import { useState, useEffect } from 'react';
import { AppHeader } from '@/components/AppHeader';
import { Sidebar } from '@/components/Sidebar';
import { WebhookStatusBadge } from '@/components/WebhookStatusBadge';
import { EmailList } from '@/components/EmailList';
import { QuoteValidation } from '@/components/QuoteValidation';
import { QuoteSummary } from '@/components/QuoteSummary';
import { ConfigPanel } from '@/components/ConfigPanel';
import { ConnectorsPanel } from '@/components/ConnectorsPanel';
import { AccountSelection } from '@/components/AccountSelection';
import { getMockEmails, processEmails } from '@/hooks/useMockData';
import { useEmails } from '@/hooks/useEmails';
import { useEmailMode } from '@/hooks/useEmailMode';
import { useWebhookNotifications } from '@/hooks/useWebhookNotifications';
import { ProcessedEmail } from '@/types/email';
import { Loader2, RefreshCw, Wifi, WifiOff, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ManualQuoteModal } from '@/components/ManualQuoteModal';
import { ManualQuoteResult, graphEmailToEmailMessage } from '@/lib/graphApi';

type View = 'account-selection' | 'inbox' | 'quotes' | 'config' | 'connectors' | 'summary';

const Index = () => {
  const [currentView, setCurrentView] = useState<View>('account-selection');
  const [selectedQuote, setSelectedQuote] = useState<ProcessedEmail | null>(null);
  const [manualModalOpen, setManualModalOpen] = useState(false);

  // Emails marqués comme traités (persisté en localStorage)
  const [processedEmailIds, setProcessedEmailIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem('nova_processed_emails');
      if (stored) return new Set<string>(JSON.parse(stored));
    } catch {}
    return new Set<string>();
  });

  // Métadonnées des emails traités (N° SAP, date)
  const [processedEmailsMeta, setProcessedEmailsMeta] = useState<Record<string, { sapDocNum?: number; createdAt: string }>>(() => {
    try {
      const stored = localStorage.getItem('nova_processed_emails_meta');
      if (stored) return JSON.parse(stored);
    } catch {}
    return {};
  });

  // Mode démo / live
  const { isDemoMode } = useEmailMode();

  // Emails réels (Microsoft Graph)
  const {
    emails: liveEmails,
    loading: liveLoading,
    error: liveError,
    analyzingEmailId,
    refreshEmails,
    analyzeEmail,
    reanalyzeEmail,
    getLatestEmail,
    addManualEmailToList,
  } = useEmails({ enabled: !isDemoMode, autoFetch: !isDemoMode });

  // Emails de démonstration (mock)
  const [mockEmails] = useState<ProcessedEmail[]>(() => processEmails(getMockEmails()));

  // Sélectionner la source de données selon le mode
  const displayEmails = isDemoMode ? mockEmails : liveEmails;
  const isLoading = !isDemoMode && liveLoading;

  const quotes = displayEmails.filter((e) => e.isQuote);

  // Notifications webhook pour emails traités automatiquement
  const webhookStatus = useWebhookNotifications({
    enabled: !isDemoMode && currentView === 'inbox',
    emails: quotes.map(q => ({
      id: q.email.id,
      subject: q.email.subject,
      clientName: q.email.from.emailAddress.name
    })),
    pollInterval: 10000, // Vérification toutes les 10 secondes
    onViewEmail: (emailId) => {
      const quote = quotes.find(q => q.email.id === emailId);
      if (quote) handleSelectQuote(quote);
    }
  });
  // Compter les devis non traités : pas de preSapDocument OU status pending
  const pendingCount = quotes.filter((q) => {
    const status = q.preSapDocument?.meta.validationStatus;
    return status !== 'validated' && status !== 'rejected';
  }).length;

  // Rafraîchir les emails quand on passe en mode live
  useEffect(() => {
    if (!isDemoMode && currentView === 'inbox') {
      refreshEmails();
    }
  }, [isDemoMode, currentView]);

  // Synchroniser processedEmailsMeta depuis le backend quand les emails sont chargés
  useEffect(() => {
    if (isDemoMode || liveEmails.length === 0) return;
    const quoteIds = liveEmails.filter(e => e.isQuote).map(e => e.email.id);
    if (quoteIds.length === 0) return;

    fetch('/api/sap/quotation/batch-by-emails', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quoteIds),
    })
      .then(r => r.json())
      .then((backendMeta: Record<string, { sapDocNum?: number; createdAt: string }>) => {
        if (!backendMeta || Object.keys(backendMeta).length === 0) return;
        // Fusionner : backend prime sur localStorage
        setProcessedEmailsMeta(prev => ({ ...prev, ...backendMeta }));
        // Marquer comme traités les IDs retournés par le backend
        setProcessedEmailIds(prev => {
          const next = new Set(prev);
          Object.keys(backendMeta).forEach(id => next.add(id));
          return next;
        });
      })
      .catch(() => { /* silencieux */ });
  }, [liveEmails, isDemoMode]);

  // Filet de sécurité: sync selectedQuote si liveEmails est mis à jour (ex: pré-analyse)
  useEffect(() => {
    if (selectedQuote && currentView === 'summary' && !isDemoMode) {
      const latestEmail = getLatestEmail(selectedQuote.email.id);
      // Mettre à jour si l'email a maintenant une analysisResult et selectedQuote n'en a pas
      if (latestEmail?.analysisResult && !selectedQuote.analysisResult) {
        setSelectedQuote(latestEmail);
      }
    }
  }, [liveEmails, selectedQuote?.email.id, currentView, isDemoMode, getLatestEmail]);

  const handleSelectQuote = async (quote: ProcessedEmail) => {
    // Si en mode live et pas encore analysé, lancer l'analyse IA
    if (!isDemoMode && !quote.analysisResult) {
      await analyzeEmail(quote.email.id);

      // FIX: Utiliser getLatestEmail au lieu de liveEmails (évite stale closure)
      const updatedEmail = getLatestEmail(quote.email.id);
      if (updatedEmail) {
        setSelectedQuote(updatedEmail);
        setCurrentView('summary');
        return;
      }
    }
    setSelectedQuote(quote);
    setCurrentView('summary');
  };

  const handleValidate = (_updatedDoc: ProcessedEmail) => {
    // En mode démo, mise à jour locale
    // En mode live, le backend gère l'état
    setSelectedQuote(null);
  };

  const handleSummaryValidate = (sapDocNum?: number) => {
    // Marquer l'email comme traité
    if (selectedQuote) {
      const emailId = selectedQuote.email.id;
      setProcessedEmailIds(prev => {
        const next = new Set(prev);
        next.add(emailId);
        try { localStorage.setItem('nova_processed_emails', JSON.stringify([...next])); } catch {}
        return next;
      });
      if (sapDocNum) {
        setProcessedEmailsMeta(prev => {
          const next = { ...prev, [emailId]: { sapDocNum, createdAt: new Date().toISOString() } };
          try { localStorage.setItem('nova_processed_emails_meta', JSON.stringify(next)); } catch {}
          return next;
        });
      }
    }
    setSelectedQuote(null);
    setCurrentView('inbox');
  };

  const handleSummaryBack = () => {
    setSelectedQuote(null);
    setCurrentView('inbox');
  };

  const handleReanalyze = async () => {
    if (!selectedQuote || isDemoMode) return;
    const analysis = await reanalyzeEmail(selectedQuote.email.id);
    if (analysis) {
      const updated = getLatestEmail(selectedQuote.email.id);
      if (updated) setSelectedQuote(updated);
    }
  };

  const handleAccountSelect = () => {
    setCurrentView('inbox');
  };

  const handleManualCreated = (result: ManualQuoteResult) => {
    // Construire un GraphEmail synthétique à partir du résultat backend
    const clientName = result.analysis_result.extracted_data?.client_name ?? 'Client';
    const itemCount = result.analysis_result.product_matches?.length ?? 0;
    const bodyPreview = (result.analysis_result.product_matches ?? [])
      .map((p: { item_name?: string; quantity?: number }) => `${p.item_name ?? p} x${p.quantity ?? 1}`)
      .join(', ');
    const syntheticGraphEmail = {
      id: result.email_id,
      subject: `Demande manuelle — ${clientName} (${itemCount} produit${itemCount > 1 ? 's' : ''})`,
      from_name: 'Saisie manuelle',
      from_address: 'saisie.manuelle@rondot.fr',
      received_datetime: new Date().toISOString(),
      body_preview: bodyPreview,
      body_content: bodyPreview,
      body_content_type: 'text',
      has_attachments: false,
      is_read: true,
      attachments: [],
      is_quote_by_subject: true,
      source: 'manual' as const,
    };
    addManualEmailToList(syntheticGraphEmail, result.analysis_result);
    // Naviguer directement vers le résumé du devis créé
    const emailMessage = graphEmailToEmailMessage(syntheticGraphEmail);
    const processedQuote = {
      email: emailMessage,
      isQuote: true,
      detection: { confidence: 'high' as const, matchedRules: ['Saisie manuelle'], sources: ['body'] as const },
      pdfContents: [],
      analysisResult: result.analysis_result,
    };
    setSelectedQuote(processedQuote as ProcessedEmail);
    setCurrentView('summary');
  };

  // Show account selection as first screen
  if (currentView === 'account-selection') {
    return <AccountSelection onSelectAccount={handleAccountSelect} />;
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <AppHeader pendingCount={pendingCount} />

      <div className="flex flex-1">
        <Sidebar
          currentView={currentView}
          onViewChange={setCurrentView}
          quotesCount={quotes.length}
          pendingCount={pendingCount}
        />

        <main className="flex-1 p-6 overflow-auto">
          {/* Barre de contrôle du mode */}
          {currentView === 'inbox' && (
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold">Emails reçus</h2>
                <Badge
                  variant={isDemoMode ? 'secondary' : 'default'}
                  className="flex items-center gap-1"
                >
                  {isDemoMode ? (
                    <>
                      <WifiOff className="h-3 w-3" />
                      Mode Démo
                    </>
                  ) : (
                    <>
                      <Wifi className="h-3 w-3" />
                      Mode Live
                    </>
                  )}
                </Badge>
                <WebhookStatusBadge
                  notifiedCount={webhookStatus.notifiedCount}
                  lastCheck={webhookStatus.lastCheck}
                  isActive={!isDemoMode && currentView === 'inbox'}
                />
                {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              </div>

              <div className="flex items-center gap-2">
                {!isDemoMode && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={refreshEmails}
                    disabled={liveLoading}
                  >
                    <RefreshCw className={`h-4 w-4 mr-1 ${liveLoading ? 'animate-spin' : ''}`} />
                    Actualiser
                  </Button>
                )}
                {!isDemoMode && (
                  <Button
                    size="sm"
                    onClick={() => setManualModalOpen(true)}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Nouvelle demande
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Affichage de l'erreur */}
          {liveError && !isDemoMode && currentView === 'inbox' && (
            <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-md mb-4">
              <p className="font-medium">Erreur de connexion</p>
              <p className="text-sm">{liveError}</p>
              <p className="text-sm mt-1">
                Vérifiez la configuration Microsoft dans l'onglet Connecteurs.
              </p>
            </div>
          )}

          {currentView === 'config' && <ConfigPanel />}

          {currentView === 'connectors' && <ConnectorsPanel />}

          {currentView === 'inbox' && (
            <>
              {isLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="h-8 w-8 animate-spin mb-4" />
                  <p>Chargement des emails...</p>
                </div>
              ) : (
                <EmailList
                  emails={displayEmails}
                  onSelectQuote={handleSelectQuote}
                  analyzingEmailId={analyzingEmailId}
                  processedIds={processedEmailIds}
                  processedMeta={processedEmailsMeta}
                  onReanalyze={!isDemoMode ? async (emailId) => { await reanalyzeEmail(emailId); } : undefined}
                />
              )}
            </>
          )}

          {currentView === 'quotes' && (
            <QuoteValidation
              quotes={quotes}
              selectedQuote={selectedQuote}
              onSelectQuote={setSelectedQuote}
              onValidate={handleValidate}
            />
          )}

          {currentView === 'summary' && selectedQuote && (
            <QuoteSummary
              quote={selectedQuote}
              onValidate={handleSummaryValidate}
              onBack={handleSummaryBack}
              onReanalyze={!isDemoMode ? handleReanalyze : undefined}
              isReanalyzing={analyzingEmailId === selectedQuote.email.id}
              isProcessed={processedEmailIds.has(selectedQuote.email.id)}
            />
          )}
        </main>
      </div>
      {!isDemoMode && (
        <ManualQuoteModal
          open={manualModalOpen}
          onClose={() => setManualModalOpen(false)}
          onCreated={handleManualCreated}
        />
      )}
    </div>
  );
};

export default Index;
