import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Building2, CheckCircle, Circle } from 'lucide-react';

interface Account {
  id: string;
  name: string;
  type: 'Production' | 'Démo' | 'Test';
  connectors: {
    sap: boolean;
    microsoft: boolean;
    salesforce: boolean;
  };
}

const mockAccounts: Account[] = [
  {
    id: '1',
    name: 'RONDOT – Production',
    type: 'Production',
    connectors: { sap: true, microsoft: true, salesforce: false }
  },
  {
    id: '2',
    name: 'RONDOT – Démo',
    type: 'Démo',
    connectors: { sap: true, microsoft: true, salesforce: true }
  },
  {
    id: '3',
    name: 'Compte Test',
    type: 'Test',
    connectors: { sap: false, microsoft: true, salesforce: false }
  }
];

interface AccountSelectionProps {
  onSelectAccount: (account: Account) => void;
}

export const AccountSelection = ({ onSelectAccount }: AccountSelectionProps) => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b bg-card px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">N</span>
          </div>
          <span className="font-semibold text-lg">NOVA</span>
          <Badge variant="outline" className="ml-2">RONDOT</Badge>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-foreground mb-2">
              Sélection du compte
            </h1>
            <p className="text-muted-foreground">
              Choisissez l'environnement sur lequel travailler
            </p>
          </div>

          <div className="space-y-4">
            {mockAccounts.map((account) => (
              <Card 
                key={account.id} 
                className="cursor-pointer hover:border-primary/50 hover:shadow-md transition-all"
                onClick={() => onSelectAccount(account)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
                        <Building2 className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <div>
                        <CardTitle className="text-lg">{account.name}</CardTitle>
                        <CardDescription>
                          {account.type === 'Production' && 'Environnement de production'}
                          {account.type === 'Démo' && 'Environnement de démonstration'}
                          {account.type === 'Test' && 'Environnement de test'}
                        </CardDescription>
                      </div>
                    </div>
                    <Badge 
                      variant={account.type === 'Production' ? 'default' : 'secondary'}
                    >
                      {account.type}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-sm text-muted-foreground mr-2">Connecteurs :</span>
                    
                    <Badge 
                      variant={account.connectors.sap ? 'default' : 'outline'} 
                      className={!account.connectors.sap ? 'opacity-40' : ''}
                    >
                      {account.connectors.sap ? (
                        <CheckCircle className="h-3 w-3 mr-1" />
                      ) : (
                        <Circle className="h-3 w-3 mr-1" />
                      )}
                      SAP
                    </Badge>
                    
                    <Badge 
                      variant={account.connectors.microsoft ? 'default' : 'outline'}
                      className={!account.connectors.microsoft ? 'opacity-40' : ''}
                    >
                      {account.connectors.microsoft ? (
                        <CheckCircle className="h-3 w-3 mr-1" />
                      ) : (
                        <Circle className="h-3 w-3 mr-1" />
                      )}
                      Microsoft
                    </Badge>
                    
                    <Badge 
                      variant={account.connectors.salesforce ? 'default' : 'outline'}
                      className={!account.connectors.salesforce ? 'opacity-40' : ''}
                    >
                      {account.connectors.salesforce ? (
                        <CheckCircle className="h-3 w-3 mr-1" />
                      ) : (
                        <Circle className="h-3 w-3 mr-1" />
                      )}
                      Salesforce
                    </Badge>
                  </div>
                  
                  <Button className="w-full" onClick={() => onSelectAccount(account)}>
                    Entrer dans ce compte
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
};
