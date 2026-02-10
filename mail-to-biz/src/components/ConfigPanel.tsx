import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle, Key, Mail, Shield, Loader2, XCircle, Wifi, WifiOff, Edit2, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SupplierTariffsConfig } from './SupplierTariffsConfig';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ConnectionTestResult {
  success: boolean;
  step: string;
  details: {
    tenantId: boolean;
    clientId: boolean;
    clientSecret: boolean;
    mailboxAddress: boolean;
    tokenAcquired: boolean;
    mailboxAccessible: boolean;
  };
  error?: string;
  mailboxInfo?: {
    displayName: string;
    mail: string;
  };
}

interface CredentialConfig {
  key: string;
  label: string;
  icon: typeof Key;
  description: string;
  placeholder: string;
  type: 'text' | 'password';
}

const CREDENTIALS: CredentialConfig[] = [
  {
    key: 'MS_TENANT_ID',
    label: 'Tenant ID',
    icon: Key,
    description: 'ID du tenant Azure AD (format GUID)',
    placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    type: 'text',
  },
  {
    key: 'MS_CLIENT_ID',
    label: 'Client ID',
    icon: Key,
    description: 'ID de l\'application Azure AD',
    placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    type: 'text',
  },
  {
    key: 'MS_CLIENT_SECRET',
    label: 'Client Secret',
    icon: Key,
    description: 'Secret de l\'application Azure AD',
    placeholder: 'Votre secret client...',
    type: 'password',
  },
  {
    key: 'MS_MAILBOX_ADDRESS',
    label: 'Adresse email',
    icon: Mail,
    description: 'Adresse de la boîte mail à surveiller',
    placeholder: 'quotes@entreprise.com',
    type: 'text',
  },
];

export function ConfigPanel() {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [editingCredential, setEditingCredential] = useState<string | null>(null);
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [individualTests, setIndividualTests] = useState<Record<string, 'pending' | 'testing' | 'success' | 'error'>>({});

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/graph/test-connection`);
      const data = await response.json();

      if (!response.ok && !data.details) {
        toast.error('Erreur lors du test de connexion');
        setTestResult({
          success: false,
          step: 'error',
          error: data.detail || 'Erreur serveur',
          details: {
            tenantId: false,
            clientId: false,
            clientSecret: false,
            mailboxAddress: false,
            tokenAcquired: false,
            mailboxAccessible: false,
          },
        });
        return;
      }

      setTestResult(data as ConnectionTestResult);

      // Update individual test states based on result
      setIndividualTests({
        MS_TENANT_ID: data.details.tenantId ? 'success' : 'error',
        MS_CLIENT_ID: data.details.clientId ? 'success' : 'error',
        MS_CLIENT_SECRET: data.details.clientSecret ? 'success' : 'error',
        MS_MAILBOX_ADDRESS: data.details.mailboxAddress ? 'success' : 'error',
      });

      if (data.success) {
        toast.success(`Connexion réussie à ${data.mailboxInfo?.mail}`);
      } else {
        toast.error(data.error || 'Échec de la connexion');
      }
    } catch (err) {
      toast.error('Erreur inattendue');
      console.error(err);
    } finally {
      setIsTesting(false);
    }
  };

  const handleEditCredential = (key: string) => {
    setEditingCredential(key);
    setCredentialValues(prev => ({ ...prev, [key]: '' }));
  };

  const handleCancelEdit = () => {
    setEditingCredential(null);
  };

  const toggleShowSecret = (key: string) => {
    setShowSecrets(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const getCredentialStatus = (key: string) => {
    if (individualTests[key] === 'success') return 'success';
    if (individualTests[key] === 'error') return 'error';
    if (testResult?.details) {
      const keyMap: Record<string, keyof ConnectionTestResult['details']> = {
        MS_TENANT_ID: 'tenantId',
        MS_CLIENT_ID: 'clientId',
        MS_CLIENT_SECRET: 'clientSecret',
        MS_MAILBOX_ADDRESS: 'mailboxAddress',
      };
      return testResult.details[keyMap[key]] ? 'success' : 'error';
    }
    return 'pending';
  };

  const renderCredentialStatus = (key: string) => {
    const status = getCredentialStatus(key);
    
    if (status === 'success') {
      return <CheckCircle className="w-4 h-4 text-success" />;
    }
    if (status === 'error') {
      return <XCircle className="w-4 h-4 text-destructive" />;
    }
    return <Badge variant="outline" className="text-xs">Non testé</Badge>;
  };

  return (
    <div className="max-w-2xl space-y-6 animate-fade-in">
      <div>
        <h2 className="section-title mb-2">Configuration Microsoft Graph</h2>
        <p className="text-sm text-muted-foreground">
          Connexion à Office 365 pour la récupération des emails
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-primary" />
              Credentials Azure AD
            </CardTitle>
            <Badge className="bg-success text-success-foreground">
              <CheckCircle className="w-3 h-3 mr-1" /> Configuré
            </Badge>
          </div>
          <CardDescription>
            Cliquez sur Modifier pour changer une valeur. Les secrets sont stockés de manière sécurisée.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4">
            {CREDENTIALS.map((cred) => {
              const Icon = cred.icon;
              const isEditing = editingCredential === cred.key;
              const isSecret = cred.type === 'password';
              const showSecret = showSecrets[cred.key];

              return (
                <div key={cred.key} className="p-4 rounded-lg bg-muted border border-border">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <Icon className="w-4 h-4 text-muted-foreground" />
                      <div>
                        <span className="text-sm font-medium">{cred.label}</span>
                        <p className="text-xs text-muted-foreground">{cred.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {renderCredentialStatus(cred.key)}
                      {!isEditing && (
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => handleEditCredential(cred.key)}
                        >
                          <Edit2 className="w-3 h-3 mr-1" />
                          Modifier
                        </Button>
                      )}
                    </div>
                  </div>

                  {isEditing ? (
                    <div className="mt-3 space-y-3">
                      <div className="relative">
                        <Label htmlFor={cred.key} className="sr-only">{cred.label}</Label>
                        <Input
                          id={cred.key}
                          type={isSecret && !showSecret ? 'password' : 'text'}
                          placeholder={cred.placeholder}
                          value={credentialValues[cred.key] || ''}
                          onChange={(e) => setCredentialValues(prev => ({ ...prev, [cred.key]: e.target.value }))}
                          className="pr-10"
                        />
                        {isSecret && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                            onClick={() => toggleShowSecret(cred.key)}
                          >
                            {showSecret ? (
                              <EyeOff className="w-4 h-4" />
                            ) : (
                              <Eye className="w-4 h-4" />
                            )}
                          </Button>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <Button 
                          size="sm" 
                          variant="outline"
                          onClick={handleCancelEdit}
                        >
                          Annuler
                        </Button>
                        <p className="text-xs text-muted-foreground flex items-center">
                          Modifiez les credentials dans le fichier .env du serveur
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2">
                      <Badge variant="outline" className="font-mono text-xs">
                        ••••••••••••
                      </Badge>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Test de connexion */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {testResult?.success ? (
              <Wifi className="w-5 h-5 text-success" />
            ) : testResult ? (
              <WifiOff className="w-5 h-5 text-destructive" />
            ) : (
              <Wifi className="w-5 h-5 text-muted-foreground" />
            )}
            Test de connexion
          </CardTitle>
          <CardDescription>
            Vérifiez que les credentials permettent d'accéder à la boîte mail
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button 
            onClick={handleTestConnection} 
            disabled={isTesting}
            className="w-full"
          >
            {isTesting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Test en cours...
              </>
            ) : (
              <>
                <Wifi className="w-4 h-4 mr-2" />
                Tester la connexion Microsoft Graph
              </>
            )}
          </Button>

          {testResult && (
            <div className="space-y-3 pt-4 border-t">
              <h4 className="font-medium text-sm">Résultat du test</h4>
              
              <div className="grid gap-2">
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Tenant ID</span>
                  {testResult.details.tenantId ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Client ID</span>
                  {testResult.details.clientId ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Client Secret</span>
                  {testResult.details.clientSecret ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Adresse boîte mail</span>
                  {testResult.details.mailboxAddress ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Token OAuth2</span>
                  {testResult.details.tokenAcquired ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-muted">
                  <span className="text-sm">Accès boîte mail</span>
                  {testResult.details.mailboxAccessible ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
              </div>

              {testResult.success && testResult.mailboxInfo && (
                <div className="p-3 rounded-lg bg-success/10 border border-success/20">
                  <p className="text-sm font-medium text-success">Connexion réussie !</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Boîte mail : {testResult.mailboxInfo.displayName} ({testResult.mailboxInfo.mail})
                  </p>
                </div>
              )}

              {testResult.error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                  <p className="text-sm font-medium text-destructive">Erreur</p>
                  <p className="text-sm text-muted-foreground mt-1">{testResult.error}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Permissions requises</CardTitle>
          <CardDescription>Azure AD App Registration</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-success" />
              <code className="px-2 py-0.5 rounded bg-muted font-mono text-xs">Mail.Read</code>
              <span className="text-muted-foreground">- Application permission</span>
            </li>
          </ul>
        </CardContent>
      </Card>

      {/* Separator */}
      <div className="border-t border-border my-8" />

      {/* Section Tarifs Fournisseurs */}
      <div>
        <h2 className="section-title mb-2">Configuration Tarifs Fournisseurs</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Indexation des catalogues et tarifs fournisseurs pour la recherche automatique
        </p>
      </div>

      <SupplierTariffsConfig />
    </div>
  );
}