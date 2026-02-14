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
import { Loader2, RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

type View = 'account-selection' | 'inbox' | 'quotes' | 'config' | 'connectors' | 'summary';

const Index = () => {
  const [currentView, setCurrentView] = useState<View>('account-selection');
  const [selectedQuote, setSelectedQuote] = useState<ProcessedEmail | null>(null);

  // Mode démo / live
  const { mode, toggleMode, isDemoMode } = useEmailMode();

  // Emails réels (Microsoft Graph)
  const {
    emails: liveEmails,
    loading: liveLoading,
    error: liveError,
    analyzingEmailId,
    refreshEmails,
    analyzeEmail,
    getLatestEmail,
  } = useEmails({ enabled: !isDemoMode, autoFetch: !isDemoMode });

  // Emails de démonstration (mock)
  const [mockEmails] = useState<ProcessedEmail[]>(() => processEmails(getMockEmails()));

  // Notifications webhook pour emails traités automatiquement
  const webhookStatus = useWebhookNotifications({
    enabled: !isDemoMode && currentView === 'inbox',
    emailIds: quotes.map(q => q.email.id),
    pollInterval: 10000 // Vérification toutes les 10 secondes
  });

  // Sélectionner la source de données selon le mode
  const displayEmails = isDemoMode ? mockEmails : liveEmails;
  const isLoading = !isDemoMode && liveLoading;

  const quotes = displayEmails.filter((e) => e.isQuote);
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

  const handleValidate = (updatedDoc: ProcessedEmail) => {
    // En mode démo, mise à jour locale
    // En mode live, le backend gère l'état
    setSelectedQuote(null);
  };

  const handleSummaryValidate = () => {
    setSelectedQuote(null);
    setCurrentView('inbox');
  };

  const handleSummaryBack = () => {
    setSelectedQuote(null);
    setCurrentView('inbox');
  };

  const handleAccountSelect = () => {
    setCurrentView('inbox');
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
                <Button variant="outline" size="sm" onClick={toggleMode}>
                  {isDemoMode ? 'Passer en Live' : 'Passer en Démo'}
                </Button>
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
                <EmailList emails={displayEmails} onSelectQuote={handleSelectQuote} analyzingEmailId={analyzingEmailId} />
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
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default Index;
