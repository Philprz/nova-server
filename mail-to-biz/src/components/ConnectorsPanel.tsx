import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle, Loader2, Cloud, Database, Users } from 'lucide-react';

interface ConnectorStatus {
  isConnected: boolean;
  isTesting: boolean;
  testResult: 'success' | 'error' | null;
  testMessage: string | null;
}

interface Connector {
  id: string;
  name: string;
  description: string;
  icon: typeof Cloud;
  initialStatus: 'connected' | 'configured' | 'not-connected';
  disabled?: boolean;
}

const connectors: Connector[] = [
  {
    id: 'microsoft',
    name: 'Microsoft 365',
    description: 'Emails, SharePoint, pièces jointes',
    icon: Cloud,
    initialStatus: 'connected',
  },
  {
    id: 'sap',
    name: 'SAP Business One',
    description: 'Clients, articles, devis',
    icon: Database,
    initialStatus: 'configured',
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description: 'Comptes, opportunités',
    icon: Users,
    initialStatus: 'not-connected',
    disabled: true,
  },
];

export const ConnectorsPanel = () => {
  const [statuses, setStatuses] = useState<Record<string, ConnectorStatus>>({
    microsoft: { isConnected: true, isTesting: false, testResult: null, testMessage: null },
    sap: { isConnected: true, isTesting: false, testResult: null, testMessage: null },
    salesforce: { isConnected: false, isTesting: false, testResult: null, testMessage: null },
  });

  const handleTestConnection = async (connectorId: string) => {
    setStatuses(prev => ({
      ...prev,
      [connectorId]: { ...prev[connectorId], isTesting: true, testResult: null, testMessage: null }
    }));

    try {
      if (connectorId === 'sap') {
        // Appel réel à l'API SAP Rondot
        const response = await fetch('/api/sap-rondot/test-connection');
        const data = await response.json();

        setStatuses(prev => ({
          ...prev,
          [connectorId]: {
            ...prev[connectorId],
            isTesting: false,
            testResult: data.success ? 'success' : 'error',
            testMessage: data.message,
          }
        }));
        return;
      }

      if (connectorId === 'microsoft') {
        // Appel réel à l'API Microsoft Graph
        const response = await fetch('/api/graph/test-connection');
        const data = await response.json();

        const message = data.success
          ? `Connexion réussie. Boîte mail accessible : ${data.mailboxInfo?.mail || 'N/A'}`
          : data.error || 'Échec de la connexion';

        setStatuses(prev => ({
          ...prev,
          [connectorId]: {
            ...prev[connectorId],
            isTesting: false,
            testResult: data.success ? 'success' : 'error',
            testMessage: message,
          }
        }));
        return;
      }

      // Pour les autres connecteurs, simulation
      await new Promise(resolve => setTimeout(resolve, 1500));

      const results: Record<string, { success: boolean; message: string }> = {
        salesforce: {
          success: false,
          message: 'Non configuré'
        },
      };

      const result = results[connectorId] || { success: false, message: 'Connecteur inconnu' };

      setStatuses(prev => ({
        ...prev,
        [connectorId]: {
          ...prev[connectorId],
          isTesting: false,
          testResult: result.success ? 'success' : 'error',
          testMessage: result.message,
        }
      }));
    } catch (error) {
      setStatuses(prev => ({
        ...prev,
        [connectorId]: {
          ...prev[connectorId],
          isTesting: false,
          testResult: 'error',
          testMessage: `Erreur de connexion: ${error instanceof Error ? error.message : 'Erreur inconnue'}`,
        }
      }));
    }
  };

  const getStatusBadge = (connector: Connector) => {
    if (connector.initialStatus === 'connected') {
      return <Badge className="bg-green-500/10 text-green-600 border-green-500/20">Connecté</Badge>;
    }
    if (connector.initialStatus === 'configured') {
      return <Badge variant="secondary">Configuré (démo)</Badge>;
    }
    return <Badge variant="outline" className="opacity-50">Non connecté</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Connecteurs</h1>
        <p className="text-muted-foreground mt-1">
          Gérez les connexions aux systèmes externes
        </p>
      </div>

      {/* Connectors Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {connectors.map((connector) => {
          const status = statuses[connector.id];
          const Icon = connector.icon;

          return (
            <Card key={connector.id} className={connector.disabled ? 'opacity-60' : ''}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
                      <Icon className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{connector.name}</CardTitle>
                      <CardDescription className="text-sm">
                        {connector.description}
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Statut</span>
                  {getStatusBadge(connector)}
                </div>

                {/* Test Result */}
                {status.testResult && (
                  <div className={`p-3 rounded-lg text-sm ${
                    status.testResult === 'success' 
                      ? 'bg-green-500/10 text-green-700 border border-green-500/20' 
                      : 'bg-destructive/10 text-destructive border border-destructive/20'
                  }`}>
                    <div className="flex items-start gap-2">
                      {status.testResult === 'success' ? (
                        <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      )}
                      <span>{status.testMessage}</span>
                    </div>
                  </div>
                )}

                {/* Action Button */}
                {connector.disabled ? (
                  <Button variant="outline" disabled className="w-full">
                    Configurer plus tard
                  </Button>
                ) : (
                  <Button 
                    variant="outline" 
                    className="w-full"
                    onClick={() => handleTestConnection(connector.id)}
                    disabled={status.isTesting}
                  >
                    {status.isTesting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Test en cours...
                      </>
                    ) : (
                      'Tester la connexion'
                    )}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Info Section */}
      <Card className="bg-muted/30">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Cloud className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-medium text-foreground">Mode démonstration</h3>
              <p className="text-sm text-muted-foreground mt-1">
                Les tests de connexion sont simulés pour cette démo. 
                En production, les connecteurs vérifient réellement l'accès aux systèmes configurés.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
