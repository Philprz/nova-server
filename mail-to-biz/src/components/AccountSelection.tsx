import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AlertCircle, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export const AccountSelection = () => {
  const { login } = useAuth();
  const [username, setUsername]     = useState('');
  const [password, setPassword]     = useState('');
  const [companyDb, setCompanyDb]   = useState('RON_20260109');
  const [showCompany, setShowCompany] = useState(false);
  const [isLoading, setIsLoading]   = useState(false);
  const [error, setError]           = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    const result = await login({
      sap_username:   username,
      sap_password:   password,
      sap_company_db: companyDb,
    });
    setIsLoading(false);
    if (!result.success) {
      setError(result.error ?? 'Erreur de connexion');
    }
    // On success, AuthContext state changes → Index.tsx re-renders to show inbox
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b bg-card px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">N</span>
          </div>
          <span className="font-semibold text-lg">NOVA</span>
        </div>
      </header>

      {/* Login form */}
      <main className="flex-1 flex items-center justify-center p-6">
        <Card className="w-full max-w-sm">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Connexion</CardTitle>
            <CardDescription>Entrez vos identifiants SAP pour accéder à NOVA</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Identifiant SAP</Label>
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="manager"
                  required
                  disabled={isLoading}
                  autoComplete="username"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Mot de passe SAP</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={isLoading}
                  autoComplete="current-password"
                />
              </div>

              {/* Société collapsible */}
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowCompany(v => !v)}
              >
                {showCompany ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                Société SAP
              </button>

              {showCompany && (
                <div className="space-y-2">
                  <Label htmlFor="companyDb">Base de données SAP</Label>
                  <Input
                    id="companyDb"
                    type="text"
                    value={companyDb}
                    onChange={e => setCompanyDb(e.target.value)}
                    placeholder="RON_20260109"
                    disabled={isLoading}
                  />
                </div>
              )}

              {error && (
                <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Connexion en cours...</>
                ) : (
                  'Se connecter'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};
