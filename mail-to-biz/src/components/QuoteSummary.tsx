import { useState, useEffect } from 'react';
import { ArrowLeft, CheckCircle, Calculator, FileText, TrendingUp, Building2, Package, Search, Loader2, UserCheck, UserPlus, AlertCircle, Plus, RefreshCw, Mail, Paperclip, Eye, ChevronDown, ChevronUp } from 'lucide-react';
import { ProcessedEmail } from '@/types/email';
import { CreateItemDialog } from './CreateItemDialog';
import { PriceEditorDialog } from './PriceEditorDialog';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { recalculatePricing, fetchGraphEmail } from '@/lib/graphApi';
import type { GraphEmail } from '@/lib/graphApi';
import { toast } from 'sonner';

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

  // État pour la recherche d'articles SAP
  const [searchingArticle, setSearchingArticle] = useState<{[key: number]: boolean}>({});
  const [articleStatus, setArticleStatus] = useState<{[key: number]: {found: boolean, message: string, itemCode?: string}}>({});

  // État pour le recalcul des prix
  const [recalculating, setRecalculating] = useState(false);

  // État pour la visualisation de l'email source
  const [showEmailContent, setShowEmailContent] = useState(false);
  const [viewingAttachment, setViewingAttachment] = useState<{ name: string; url: string; contentType: string } | null>(null);
  const [loadingAttachment] = useState<string | null>(null);
  const [fullEmail, setFullEmail] = useState<GraphEmail | null>(null);
  const [loadingEmail, setLoadingEmail] = useState(false);

  // État pour le dialog de création d'article
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [articleToCreate, setArticleToCreate] = useState<{lineNum: number, itemCode: string, itemDescription: string} | null>(null);

  // Données client extraites
  const clientName = doc?.businessPartner.CardName || 'Client inconnu';
  const clientEmail = doc?.businessPartner.ContactEmail || quote.email.from.emailAddress.address;

  // Articles extraits avec enrichissement automatique des prix
  const [enrichedArticles, setEnrichedArticles] = useState<any[]>([]);

  // Marge par défaut RONDOT-SAS (min 35%, cible 40%, max 45%)
  const margin = 40;

  // ✨ NOUVEAUTÉ : Enrichir automatiquement les articles avec les prix depuis product_matches
  useEffect(() => {
    const baseArticles = doc?.documentLines || [];
    const productMatches = (quote.analysisResult?.product_matches as any[]) || [];

    if (productMatches.length > 0) {
      // Créer une map des prix par item_code
      const priceMap = new Map();
      productMatches.forEach((pm: any) => {
        priceMap.set(pm.item_code, {
          unit_price: pm.unit_price,
          line_total: pm.line_total,
          pricing_case: pm.pricing_case,
          pricing_justification: pm.pricing_justification,
          margin_applied: pm.margin_applied,
          requires_validation: pm.requires_validation,
          validation_reason: pm.validation_reason,
          supplier_price: pm.supplier_price,
          decision_id: pm.decision_id,
          historical_sales: pm.historical_sales,
          sap_avg_price: pm.sap_avg_price,
          last_sale_price: pm.last_sale_price,
          last_sale_date: pm.last_sale_date,
          average_price_others: pm.average_price_others,
          alerts: pm.alerts,
          confidence_score: pm.confidence_score,
        });
      });

      // Enrichir les articles avec les prix et toutes les métadonnées pricing
      const enriched = baseArticles.map((article: any) => {
        const pricing = priceMap.get(article.ItemCode);
        if (pricing) {
          return {
            ...article,
            ...pricing,  // Copie TOUS les champs pricing (supplier_price, decision_id, historical_sales, sap_avg_price, etc.)
          };
        }
        return article;
      });

      setEnrichedArticles(enriched);
    } else {
      setEnrichedArticles(baseArticles);
    }
  }, [doc?.documentLines, quote.analysisResult?.product_matches]);

  // Utiliser les articles enrichis
  const articles = enrichedArticles;

  // ✨ Helpers pricing automatique (Phase 5)
  const calculateTotals = () => {
    if (!articles || articles.length === 0) {
      return { subtotal: 0, avgMargin: margin, total: 0 };
    }

    let subtotal = 0;
    let totalMargin = 0;
    let count = 0;

    articles.forEach((line: any) => {
      if (line.unit_price && line.Quantity) {
        const lineTotal = line.unit_price * line.Quantity;
        subtotal += lineTotal;

        if (line.margin_applied) {
          totalMargin += line.margin_applied;
          count++;
        }
      }
    });

    const avgMargin = count > 0 ? totalMargin / count : margin;
    return { subtotal, avgMargin, total: subtotal };
  };

  const getCasVariant = (casType?: string): "default" | "secondary" | "outline" | "destructive" => {
    switch (casType) {
      case 'CAS_1_HC': return 'default';      // Vert - historique stable
      case 'CAS_2_HCM': return 'outline';     // Orange - variation prix
      case 'CAS_3_HA': return 'secondary';    // Bleu - prix moyen
      case 'CAS_4_NP': return 'destructive';  // Rouge - nouveau produit
      default: return 'default';
    }
  };

  const formatCasLabel = (casType?: string): string => {
    switch (casType) {
      case 'CAS_1_HC': return 'Historique Client';
      case 'CAS_2_HCM': return 'Prix Modifié';
      case 'CAS_3_HA': return 'Prix Moyen';
      case 'CAS_4_NP': return 'Nouveau Produit';
      case 'SAP_FUNCTION': return 'SAP Direct';
      default: return 'Prix calculé';
    }
  };

  const totals = calculateTotals();

  // ✨ NOUVEAUTÉ : Pré-initialiser articleStatus pour les produits déjà trouvés
  useEffect(() => {
    const productMatches = (quote.analysisResult?.product_matches as any[]) || [];
    const baseArticles = doc?.documentLines || [];

    if (productMatches.length > 0 && baseArticles.length > 0) {
      const initialStatus: {[key: number]: {found: boolean, message: string, itemCode?: string}} = {};

      // Créer une map des product_matches par item_code
      const matchMap = new Map();
      productMatches.forEach((pm: any) => {
        if (pm.item_code && !pm.not_found_in_sap) {
          matchMap.set(pm.item_code, {
            found: true,
            message: 'Trouvé automatiquement',
            itemCode: pm.item_code
          });
        }
      });

      // Marquer les articles trouvés en utilisant leur LineNum
      baseArticles.forEach((article: any) => {
        if (article.ItemCode && matchMap.has(article.ItemCode)) {
          initialStatus[article.LineNum] = matchMap.get(article.ItemCode);
        }
      });

      setArticleStatus(initialStatus);
    }
  }, [quote.analysisResult?.product_matches, doc?.documentLines]);

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
      const response = await fetch(`/api/clients/search_clients?q=${encodeURIComponent(query)}&source=sap&limit=10`);

      if (response.ok) {
        const data = await response.json();

        if (data.success && data.results && data.results.length > 0) {
          // Adapter le format de réponse
          const sapClients = data.results.map((client: any) => ({
            CardCode: client.CardCode,
            CardName: client.CardName,
            EmailAddress: client.EmailAddress || client.Email,
            Phone1: client.Phone1,
            similarity: client.similarity
          }));
          setSapClients(sapClients);
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

  // Ouvrir/fermer l'email source — fetche le corps complet + attachments si nécessaire
  const handleToggleEmail = async () => {
    const opening = !showEmailContent;
    setShowEmailContent(opening);

    if (!opening || fullEmail) return; // Déjà chargé ou on ferme

    const needsFullBody = !quote.email.body?.content || quote.email.body.content === quote.email.bodyPreview;
    const needsAttachments = quote.email.hasAttachments && quote.email.attachments.length === 0;

    if (!needsFullBody && !needsAttachments) return; // Données déjà disponibles

    setLoadingEmail(true);
    try {
      const result = await fetchGraphEmail(quote.email.id);
      if (result.success && result.data) {
        setFullEmail(result.data);
      }
    } catch {
      toast.error('Impossible de charger le contenu de l\'email');
    } finally {
      setLoadingEmail(false);
    }
  };

  // Ouvrir une pièce jointe dans le viewer via l'endpoint de streaming
  const openAttachment = (att: { id: string; name: string; contentType: string; size: number; contentBytes?: string }) => {
    const emailId = encodeURIComponent(quote.email.id);
    const attId = encodeURIComponent(att.id);
    const streamUrl = `/api/graph/emails/${emailId}/attachments/${attId}/stream`;
    setViewingAttachment({ name: att.name, url: streamUrl, contentType: att.contentType });
  };

  // Recalculer les prix automatiquement
  const handleRecalculatePricing = async () => {
    if (!quote.email?.id) {
      toast.error("ID de l'email introuvable");
      return;
    }

    setRecalculating(true);

    try {
      toast.info("Calcul des prix en cours...");
      const result = await recalculatePricing(quote.email.id);

      if (result.success && result.analysis) {
        toast.success(
          `Prix calculés avec succès ! ${result.pricing_calculated}/${result.total_products} produits (${result.duration_ms.toFixed(0)}ms)`
        );

        // ✨ NOUVEAUTÉ : Mettre à jour l'état local au lieu de recharger la page
        if (result.analysis.product_matches) {
          // Ré-enrichir les articles avec les nouveaux prix
          const baseArticles = doc?.documentLines || [];
          const productMatches = result.analysis.product_matches;

          const priceMap = new Map();
          productMatches.forEach((pm: any) => {
            priceMap.set(pm.item_code, {
              unit_price: pm.unit_price,
              line_total: pm.line_total,
              pricing_case: pm.pricing_case,
              margin_applied: pm.margin_applied,
              requires_validation: pm.requires_validation
            });
          });

          const enriched = baseArticles.map((article: any) => {
            const pricing = priceMap.get(article.ItemCode);
            if (pricing) {
              return {
                ...article,
                unit_price: pricing.unit_price,
                line_total: pricing.line_total,
                pricing_case: pricing.pricing_case,
                margin_applied: pricing.margin_applied,
                requires_validation: pricing.requires_validation
              };
            }
            return article;
          });

          setEnrichedArticles(enriched);
        }
      } else {
        toast.error("Échec du calcul des prix");
      }
    } catch (error: any) {
      console.error('Recalculate pricing error:', error);
      toast.error(error.message || "Erreur lors du calcul des prix");
    } finally {
      setRecalculating(false);
    }
  };

  // Rechercher un article dans SAP
  const searchArticle = async (lineNum: number, itemCode: string, itemDescription: string) => {
    if (!itemCode || itemCode === 'À définir') {
      setArticleStatus({
        ...articleStatus,
        [lineNum]: { found: false, message: 'Référence manquante' }
      });
      return;
    }

    setSearchingArticle({ ...searchingArticle, [lineNum]: true });

    try {
      // Rechercher l'article dans SAP par ItemCode
      const response = await fetch(`/api/sap/items?search=${encodeURIComponent(itemCode)}&limit=1`);

      if (response.ok) {
        const data = await response.json();

        if (data.items && data.items.length > 0) {
          const item = data.items[0];
          setArticleStatus({
            ...articleStatus,
            [lineNum]: {
              found: true,
              message: `Trouvé: ${item.ItemName}`,
              itemCode: item.ItemCode
            }
          });
        } else {
          setArticleStatus({
            ...articleStatus,
            [lineNum]: {
              found: false,
              message: 'Article non trouvé dans SAP'
            }
          });
        }
      } else {
        setArticleStatus({
          ...articleStatus,
          [lineNum]: { found: false, message: 'Erreur de recherche' }
        });
      }
    } catch (error) {
      console.error('Erreur recherche article:', error);
      setArticleStatus({
        ...articleStatus,
        [lineNum]: { found: false, message: 'Erreur de connexion' }
      });
    } finally {
      setSearchingArticle({ ...searchingArticle, [lineNum]: false });
    }
  };

  // Ouvrir le dialog de création d'article
  const createArticle = (lineNum: number, itemCode: string, itemDescription: string) => {
    setArticleToCreate({ lineNum, itemCode, itemDescription });
    setCreateDialogOpen(true);
  };

  // Gérer le succès de la création d'article
  const handleArticleCreated = (createdItemCode: string) => {
    if (articleToCreate) {
      // Marquer l'article comme trouvé après création
      setArticleStatus({
        ...articleStatus,
        [articleToCreate.lineNum]: {
          found: true,
          message: `Article créé: ${createdItemCode}`,
          itemCode: createdItemCode
        }
      });
      setArticleToCreate(null);
    }
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

      {/* Email source */}
      <Card className="card-elevated">
        <CardHeader
          className="pb-3 cursor-pointer select-none"
          onClick={handleToggleEmail}
        >
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center gap-2">
              <Mail className="w-5 h-5 text-primary" />
              Email source
            </span>
            <div className="flex items-center gap-2">
              {quote.email.hasAttachments && (
                <Badge variant="outline" className="text-xs">
                  <Paperclip className="w-3 h-3 mr-1" />
                  {fullEmail ? fullEmail.attachments.length : quote.email.attachments.length || '?'} PJ
                </Badge>
              )}
              {showEmailContent ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </div>
          </CardTitle>
          <div className="grid grid-cols-2 gap-1 text-sm mt-1 pointer-events-none">
            <div>
              <span className="text-muted-foreground">De : </span>
              <span className="font-medium">{quote.email.from.emailAddress.name}</span>
              <span className="text-muted-foreground text-xs ml-1">({quote.email.from.emailAddress.address})</span>
            </div>
            <div>
              <span className="text-muted-foreground">Reçu : </span>
              <span>{new Date(quote.email.receivedDateTime).toLocaleString('fr-FR')}</span>
            </div>
            <div className="col-span-2">
              <span className="text-muted-foreground">Objet : </span>
              <span className="font-medium">{quote.email.subject}</span>
            </div>
          </div>
        </CardHeader>

        {showEmailContent && (
          <CardContent className="space-y-4 pt-0">
            <Separator />

            {loadingEmail ? (
              <div className="flex items-center justify-center py-6 text-muted-foreground gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Chargement du contenu...
              </div>
            ) : (
              <>
                {/* Corps de l'email */}
                <div>
                  <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">Corps du message</p>
                  <div className="border rounded overflow-hidden bg-white">
                    {(() => {
                      const bodyType = fullEmail?.body_content_type || quote.email.body?.contentType;
                      const isHtml = bodyType === 'html' || bodyType === 'HTML';
                      if (isHtml) {
                        // Utiliser l'endpoint /body pour éviter les restrictions de sandbox
                        const bodyUrl = `/api/graph/emails/${encodeURIComponent(quote.email.id)}/body`;
                        return (
                          <iframe
                            src={bodyUrl}
                            className="w-full"
                            style={{ height: '300px', border: 'none' }}
                            title="Contenu email"
                          />
                        );
                      }
                      const bodyContent = fullEmail?.body_content || quote.email.body?.content;
                      return (
                        <pre className="p-3 text-sm text-foreground whitespace-pre-wrap max-h-64 overflow-y-auto font-sans">
                          {bodyContent || quote.email.bodyPreview || '(Contenu non disponible)'}
                        </pre>
                      );
                    })()}
                  </div>
                </div>

                {/* Pièces jointes */}
                {(() => {
                  const attachments = fullEmail
                    ? fullEmail.attachments.map(a => ({ id: a.id, name: a.name, contentType: a.content_type, size: a.size, contentBytes: a.content_bytes }))
                    : quote.email.attachments;
                  if (attachments.length === 0 && !quote.email.hasAttachments) return null;
                  return (
                    <div>
                      <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">
                        Pièces jointes {attachments.length === 0 && quote.email.hasAttachments ? '(chargement…)' : ''}
                      </p>
                      <div className="space-y-2">
                        {attachments.map((att) => (
                          <div key={att.id} className="flex items-center justify-between p-2 border rounded bg-muted/20">
                            <div className="flex items-center gap-2 min-w-0">
                              <Paperclip className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                              <span className="text-sm font-medium truncate">{att.name}</span>
                              <span className="text-xs text-muted-foreground flex-shrink-0">
                                ({Math.round(att.size / 1024)} Ko)
                              </span>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={(e) => { e.stopPropagation(); openAttachment(att); }}
                              className="ml-2 flex-shrink-0"
                            >
                              <Eye className="w-3 h-3 mr-1" />
                              Visualiser
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
          </CardContent>
        )}
      </Card>

      {/* Dialog viewer pièce jointe */}
      {viewingAttachment && (
        <Dialog open onOpenChange={() => setViewingAttachment(null)}>
          <DialogContent className="max-w-5xl p-0 overflow-hidden" style={{ height: '90vh' }}>
            <DialogHeader className="px-4 py-3 border-b flex-row items-center justify-between">
              <DialogTitle className="flex items-center gap-2 text-base">
                <Paperclip className="w-4 h-4" />
                {viewingAttachment.name}
              </DialogTitle>
              <a
                href={viewingAttachment.url}
                download={viewingAttachment.name}
                className="text-xs text-muted-foreground hover:text-foreground underline mr-8"
                onClick={(e) => e.stopPropagation()}
              >
                Télécharger
              </a>
            </DialogHeader>
            {viewingAttachment.contentType.startsWith('image/') ? (
              <div className="flex items-center justify-center p-4 overflow-auto" style={{ height: 'calc(90vh - 60px)' }}>
                <img
                  src={viewingAttachment.url}
                  alt={viewingAttachment.name}
                  className="max-w-full max-h-full object-contain"
                />
              </div>
            ) : (
              <iframe
                src={viewingAttachment.url}
                className="w-full"
                style={{ height: 'calc(90vh - 60px)', border: 'none' }}
                title={viewingAttachment.name}
              />
            )}
          </DialogContent>
        </Dialog>
      )}

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
                <TableHead className="text-center">Statut SAP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {articles.length > 0 ? (
                articles.map((line) => {
                  const status = articleStatus[line.LineNum];
                  const isSearching = searchingArticle[line.LineNum];

                  return (
                    <TableRow key={line.LineNum}>
                      <TableCell className="font-mono text-sm">
                        {line.ItemCode || 'À définir'}
                      </TableCell>
                      <TableCell>{line.ItemDescription}</TableCell>
                      <TableCell className="text-right">
                        {line.Quantity} {line.UnitOfMeasure}
                      </TableCell>
                      <TableCell className="text-right">
                        <PriceEditorDialog
                          line={line}
                          onPriceUpdated={(newPrice) => {
                            // Mettre à jour le prix dans la ligne localement
                            line.unit_price = newPrice;
                            line.line_total = newPrice * (line.Quantity || 1);
                            line.pricing_case = 'CAS_MANUAL';
                          }}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="flex items-center justify-center gap-2">
                          {!status ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => searchArticle(line.LineNum, line.ItemCode || '', line.ItemDescription)}
                              disabled={isSearching || !line.ItemCode || line.ItemCode === 'À définir'}
                            >
                              {isSearching ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <>
                                  <Search className="w-3 h-3 mr-1" />
                                  Vérifier
                                </>
                              )}
                            </Button>
                          ) : status.found ? (
                            <Badge className="bg-success/10 text-success border-success/20">
                              <CheckCircle className="w-3 h-3 mr-1" />
                              Trouvé
                            </Badge>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-warning border-warning">
                                <AlertCircle className="w-3 h-3 mr-1" />
                                Non trouvé
                              </Badge>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => createArticle(line.LineNum, line.ItemCode || '', line.ItemDescription)}
                              >
                                <Plus className="w-3 h-3 mr-1" />
                                Créer
                              </Button>
                            </div>
                          )}
                        </div>
                        {status && (
                          <p className="text-xs text-muted-foreground mt-1">{status.message}</p>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
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
            <Button
              variant={totals.subtotal > 0 ? "outline" : "default"}
              size="sm"
              onClick={handleRecalculatePricing}
              disabled={recalculating}
              className="gap-2"
            >
              {recalculating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Calcul en cours...
                </>
              ) : totals.subtotal > 0 ? (
                <>
                  <RefreshCw className="w-4 h-4" />
                  Recalculer
                </>
              ) : (
                <>
                  <TrendingUp className="w-4 h-4" />
                  Calculer les prix
                </>
              )}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-6">
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Sous-total HT</p>
              {totals.subtotal > 0 ? (
                <p className="text-xl font-semibold text-foreground">
                  {totals.subtotal.toFixed(2)} €
                </p>
              ) : (
                <p className="text-xl font-semibold text-muted-foreground">
                  À calculer
                </p>
              )}
              {totals.subtotal === 0 && (
                <p className="text-xs text-muted-foreground mt-1">En attente pricing</p>
              )}
            </div>
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Marge moyenne</p>
              <p className="text-xl font-semibold text-success">{totals.avgMargin.toFixed(0)}%</p>
            </div>
            <div className="text-center p-4 bg-primary/10 rounded-lg border border-primary/20">
              <p className="text-sm text-muted-foreground mb-1">Total HT</p>
              {totals.total > 0 ? (
                <p className="text-2xl font-bold text-foreground">
                  {totals.total.toFixed(2)} €
                </p>
              ) : (
                <p className="text-2xl font-bold text-muted-foreground">
                  À calculer
                </p>
              )}
              {totals.total > 0 && (
                <p className="text-xs text-success mt-1">Calculé automatiquement</p>
              )}
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

      {/* Dialog de création d'article */}
      <CreateItemDialog
        open={createDialogOpen}
        onClose={() => {
          setCreateDialogOpen(false);
          setArticleToCreate(null);
        }}
        onSuccess={handleArticleCreated}
        initialItemCode={articleToCreate?.itemCode || ''}
        initialDescription={articleToCreate?.itemDescription || ''}
      />
    </div>
  );
}
