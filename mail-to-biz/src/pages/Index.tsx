import { useState, useEffect, useCallback } from 'react';
import { AppHeader } from '@/components/AppHeader';
import { Sidebar } from '@/components/Sidebar';
import { WebhookStatusBadge } from '@/components/WebhookStatusBadge';
import { EmailList } from '@/components/EmailList';
import { EmailFilters, EmailFiltersState, DEFAULT_FILTERS } from '@/components/EmailFilters';
import { QuoteValidation } from '@/components/QuoteValidation';
import { QuoteSummary } from '@/components/QuoteSummary';
import { ConfigPanel } from '@/components/ConfigPanel';
import { ConnectorsPanel } from '@/components/ConnectorsPanel';
import { AccountSelection } from '@/components/AccountSelection';
import { useAuth } from '@/contexts/AuthContext';
import { fetchWithAuth } from '@/lib/fetchWithAuth';
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

type View = 'inbox' | 'quotes' | 'config' | 'connectors' | 'summary';

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

function normalizeStr(s: string) {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

const Index = () => {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [currentView, setCurrentView] = useState<View>('inbox');
  const [selectedQuote, setSelectedQuote] = useState<ProcessedEmail | null>(null);
  const [manualModalOpen, setManualModalOpen] = useState(false);

  // ── Emails marqués comme traités ────────────────────────────────
  const [processedEmailIds, setProcessedEmailIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem('nova_processed_emails');
      if (stored) return new Set<string>(JSON.parse(stored));
    } catch {}
    return new Set<string>();
  });

  const [processedEmailsMeta, setProcessedEmailsMeta] = useState<Record<string, { sapDocNum?: number; createdAt: string }>>(() => {
    try {
      const stored = localStorage.getItem('nova_processed_emails_meta');
      if (stored) return JSON.parse(stored);
    } catch {}
    return {};
  });

  // ── Statuts archive / étoile (serveur) ──────────────────────────
  const [emailStatusMap, setEmailStatusMap] = useState<Record<string, { archived: boolean; starred: boolean; label?: string }>>({});

  const archivedIds = new Set(
    Object.entries(emailStatusMap)
      .filter(([, s]) => s.archived)
      .map(([id]) => id)
  );
  const starredIds = new Set(
    Object.entries(emailStatusMap)
      .filter(([, s]) => s.starred)
      .map(([id]) => id)
  );

  // ── Filtres ──────────────────────────────────────────────────────
  const [filters, setFilters] = useState<EmailFiltersState>(DEFAULT_FILTERS);

  // ── Mode démo / live ────────────────────────────────────────────
  const { isDemoMode } = useEmailMode();

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
  } = useEmails({ enabled: !isDemoMode && isAuthenticated, autoFetch: !isDemoMode && isAuthenticated });

  const [mockEmails] = useState<ProcessedEmail[]>(() => processEmails(getMockEmails()));

  const displayEmails = isDemoMode ? mockEmails : liveEmails;
  const isLoading = !isDemoMode && liveLoading;

  const quotes = displayEmails.filter((e) => e.isQuote);

  const webhookStatus = useWebhookNotifications({
    enabled: !isDemoMode && currentView === 'inbox',
    emails: quotes.map(q => ({
      id: q.email.id,
      subject: q.email.subject,
      clientName: q.email.from.emailAddress.name,
    })),
    pollInterval: 10000,
    onViewEmail: (emailId) => {
      const quote = quotes.find(q => q.email.id === emailId);
      if (quote) handleSelectQuote(quote);
    },
  });

  const pendingCount = quotes.filter((q) =>
    !processedEmailIds.has(q.email.id) && !archivedIds.has(q.email.id)
  ).length;

  // ── Chargement du status-map depuis le serveur ───────────────────
  useEffect(() => {
    if (isDemoMode || !isAuthenticated) return;
    fetchWithAuth('/api/graph/emails/status-map')
      .then(r => r.ok ? r.json() : {})
      .then(data => setEmailStatusMap(data))
      .catch(() => {});
  }, [isDemoMode, isAuthenticated]);

  // ── Sync emails traités depuis le backend ────────────────────────
  useEffect(() => {
    if (isDemoMode || liveEmails.length === 0) return;
    const quoteIds = liveEmails.filter(e => e.isQuote).map(e => e.email.id);
    if (quoteIds.length === 0) return;

    fetchWithAuth('/api/sap/quotation/batch-by-emails', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quoteIds),
    })
      .then(r => r.json())
      .then((backendMeta: Record<string, { sapDocNum?: number; createdAt: string }>) => {
        if (!backendMeta || Object.keys(backendMeta).length === 0) return;
        setProcessedEmailsMeta(prev => ({ ...prev, ...backendMeta }));
        setProcessedEmailIds(prev => {
          const next = new Set(prev);
          Object.keys(backendMeta).forEach(id => next.add(id));
          return next;
        });
      })
      .catch(() => {});
  }, [liveEmails, isDemoMode]);

  useEffect(() => {
    if (!isDemoMode && currentView === 'inbox') refreshEmails();
  }, [isDemoMode, currentView]);

  useEffect(() => {
    if (selectedQuote && currentView === 'summary' && !isDemoMode) {
      const latestEmail = getLatestEmail(selectedQuote.email.id);
      if (latestEmail?.analysisResult && !selectedQuote.analysisResult) {
        setSelectedQuote(latestEmail);
      }
    }
  }, [liveEmails, selectedQuote?.email.id, currentView, isDemoMode, getLatestEmail]);

  // ── Logique de filtrage ──────────────────────────────────────────
  const filteredEmails = displayEmails.filter((item) => {
    const id = item.email.id;
    const isProcessed = processedEmailIds.has(id);
    const isArchived  = archivedIds.has(id);
    const isManual    = id.startsWith('manual_');

    // Statut
    if (filters.status === 'archived'  && !isArchived)  return false;
    if (filters.status === 'processed' && !isProcessed) return false;
    if (filters.status === 'pending'   && (isProcessed || isArchived)) return false;
    // Par défaut ('all') : on masque les archivés sauf si on filtre explicitement dessus
    if (filters.status === 'all' && isArchived) return false;

    // Type
    if (filters.type === 'quote' && !item.isQuote)  return false;
    if (filters.type === 'other' && item.isQuote)   return false;

    // Source
    if (filters.source === 'email'  && isManual)  return false;
    if (filters.source === 'manual' && !isManual) return false;

    // Confiance (uniquement sur les devis)
    if (filters.confidence !== 'all' && item.isQuote) {
      if (item.detection.confidence !== filters.confidence) return false;
    }

    // Étoilés
    if (filters.starredOnly && !starredIds.has(id)) return false;

    // Non lus
    if (filters.unreadOnly && item.email.isRead) return false;

    // Pièces jointes
    if (filters.withAttachments && !item.email.hasAttachments) return false;

    // Recherche texte (objet, expéditeur, aperçu)
    if (filters.search.trim()) {
      const q = normalizeStr(filters.search.trim());
      const hay = normalizeStr(
        [
          item.email.subject,
          item.email.from.emailAddress.name,
          item.email.from.emailAddress.address,
          item.email.bodyPreview,
        ].join(' ')
      );
      if (!hay.includes(q)) return false;
    }

    return true;
  });

  // ── Handlers archive / étoile ────────────────────────────────────
  const handleArchive = useCallback((emailId: string, archived: boolean) => {
    setEmailStatusMap(prev => ({
      ...prev,
      [emailId]: { ...(prev[emailId] ?? { starred: false }), archived },
    }));
    fetchWithAuth(`/api/graph/emails/${encodeURIComponent(emailId)}/set-status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived }),
    }).catch(() => {});
  }, []);

  const handleStar = useCallback((emailId: string, starred: boolean) => {
    setEmailStatusMap(prev => ({
      ...prev,
      [emailId]: { ...(prev[emailId] ?? { archived: false }), starred },
    }));
    fetchWithAuth(`/api/graph/emails/${encodeURIComponent(emailId)}/set-status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred }),
    }).catch(() => {});
  }, []);

  // ── Handlers navigation ──────────────────────────────────────────
  const handleSelectQuote = async (quote: ProcessedEmail) => {
    if (!isDemoMode && !quote.analysisResult) {
      await analyzeEmail(quote.email.id);
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
    setSelectedQuote(null);
  };

  const handleSummaryValidate = (sapDocNum?: number) => {
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

  // Analyse forcée d'un email classé "Non pertinent"
  const handleAnalyzeNonQuote = async (item: ProcessedEmail) => {
    if (isDemoMode) return;
    await reanalyzeEmail(item.email.id);
    const updated = getLatestEmail(item.email.id);
    if (updated?.isQuote) {
      setSelectedQuote(updated);
      setCurrentView('summary');
    }
  };


  const handleManualCreated = (result: ManualQuoteResult) => {
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
    const emailMessage = graphEmailToEmailMessage(syntheticGraphEmail);
    const processedQuote = {
      email: emailMessage,
      isQuote: true,
      detection: { confidence: 'high' as const, matchedRules: ['Saisie manuelle'], sources: ['body'] as ('body' | 'subject' | 'attachment')[] },
      pdfContents: [],
      analysisResult: result.analysis_result,
    };
    setSelectedQuote(processedQuote as ProcessedEmail);
    setCurrentView('summary');
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AccountSelection />;
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
          {/* Barre de contrôle */}
          {currentView === 'inbox' && (
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold">Emails reçus</h2>
                <Badge
                  variant={isDemoMode ? 'secondary' : 'default'}
                  className="flex items-center gap-1"
                >
                  {isDemoMode ? (
                    <><WifiOff className="h-3 w-3" />Mode Démo</>
                  ) : (
                    <><Wifi className="h-3 w-3" />Mode Live</>
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
                  <Button variant="outline" size="sm" onClick={refreshEmails} disabled={liveLoading}>
                    <RefreshCw className={`h-4 w-4 mr-1 ${liveLoading ? 'animate-spin' : ''}`} />
                    Actualiser
                  </Button>
                )}
                {!isDemoMode && (
                  <Button size="sm" onClick={() => setManualModalOpen(true)}>
                    <Plus className="h-4 w-4 mr-1" />
                    Nouvelle demande
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Erreur connexion */}
          {liveError && !isDemoMode && currentView === 'inbox' && (
            <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-md mb-4">
              <p className="font-medium">Erreur de connexion</p>
              <p className="text-sm">{liveError}</p>
              <p className="text-sm mt-1">Vérifiez la configuration Microsoft dans l'onglet Connecteurs.</p>
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
                <>
                  <EmailFilters
                    filters={filters}
                    onChange={setFilters}
                    totalCount={displayEmails.filter(e => !archivedIds.has(e.email.id) || filters.status === 'archived').length}
                    filteredCount={filteredEmails.length}
                  />
                  <EmailList
                    emails={filteredEmails}
                    onSelectQuote={handleSelectQuote}
                    onAnalyze={!isDemoMode ? handleAnalyzeNonQuote : undefined}
                    analyzingEmailId={analyzingEmailId}
                    processedIds={processedEmailIds}
                    processedMeta={processedEmailsMeta}
                    onReanalyze={!isDemoMode ? async (emailId) => { await reanalyzeEmail(emailId); } : undefined}
                    archivedIds={archivedIds}
                    starredIds={starredIds}
                    onArchive={!isDemoMode ? handleArchive : undefined}
                    onStar={!isDemoMode ? handleStar : undefined}
                  />
                </>
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
              onReanalyze={!isDemoMode && !processedEmailIds.has(selectedQuote.email.id) ? handleReanalyze : undefined}
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
