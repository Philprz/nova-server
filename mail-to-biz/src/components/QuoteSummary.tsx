import { useState, useEffect } from 'react';
import { ArrowLeft, CheckCircle, Calculator, FileText, TrendingUp, Building2, Package, Search, Loader2, UserCheck, UserPlus } from 'lucide-react';
import { ProcessedEmail } from '@/types/email';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface SapClient {
  CardCode: string;
  CardName: string;
  Phone1?: string;
  EmailAddress?: string;
  similarity?: number;
}

interface ClientSearchResult {
  sap: {
    found: boolean;
    clients: SapClient[];
  };
  total_found: number;
}

interface QuoteSummaryProps {
  quote: ProcessedEmail;
  onValidate: () => void;
  onBack: () => void;
}

export function QuoteSummary({ quote, onValidate, onBack }: QuoteSummaryProps) {
  const doc = quote.preSapDocument;

  // État pour la recherche de clients SAP
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [sapClients, setSapClients] = useState<SapClient[]>([]);
  const [selectedClient, setSelectedClient] = useState<SapClient | null>(null);
  const [createNewClient, setCreateNewClient] = useState(false);
  const [searchPerformed, setSearchPerformed] = useState(false);

  // Données client extraites
  const clientName = doc?.businessPartner.CardName || 'Client inconnu';
  const clientEmail = doc?.businessPartner.ContactEmail || quote.email.from.emailAddress.address;

  // Articles extraits
  const articles = doc?.documentLines || [];

  // Marge par défaut
  const margin = 18;

  // Auto-sélection si le client SAP est déjà identifié par le matching backend
  useEffect(() => {
    if (doc?.businessPartner.CardCode) {
      setSelectedClient({
        CardCode: doc.businessPartner.CardCode,
        CardName: doc.businessPartner.CardName,
        EmailAddress: doc.businessPartner.ContactEmail,
      });
      setSearchPerformed(true);
    } else if (clientName && clientName !== 'Client inconnu') {
      setSearchQuery(clientName);
      searchClients(clientName);
    }
  }, [clientName, doc?.businessPartner.CardCode]);

  // Fonction de recherche de clients SAP
  const searchClients = async (query: string) => {
    if (!query || query.length < 2) return;

    setSearching(true);
    setSearchPerformed(true);

    try {
      const response = await fetch(`/api/clients/search_client/${encodeURIComponent(query)}`);

      if (response.ok) {
        const data: { success: boolean; search_results: ClientSearchResult } = await response.json();

        if (data.success && data.search_results.sap.found) {
          setSapClients(data.search_results.sap.clients);
        } else {
          setSapClients([]);
        }
      } else {
        setSapClients([]);
      }
    } catch (error) {
      console.error('Erreur recherche clients:', error);
      setSapClients([]);
    } finally {
      setSearching(false);
    }
  };

  // Sélectionner un client existant
  const handleSelectClient = (client: SapClient) => {
    setSelectedClient(client);
    setCreateNewClient(false);
  };

  // Créer un nouveau client
  const handleCreateNew = () => {
    setSelectedClient(null);
    setCreateNewClient(true);
  };

  // Déterminer le type de client à afficher
  const getClientStatus = () => {
    if (selectedClient) {
      return { type: 'existing', label: 'Client SAP sélectionné', color: 'bg-success/10 text-success' };
    }
    if (createNewClient) {
      return { type: 'new', label: 'Nouveau client', color: 'bg-warning/10 text-warning' };
    }
    if (sapClients.length > 0) {
      return { type: 'found', label: `${sapClients.length} client(s) trouvé(s)`, color: 'bg-primary/10 text-primary' };
    }
    return { type: 'unknown', label: 'Client à identifier', color: 'bg-muted text-muted-foreground' };
  };

  const clientStatus = getClientStatus();

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl mx-auto">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">Synthèse du devis</h1>
        <p className="text-muted-foreground">Pré-analyse automatique avant création SAP</p>
      </div>

      {/* Client Block avec recherche SAP */}
      <Card className="card-elevated">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-primary" />
              Client
            </span>
            <Badge className={clientStatus.color}>
              {clientStatus.type === 'existing' && <UserCheck className="w-3 h-3 mr-1" />}
              {clientStatus.type === 'new' && <UserPlus className="w-3 h-3 mr-1" />}
              {clientStatus.label}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Informations client détectées */}
          <div className="grid grid-cols-2 gap-4 p-3 bg-muted/30 rounded-lg">
            <div>
              <p className="text-xs text-muted-foreground">Détecté dans l'email</p>
              <p className="font-medium">{clientName}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Email</p>
              <p className="font-medium text-sm">{clientEmail}</p>
            </div>
          </div>

          {/* Barre de recherche SAP */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Rechercher un client dans SAP..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchClients(searchQuery)}
                className="pl-10"
              />
            </div>
            <Button
              variant="outline"
              onClick={() => searchClients(searchQuery)}
              disabled={searching || searchQuery.length < 2}
            >
              {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Rechercher'}
            </Button>
          </div>

          {/* Résultats de recherche SAP */}
          {searchPerformed && (
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-muted/50 px-3 py-2 text-sm font-medium flex items-center justify-between">
                <span>Clients SAP correspondants</span>
                {sapClients.length === 0 && !searching && (
                  <Badge variant="outline" className="text-warning border-warning">
                    Aucun trouvé
                  </Badge>
                )}
              </div>

              {searching ? (
                <div className="p-4 text-center text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                  Recherche en cours...
                </div>
              ) : sapClients.length > 0 ? (
                <div className="divide-y max-h-48 overflow-y-auto">
                  {sapClients.map((client) => (
                    <div
                      key={client.CardCode}
                      className={`p-3 cursor-pointer hover:bg-muted/50 transition-colors flex items-center justify-between ${
                        selectedClient?.CardCode === client.CardCode ? 'bg-primary/10 border-l-2 border-l-primary' : ''
                      }`}
                      onClick={() => handleSelectClient(client)}
                    >
                      <div>
                        <p className="font-medium">{client.CardName}</p>
                        <p className="text-xs text-muted-foreground">
                          Code: {client.CardCode}
                          {client.EmailAddress && ` • ${client.EmailAddress}`}
                        </p>
                      </div>
                      {selectedClient?.CardCode === client.CardCode && (
                        <CheckCircle className="w-5 h-5 text-primary" />
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 text-center text-muted-foreground text-sm">
                  Aucun client trouvé dans SAP pour "{searchQuery}"
                </div>
              )}

              {/* Option créer nouveau client */}
              <div className="border-t">
                <button
                  className={`w-full p-3 text-left hover:bg-muted/50 transition-colors flex items-center gap-2 ${
                    createNewClient ? 'bg-warning/10 border-l-2 border-l-warning' : ''
                  }`}
                  onClick={handleCreateNew}
                >
                  <UserPlus className="w-4 h-4 text-warning" />
                  <span className="font-medium">Créer un nouveau client</span>
                  {createNewClient && <CheckCircle className="w-4 h-4 text-warning ml-auto" />}
                </button>
              </div>
            </div>
          )}

          {/* Client sélectionné */}
          {selectedClient && (
            <div className="p-3 bg-success/10 border border-success/20 rounded-lg">
              <p className="text-sm font-medium text-success flex items-center gap-2">
                <UserCheck className="w-4 h-4" />
                Client SAP sélectionné
              </p>
              <p className="font-medium mt-1">{selectedClient.CardName}</p>
              <p className="text-xs text-muted-foreground">Code: {selectedClient.CardCode}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Articles Block */}
      <Card className="card-elevated">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Package className="w-5 h-5 text-primary" />
            Articles détectés
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Référence</TableHead>
                <TableHead>Désignation</TableHead>
                <TableHead className="text-right">Quantité</TableHead>
                <TableHead className="text-right">Prix estimé</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {articles.length > 0 ? (
                articles.map((line) => (
                  <TableRow key={line.LineNum}>
                    <TableCell className="font-mono text-sm">
                      {line.ItemCode || 'À définir'}
                    </TableCell>
                    <TableCell>{line.ItemDescription}</TableCell>
                    <TableCell className="text-right">
                      {line.Quantity} {line.UnitOfMeasure}
                    </TableCell>
                    <TableCell className="text-right font-medium text-muted-foreground">
                      À calculer
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    Aucun article détecté. Analyse manuelle requise.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pricing Block */}
      <Card className="card-elevated border-primary/20">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center gap-2">
              <Calculator className="w-5 h-5 text-primary" />
              Pricing
            </span>
            <Badge className="bg-primary/10 text-primary border-primary/20">
              <TrendingUp className="w-3 h-3 mr-1" />
              Calcul automatique
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-6">
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Sous-total HT</p>
              <p className="text-xl font-semibold text-muted-foreground">
                À calculer
              </p>
              <p className="text-xs text-muted-foreground mt-1">Nécessite tarif SAP</p>
            </div>
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Marge appliquée</p>
              <p className="text-xl font-semibold text-success">{margin}%</p>
            </div>
            <div className="text-center p-4 bg-primary/10 rounded-lg border border-primary/20">
              <p className="text-sm text-muted-foreground mb-1">Prix total estimé</p>
              <p className="text-2xl font-bold text-muted-foreground">
                À calculer
              </p>
              <p className="text-xs text-muted-foreground mt-1">Après récupération des prix</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Why this price Block */}
      <Card className="card-elevated bg-muted/30">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileText className="w-5 h-5 text-primary" />
            Pourquoi ce prix ?
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-warning mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">Informations extraites par IA</p>
                <p className="text-sm text-muted-foreground">
                  {articles.length} article{articles.length > 1 ? 's' : ''} détecté{articles.length > 1 ? 's' : ''}
                  dans l'email de {clientName}. Classification: {doc?.meta.confidenceLevel || 'low'} confidence.
                </p>
              </div>
            </div>

            <Separator />

            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">Tarification SAP requise</p>
                <p className="text-sm text-muted-foreground">
                  Les prix seront récupérés depuis SAP B1 lors de la validation. Marge {margin}% sera appliquée selon la catégorie client.
                </p>
              </div>
            </div>

            <Separator />

            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">Délai de livraison</p>
                <p className="text-sm text-muted-foreground">
                  {doc?.deliveryLeadTimeDays
                    ? `${doc.deliveryLeadTimeDays} jours demandés`
                    : 'Non spécifié - délai standard appliqué'}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex justify-between items-center pt-4">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Retour
        </Button>
        <Button
          onClick={onValidate}
          size="lg"
          disabled={!doc || articles.length === 0 || (!selectedClient && !createNewClient)}
        >
          <CheckCircle className="w-4 h-4 mr-2" />
          {!selectedClient && !createNewClient
            ? 'Sélectionnez un client'
            : articles.length > 0
              ? 'Créer le devis SAP'
              : 'Extraction incomplète'}
        </Button>
      </div>
    </div>
  );
}
