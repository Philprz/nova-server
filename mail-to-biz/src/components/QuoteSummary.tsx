import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, CheckCircle, Calculator, FileText, TrendingUp, Building2, Package, Search, Loader2, UserCheck, UserPlus, AlertCircle, AlertTriangle, RefreshCw, Mail, Paperclip, RotateCcw, X } from 'lucide-react';
import { ProcessedEmail } from '@/types/email';
import { CreateItemDialog } from './CreateItemDialog';
import { PriceEditorDialog } from './PriceEditorDialog';
import { EmailSourceTab } from './EmailSourceTab';
import { AttachmentsTab } from './AttachmentsTab';
import { ExtractedDataTab } from './ExtractedDataTab';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { recalculatePricing, excludeProduct, setManualCode, retrySearchProduct, updateProductQuantity, loadDraftState, saveDraftState } from '@/lib/graphApi';
import { previewSAPQuotation, createSAPQuotation, PreviewResponse, CreateQuoteRequest, getExistingQuoteForEmail, ExistingQuoteInfo } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
  onValidate: (sapDocNum?: number) => void;
  onBack: () => void;
  onReanalyze?: () => Promise<void>;
  isReanalyzing?: boolean;
  isProcessed?: boolean;
}

export function QuoteSummary({ quote, onValidate, onBack, onReanalyze, isReanalyzing = false, isProcessed = false }: QuoteSummaryProps) {
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

  // État pour les quantités modifiées
  const [quantityOverrides, setQuantityOverrides] = useState<{[lineNum: number]: number}>({});

  // État pour les articles ignorés (exclus du devis)
  const [ignoredItems, setIgnoredItems] = useState<{[lineNum: number]: boolean}>({});

  // État pour la saisie manuelle du code SAP
  const [showManualInput, setShowManualInput] = useState<{[lineNum: number]: boolean}>({});
  const [manualCodeInput, setManualCodeInput] = useState<{[lineNum: number]: string}>({});
  const [manualCodeLoading, setManualCodeLoading] = useState<{[lineNum: number]: boolean}>({});

  // État pour les résultats de relance de recherche
  const [retryResults, setRetryResults] = useState<{[lineNum: number]: any[]}>({});
  const [showRetryResults, setShowRetryResults] = useState<{[lineNum: number]: boolean}>({});
  const [retryLoading, setRetryLoading] = useState<{[lineNum: number]: boolean}>({});

  // État pour le recalcul des prix
  const [recalculating, setRecalculating] = useState(false);

  // État pour la modale de prévisualisation SAP
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Devis SAP déjà créé pour cet email
  const [existingQuote, setExistingQuote] = useState<ExistingQuoteInfo | null>(null);

  // Debounce pour la sauvegarde des quantités
  const saveQtyTimeouts = useRef<{[key: string]: ReturnType<typeof setTimeout>}>({});

  // Debounce pour la sauvegarde du draft state complet
  const saveDraftTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Flag : un client a été chargé depuis le draft (empêche l'auto-sélection de l'écraser)
  const draftClientLoaded = useRef(false);

  // État pour le dialog de création d'article
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [articleToCreate, setArticleToCreate] = useState<{lineNum: number, itemCode: string, itemDescription: string} | null>(null);

  // Prix manuellement fixés (protège contre Recalculer)
  const [manualPriceOverrides, setManualPriceOverrides] = useState<{[itemCode: string]: number}>({});

  // Lignes fixes : Emballage et Transport
  const [emballagePrice, setEmballagePrice] = useState<number>(20);
  const [transportPriceOverride, setTransportPriceOverride] = useState<number | null>(null);
  const [editingFixedLine, setEditingFixedLine] = useState<'emballage' | 'transport' | null>(null);
  const [fixedLineInputValue, setFixedLineInputValue] = useState<string>('');

  // Données client extraites
  const clientName = doc?.businessPartner.CardName || 'Client inconnu';
  const clientEmail = doc?.businessPartner.ContactEmail || quote.email.from.emailAddress.address;

  // Articles extraits avec enrichissement automatique des prix
  const [enrichedArticles, setEnrichedArticles] = useState<any[]>([]);

  // Marge par défaut RONDOT-SAS (min 35%, cible 40%, max 45%)
  const margin = 40;

  /** Sauvegarde l'état UI courant (debounce 800ms) */
  const triggerDraftSave = (
    overrides: {[lineNum: number]: number},
    ignored: {[lineNum: number]: boolean},
    client: SapClient | null,
  ) => {
    if (saveDraftTimeout.current) clearTimeout(saveDraftTimeout.current);
    saveDraftTimeout.current = setTimeout(async () => {
      try {
        const qtyMap: Record<string, number> = {};
        Object.entries(overrides).forEach(([k, v]) => { qtyMap[k] = v; });
        const ignoredNums = Object.entries(ignored)
          .filter(([, v]) => v)
          .map(([k]) => Number(k));
        await saveDraftState(quote.email.id, {
          quantity_overrides: qtyMap,
          ignored_line_nums: ignoredNums,
          selected_client_code: client?.CardCode ?? null,
          selected_client_name: client?.CardName ?? null,
        });
      } catch (e) {
        // Non bloquant
      }
    }, 800);
  };

  // Chargement au montage : draft state + statut SAP existant
  useEffect(() => {
    // 1. Draft state (quantités, articles ignorés, client)
    loadDraftState(quote.email.id).then((draft) => {
      if (!draft.found) return;
      if (draft.quantity_overrides && Object.keys(draft.quantity_overrides).length > 0) {
        const numKeys: {[k: number]: number} = {};
        Object.entries(draft.quantity_overrides).forEach(([k, v]) => { numKeys[Number(k)] = v; });
        setQuantityOverrides(numKeys);
      }
      if (draft.ignored_line_nums && draft.ignored_line_nums.length > 0) {
        const map: {[k: number]: boolean} = {};
        draft.ignored_line_nums.forEach((n) => { map[n] = true; });
        setIgnoredItems(map);
      }
      if (draft.selected_client_code && draft.selected_client_name) {
        draftClientLoaded.current = true;
        setSelectedClient({ CardCode: draft.selected_client_code, CardName: draft.selected_client_name });
        setSearchPerformed(true);
      }
    }).catch(() => {});

    // 2. Vérifier si un devis SAP existe déjà pour cet email
    getExistingQuoteForEmail(quote.email.id).then((info) => {
      if (info.found) setExistingQuote(info);
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quote.email.id]);

  // ✨ NOUVEAUTÉ : Enrichir automatiquement les articles avec les prix depuis product_matches
  useEffect(() => {
    const baseArticles = doc?.documentLines || [];
    const productMatches = (quote.analysisResult?.product_matches as any[]) || [];

    if (productMatches.length > 0) {
      // Créer une map des prix par item_code
      // Indexée à la fois par item_code (SAP) ET par original_item_code (code externe)
      // pour que les articles dont le code a été corrigé manuellement soient correctement enrichis
      const priceMap = new Map();
      productMatches.forEach((pm: any) => {
        const entry = {
          ItemCode: pm.item_code,  // Code SAP corrigé (pour update de l'article)
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
          weight_unit_value: pm.weight_unit_value,
          weight_unit: pm.weight_unit,
          weight_total: pm.weight_total,
          not_found_in_sap: pm.not_found_in_sap,
          item_name: pm.item_name,
          match_reason: pm.match_reason,
        };
        priceMap.set(pm.item_code, entry);
        // Fallback sur le code externe original (si le code a été corrigé manuellement)
        if (pm.original_item_code && pm.original_item_code !== pm.item_code) {
          priceMap.set(pm.original_item_code, entry);
        }
      });

      // Enrichir les articles avec les prix et toutes les métadonnées pricing
      const enriched = baseArticles.map((article: any) => {
        const pricing = priceMap.get(article.ItemCode);
        if (pricing) {
          return {
            ...article,
            ...pricing,  // Copie TOUS les champs pricing + le code SAP corrigé via ItemCode
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
    let totalWeight = 0;

    articles.forEach((line: any) => {
      if (ignoredItems[line.LineNum]) return;
      const effectiveQty = quantityOverrides[line.LineNum] ?? line.Quantity ?? 1;
      if (line.unit_price && line.Quantity) {
        const lineTotal = line.unit_price * effectiveQty;
        subtotal += lineTotal;

        if (line.margin_applied) {
          totalMargin += line.margin_applied;
          count++;
        }
      }
      if (line.weight_unit_value) {
        totalWeight += line.weight_unit_value * effectiveQty;
      }
    });

    const avgMargin = count > 0 ? totalMargin / count : margin;
    return { subtotal, avgMargin, total: subtotal, totalWeight };
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
  // Transport = poids total × 2 sauf si manuellement surchargé
  const transportPrice = transportPriceOverride ?? Math.round((totals.totalWeight ?? 0) * 2 * 100) / 100;
  // Grand total = articles + emballage + transport
  const grandTotal = totals.subtotal + emballagePrice + transportPrice;

  // ✨ NOUVEAUTÉ : Pré-initialiser articleStatus pour les produits déjà trouvés
  useEffect(() => {
    const productMatches = (quote.analysisResult?.product_matches as any[]) || [];
    const baseArticles = doc?.documentLines || [];

    if (productMatches.length > 0 && baseArticles.length > 0) {
      const initialStatus: {[key: number]: {found: boolean, message: string, itemCode?: string}} = {};

      // Créer une map des product_matches par item_code (SAP) ET par original_item_code (code externe)
      const matchMap = new Map();
      productMatches.forEach((pm: any) => {
        if (pm.item_code && !pm.not_found_in_sap) {
          const wasManuallyValidated = pm.match_reason === 'Code RONDOT saisi manuellement' && pm.original_item_code;
          const status = {
            found: true,
            message: wasManuallyValidated ? `Code validé: ${pm.item_code}` : 'Trouvé automatiquement',
            itemCode: pm.item_code,
          };
          matchMap.set(pm.item_code, status);
          // Fallback : aussi indexer par le code externe original
          if (pm.original_item_code && pm.original_item_code !== pm.item_code) {
            matchMap.set(pm.original_item_code, status);
          }
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
  // Ignoré si le draft a déjà chargé un client (draftClientLoaded)
  useEffect(() => {
    if (draftClientLoaded.current) return;
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

  // ──────────────────────────────────────────────────────────────
  // Création devis SAP — Prévisualisation + Confirmation
  // ──────────────────────────────────────────────────────────────

  /** Construit le payload QuotationPayload depuis l'état local courant */
  const buildQuotationPayload = (): CreateQuoteRequest => {
    const activeLines = articles
      .filter((line: any) => !ignoredItems[line.LineNum])
      .map((line: any) => ({
        // N'envoyer l'ItemCode que si l'article est confirmé dans SAP (not_found_in_sap=false ou absent)
        ItemCode: (line.not_found_in_sap === true) ? undefined : (line.ItemCode || undefined),
        ItemDescription: line.ItemDescription || line.ItemCode || 'Article',
        Quantity: quantityOverrides[line.LineNum] ?? line.Quantity ?? 1,
        UnitPrice: line.unit_price ?? undefined,
        DiscountPercent: 0,
      }));

    // Lignes fixes toujours ajoutées
    const fixedLines = [
      { ItemCode: 'A06572', ItemDescription: 'Emballage', Quantity: 1, UnitPrice: emballagePrice, DiscountPercent: 0 },
      { ItemCode: 'A07042', ItemDescription: 'Transport', Quantity: 1, UnitPrice: transportPrice, DiscountPercent: 0 },
    ];

    return {
      CardCode: selectedClient!.CardCode,
      Comments: `Devis suite email: ${quote.email.subject || ''}`,
      email_id: quote.email.id,
      email_subject: quote.email.subject,
      DocumentLines: [...activeLines, ...fixedLines],
    };
  };

  /** Étape 1 : prévisualisation — appel backend sans écriture SAP */
  const handlePreviewQuote = async () => {
    if (!selectedClient) return;
    const payload = buildQuotationPayload();
    setIsPreviewing(true);
    try {
      const result = await previewSAPQuotation(payload);
      if (result.success && result.data) {
        // Enrichir les lignes preview avec les poids depuis enrichedArticles
        const weightMap = new Map<string, { weight_unit_value?: number; weight_unit?: string; weight_total?: number }>();
        articles.forEach((a: any) => {
          if (a.ItemCode && a.weight_unit_value != null) {
            weightMap.set(a.ItemCode, {
              weight_unit_value: a.weight_unit_value,
              weight_unit: a.weight_unit || 'kg',
              weight_total: a.weight_unit_value * (quantityOverrides[a.LineNum] ?? a.Quantity ?? 1),
            });
          }
        });
        const enrichedLines = result.data.lines.map((l: any) => ({
          ...l,
          ...(weightMap.get(l.ItemCode) || {}),
        }));
        setPreviewData({ ...result.data, lines: enrichedLines });
        setShowPreviewModal(true);
      } else {
        toast.error(`Erreur prévisualisation : ${result.error || 'inconnue'}`);
      }
    } finally {
      setIsPreviewing(false);
    }
  };

  /** Étape 2 : confirmation — création réelle dans SAP */
  const handleConfirmCreate = async () => {
    if (!selectedClient) return;
    const payload = buildQuotationPayload();
    setIsCreating(true);
    try {
      const result = await createSAPQuotation(payload);
      if (result.success && result.data) {
        if (result.data.retried) {
          toast.warning(
            `Session SAP réinitialisée automatiquement (${result.data.retry_reason || 'erreur transitoire'}) — nouvelle tentative réussie.`,
            { duration: 5000 }
          );
        }
        toast.success(`Devis SAP créé avec succès ! N° ${result.data.doc_num}`);
        setShowPreviewModal(false);
        // Marquer le devis comme créé pour bloquer les doublons
        setExistingQuote({
          found: true,
          sap_doc_num: result.data.doc_num,
          sap_doc_entry: result.data.doc_entry,
          client_code: selectedClient?.CardCode,
          created_at: new Date().toISOString(),
          status: 'created',
        });
        onValidate(result.data.doc_num);
      } else {
        toast.error(`Échec création SAP : ${result.error || 'inconnue'}`);
      }
    } finally {
      setIsCreating(false);
    }
  };

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
    triggerDraftSave(quantityOverrides, ignoredItems, client);
  };

  // Créer un nouveau client
  const handleCreateNew = () => {
    setSelectedClient(null);
    setCreateNewClient(true);
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
          // IMPORTANT: utiliser enrichedArticles pour conserver les codes SAP validés manuellement
          const baseArticles = enrichedArticles.length > 0 ? enrichedArticles : (doc?.documentLines || []);
          const productMatches = result.analysis.product_matches;

          const priceMap = new Map();
          productMatches.forEach((pm: any) => {
            priceMap.set(pm.item_code, {
              unit_price: pm.unit_price,
              line_total: pm.line_total,
              pricing_case: pm.pricing_case,
              margin_applied: pm.margin_applied,
              requires_validation: pm.requires_validation,
              weight_unit_value: pm.weight_unit_value,
              weight_unit: pm.weight_unit,
              weight_total: pm.weight_total,
            });
          });

          const enriched = baseArticles.map((article: any) => {
            // Conserver les prix manuellement fixés par l'utilisateur
            const manualPrice = manualPriceOverrides[article.ItemCode];
            if (manualPrice != null) {
              return {
                ...article,
                unit_price: manualPrice,
                line_total: manualPrice * (quantityOverrides[article.LineNum] ?? article.Quantity ?? 1),
                pricing_case: 'CAS_MANUAL',
              };
            }
            const pricing = priceMap.get(article.ItemCode);
            if (pricing) {
              return { ...article, ...pricing };
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

  // Gérer la modification de quantité (mise à jour immédiate UI + sauvegarde debounce 600ms)
  const handleQuantityChange = (lineNum: number, value: string, itemCode: string) => {
    const parsed = parseInt(value, 10);
    if (!isNaN(parsed) && parsed > 0) {
      const updated = { ...quantityOverrides, [lineNum]: parsed };
      setQuantityOverrides(updated);
      triggerDraftSave(updated, ignoredItems, selectedClient);

      // Sauvegarde backend avec debounce
      const key = `${lineNum}_${itemCode}`;
      if (saveQtyTimeouts.current[key]) clearTimeout(saveQtyTimeouts.current[key]);
      saveQtyTimeouts.current[key] = setTimeout(async () => {
        try {
          await updateProductQuantity(quote.email.id, itemCode, parsed);
        } catch (err: any) {
          console.warn('Erreur sauvegarde quantité:', err.message);
        }
      }, 600);
    }
  };

  // Réinitialiser la quantité à la valeur initiale
  const handleQuantityReset = (lineNum: number, itemCode: string) => {
    setQuantityOverrides(prev => {
      const updated = { ...prev };
      delete updated[lineNum];
      triggerDraftSave(updated, ignoredItems, selectedClient);
      return updated;
    });
    // Restaurer la quantité originale en base
    const original = enrichedArticles.find((a: any) => a.LineNum === lineNum);
    if (original?.Quantity && itemCode) {
      updateProductQuantity(quote.email.id, itemCode, original.Quantity)
        .catch(err => console.warn('Erreur restauration quantité:', err.message));
    }
  };

  // Ignorer un article (Option C)
  const handleIgnoreItem = async (lineNum: number, itemCode: string) => {
    try {
      await excludeProduct(quote.email.id, itemCode, "Ignoré par l'utilisateur");
      const updated = { ...ignoredItems, [lineNum]: true };
      setIgnoredItems(updated);
      triggerDraftSave(quantityOverrides, updated, selectedClient);
      toast.success('Article ignoré et exclu du devis');
    } catch (error: any) {
      toast.error(error.message || "Erreur lors de l'exclusion");
    }
  };

  // Restaurer un article ignoré par erreur
  const handleRestoreItem = (lineNum: number) => {
    const updated = { ...ignoredItems };
    delete updated[lineNum];
    setIgnoredItems(updated);
    triggerDraftSave(quantityOverrides, updated, selectedClient);
    toast.success('Article restauré dans le devis');
  };

  // Valider le code SAP saisi manuellement (Option A)
  const handleManualCodeSubmit = async (lineNum: number, originalItemCode: string) => {
    const code = (manualCodeInput[lineNum] || '').trim();
    if (!code) return;

    setManualCodeLoading(prev => ({ ...prev, [lineNum]: true }));
    try {
      const result = await setManualCode(quote.email.id, originalItemCode, code);
      setEnrichedArticles(prev => prev.map((a: any) =>
        a.LineNum === lineNum
          ? { ...a, ItemCode: result.item_code, ItemDescription: result.item_name, not_found_in_sap: false }
          : a
      ));
      setArticleStatus(prev => ({
        ...prev,
        [lineNum]: { found: true, message: `Code validé: ${result.item_code}`, itemCode: result.item_code }
      }));
      setShowManualInput(prev => ({ ...prev, [lineNum]: false }));
      toast.success(`Article associé: ${result.item_name}`);
    } catch (error: any) {
      toast.error(error.message || 'Code SAP invalide');
    } finally {
      setManualCodeLoading(prev => ({ ...prev, [lineNum]: false }));
    }
  };

  // Relancer la recherche SAP (Option B)
  const handleRetrySearch = async (lineNum: number, itemCode: string, itemDescription: string) => {
    setRetryLoading(prev => ({ ...prev, [lineNum]: true }));
    try {
      const result = await retrySearchProduct(quote.email.id, itemCode, itemDescription);
      setRetryResults(prev => ({ ...prev, [lineNum]: result.items || [] }));
      setShowRetryResults(prev => ({ ...prev, [lineNum]: true }));
      if ((result.items || []).length === 0) {
        toast.info('Aucun article trouvé pour cette référence');
      }
    } catch (error: any) {
      toast.error(error.message || 'Erreur lors de la recherche');
    } finally {
      setRetryLoading(prev => ({ ...prev, [lineNum]: false }));
    }
  };

  // Sélectionner un article dans les résultats de relance
  const handleSelectRetryResult = async (lineNum: number, originalItemCode: string, selectedCode: string, selectedName: string) => {
    setManualCodeLoading(prev => ({ ...prev, [lineNum]: true }));
    try {
      const result = await setManualCode(quote.email.id, originalItemCode, selectedCode);
      setEnrichedArticles(prev => prev.map((a: any) =>
        a.LineNum === lineNum
          ? { ...a, ItemCode: result.item_code, ItemDescription: result.item_name, not_found_in_sap: false }
          : a
      ));
      setArticleStatus(prev => ({
        ...prev,
        [lineNum]: { found: true, message: `Article sélectionné: ${result.item_code}`, itemCode: result.item_code }
      }));
      setShowRetryResults(prev => ({ ...prev, [lineNum]: false }));
      toast.success(`Article associé: ${result.item_name}`);
    } catch (error: any) {
      toast.error(error.message || "Erreur lors de l'association");
    } finally {
      setManualCodeLoading(prev => ({ ...prev, [lineNum]: false }));
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

      {/* Bannière consultation - devis déjà traité */}
      {isProcessed && (
        <div className="flex items-center gap-3 p-4 rounded-lg border border-success/40 bg-success/8">
          <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-success">
              Devis traité
              {existingQuote?.found && existingQuote.sap_doc_num
                ? ` — N° SAP ${existingQuote.sap_doc_num}`
                : ''}
            </p>
            <p className="text-sm text-muted-foreground">
              Ce mail a déjà fait l'objet d'un devis. Consultation en lecture seule.
            </p>
          </div>
        </div>
      )}

      {/* Onglets principaux */}
      <Tabs defaultValue="synthese">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="synthese" className="flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5" />
            Synthèse
          </TabsTrigger>
          <TabsTrigger value="email" className="flex items-center gap-1.5">
            <Mail className="w-3.5 h-3.5" />
            Email source
          </TabsTrigger>
          <TabsTrigger value="pieces-jointes" className="flex items-center gap-1.5">
            <Paperclip className="w-3.5 h-3.5" />
            Pièces jointes
            {quote.email.hasAttachments && (
              <Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0 h-4">
                {quote.email.attachments.length || '?'}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="donnees" className="flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" />
            Données extraites
          </TabsTrigger>
        </TabsList>

        {/* Onglet Synthèse — contenu principal */}
        <TabsContent value="synthese" className="space-y-6 mt-4">

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
                <TableHead className="text-right">Poids u.</TableHead>
                <TableHead className="text-right">Poids total</TableHead>
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
                    <TableRow key={line.LineNum} className={ignoredItems[line.LineNum] ? 'opacity-40' : ''}>
                      <TableCell className="font-mono text-sm">
                        {line.ItemCode || 'À définir'}
                      </TableCell>
                      <TableCell className={ignoredItems[line.LineNum] ? 'line-through text-muted-foreground' : ''}>{line.ItemDescription}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Input
                            type="number"
                            min="1"
                            value={quantityOverrides[line.LineNum] ?? line.Quantity}
                            onChange={(e) => handleQuantityChange(line.LineNum, e.target.value, line.ItemCode || '')}
                            className={`w-16 text-right h-7 text-sm px-1 ${quantityOverrides[line.LineNum] !== undefined ? 'border-warning text-warning font-semibold' : ''}`}
                            disabled={!!ignoredItems[line.LineNum]}
                          />
                          {quantityOverrides[line.LineNum] !== undefined && (
                            <button
                              onClick={() => handleQuantityReset(line.LineNum, line.ItemCode || '')}
                              className="text-muted-foreground hover:text-foreground transition-colors"
                              title="Réinitialiser la quantité"
                            >
                              <RotateCcw className="w-3 h-3" />
                            </button>
                          )}
                          {line.UnitOfMeasure && (
                            <span className="text-xs text-muted-foreground">{line.UnitOfMeasure}</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {(line as any).weight_unit_value != null ? (
                          <span>{(line as any).weight_unit_value} {(line as any).weight_unit || 'kg'}</span>
                        ) : (
                          <span className="text-muted-foreground" title="Poids non renseigné dans SAP">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {(line as any).weight_unit_value != null ? (
                          <span className="font-medium">
                            {((line as any).weight_unit_value * (quantityOverrides[line.LineNum] ?? line.Quantity ?? 1)).toFixed(3)} kg
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <PriceEditorDialog
                          line={line}
                          effectiveQuantity={quantityOverrides[line.LineNum] ?? line.Quantity}
                          onPriceUpdated={(newPrice) => {
                            // Mémoriser l'override manuel (protège contre Recalculer)
                            setManualPriceOverrides(prev => ({ ...prev, [line.ItemCode]: newPrice }));
                            // Mettre à jour le state React (déclenche re-render)
                            setEnrichedArticles(prev => prev.map((a: any) =>
                              a.LineNum === line.LineNum
                                ? { ...a, unit_price: newPrice, line_total: newPrice * (quantityOverrides[a.LineNum] ?? a.Quantity ?? 1), pricing_case: 'CAS_MANUAL' }
                                : a
                            ));
                          }}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        {(() => {
                          const isIgnored = !!ignoredItems[line.LineNum];
                          const isNotFound = line.not_found_in_sap === true || (status && !status.found);

                          if (isIgnored) {
                            return (
                              <div className="flex flex-col items-center gap-1">
                                <Badge variant="outline" className="text-muted-foreground">
                                  Ignoré
                                </Badge>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 text-xs px-2 text-primary hover:text-primary"
                                  onClick={() => handleRestoreItem(line.LineNum)}
                                >
                                  <RotateCcw className="w-3 h-3 mr-1" />
                                  Restaurer
                                </Button>
                              </div>
                            );
                          }

                          if (status?.found) {
                            return (
                              <div>
                                <Badge className="bg-success/10 text-success border-success/20">
                                  <CheckCircle className="w-3 h-3 mr-1" />
                                  Trouvé
                                </Badge>
                                {status.message && (
                                  <p className="text-xs text-muted-foreground mt-1">{status.message}</p>
                                )}
                              </div>
                            );
                          }

                          if (isNotFound) {
                            return (
                              <div className="space-y-1.5">
                                <Badge variant="outline" className="text-destructive border-destructive">
                                  <AlertCircle className="w-3 h-3 mr-1" />
                                  Non trouvé
                                </Badge>

                                {/* Option A : saisie manuelle */}
                                {showManualInput[line.LineNum] ? (
                                  <div className="flex items-center gap-1">
                                    <Input
                                      placeholder="Code SAP..."
                                      value={manualCodeInput[line.LineNum] || ''}
                                      onChange={(e) => setManualCodeInput(prev => ({ ...prev, [line.LineNum]: e.target.value }))}
                                      onKeyDown={(e) => e.key === 'Enter' && handleManualCodeSubmit(line.LineNum, line.ItemCode || '')}
                                      className="h-7 text-xs w-24 px-1"
                                      autoFocus
                                    />
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 w-7 p-0"
                                      onClick={() => handleManualCodeSubmit(line.LineNum, line.ItemCode || '')}
                                      disabled={!!manualCodeLoading[line.LineNum]}
                                    >
                                      {manualCodeLoading[line.LineNum]
                                        ? <Loader2 className="w-3 h-3 animate-spin" />
                                        : <CheckCircle className="w-3 h-3" />}
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="h-7 w-7 p-0"
                                      onClick={() => setShowManualInput(prev => ({ ...prev, [line.LineNum]: false }))}
                                    >
                                      <X className="w-3 h-3" />
                                    </Button>
                                  </div>

                                /* Option B : résultats de relance */
                                ) : showRetryResults[line.LineNum] ? (
                                  <div className="space-y-1 text-left max-w-[180px]">
                                    {(retryResults[line.LineNum] || []).length > 0 ? (
                                      retryResults[line.LineNum].map((item: any) => (
                                        <button
                                          key={item.item_code}
                                          className="flex flex-col w-full text-left px-1.5 py-1 rounded hover:bg-muted/60 transition-colors text-xs"
                                          onClick={() => handleSelectRetryResult(line.LineNum, line.ItemCode || '', item.item_code, item.item_name)}
                                          disabled={!!manualCodeLoading[line.LineNum]}
                                        >
                                          <span className="font-mono font-medium">{item.item_code}</span>
                                          <span className="text-muted-foreground truncate">{item.item_name}</span>
                                        </button>
                                      ))
                                    ) : (
                                      <p className="text-xs text-muted-foreground px-1">Aucun résultat</p>
                                    )}
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="h-6 text-xs w-full"
                                      onClick={() => setShowRetryResults(prev => ({ ...prev, [line.LineNum]: false }))}
                                    >
                                      Fermer
                                    </Button>
                                  </div>

                                /* Actions principales */
                                ) : (
                                  <div className="flex flex-col gap-1">
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 text-xs justify-start px-2"
                                      onClick={() => setShowManualInput(prev => ({ ...prev, [line.LineNum]: true }))}
                                    >
                                      <FileText className="w-3 h-3 mr-1 flex-shrink-0" />
                                      Saisir code SAP
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 text-xs justify-start px-2"
                                      onClick={() => handleRetrySearch(line.LineNum, line.ItemCode || '', line.ItemDescription)}
                                      disabled={!!retryLoading[line.LineNum]}
                                    >
                                      {retryLoading[line.LineNum]
                                        ? <Loader2 className="w-3 h-3 mr-1 animate-spin flex-shrink-0" />
                                        : <RefreshCw className="w-3 h-3 mr-1 flex-shrink-0" />}
                                      Relancer la recherche
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="h-7 text-xs justify-start px-2 text-muted-foreground hover:text-destructive"
                                      onClick={() => handleIgnoreItem(line.LineNum, line.ItemCode || '')}
                                    >
                                      <X className="w-3 h-3 mr-1 flex-shrink-0" />
                                      Ignorer
                                    </Button>
                                  </div>
                                )}
                              </div>
                            );
                          }

                          // Statut non vérifié → bouton Vérifier
                          return (
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
                          );
                        })()}
                      </TableCell>
                    </TableRow>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    Aucun article détecté. Analyse manuelle requise.
                  </TableCell>
                </TableRow>
              )}

              {/* ── Ligne fixe : Emballage ── */}
              <TableRow className="bg-muted/20 border-t-2 border-dashed border-muted-foreground/20">
                <TableCell className="font-mono text-sm text-muted-foreground">A06572</TableCell>
                <TableCell className="text-sm">Emballage</TableCell>
                <TableCell className="text-right text-sm">1</TableCell>
                <TableCell className="text-right text-sm text-muted-foreground">—</TableCell>
                <TableCell className="text-right text-sm text-muted-foreground">—</TableCell>
                <TableCell className="text-right">
                  {editingFixedLine === 'emballage' ? (
                    <div className="flex items-center justify-end gap-1">
                      <Input
                        type="number"
                        value={fixedLineInputValue}
                        onChange={(e) => setFixedLineInputValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const v = parseFloat(fixedLineInputValue);
                            if (!isNaN(v) && v >= 0) setEmballagePrice(v);
                            setEditingFixedLine(null);
                          }
                          if (e.key === 'Escape') setEditingFixedLine(null);
                        }}
                        className="h-7 w-24 text-xs text-right"
                        autoFocus
                      />
                      <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                        onClick={() => {
                          const v = parseFloat(fixedLineInputValue);
                          if (!isNaN(v) && v >= 0) setEmballagePrice(v);
                          setEditingFixedLine(null);
                        }}>
                        <CheckCircle className="w-3 h-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-end gap-2 cursor-pointer group"
                      onClick={() => { setEditingFixedLine('emballage'); setFixedLineInputValue(emballagePrice.toString()); }}>
                      <span className="font-semibold">{emballagePrice.toFixed(2)} €</span>
                      <span className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </span>
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-center">
                  <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">Fixe</span>
                </TableCell>
              </TableRow>

              {/* ── Ligne fixe : Transport ── */}
              <TableRow className="bg-muted/20">
                <TableCell className="font-mono text-sm text-muted-foreground">A07042</TableCell>
                <TableCell className="text-sm">
                  Transport
                  {transportPriceOverride === null && totals.totalWeight > 0 && (
                    <span className="text-xs text-muted-foreground ml-1">({totals.totalWeight?.toFixed(3)} kg × 2)</span>
                  )}
                </TableCell>
                <TableCell className="text-right text-sm">1</TableCell>
                <TableCell className="text-right text-sm text-muted-foreground">—</TableCell>
                <TableCell className="text-right text-sm text-muted-foreground">—</TableCell>
                <TableCell className="text-right">
                  {editingFixedLine === 'transport' ? (
                    <div className="flex items-center justify-end gap-1">
                      <Input
                        type="number"
                        value={fixedLineInputValue}
                        onChange={(e) => setFixedLineInputValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const v = parseFloat(fixedLineInputValue);
                            if (!isNaN(v) && v >= 0) setTransportPriceOverride(v);
                            setEditingFixedLine(null);
                          }
                          if (e.key === 'Escape') setEditingFixedLine(null);
                        }}
                        className="h-7 w-24 text-xs text-right"
                        autoFocus
                      />
                      <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                        onClick={() => {
                          const v = parseFloat(fixedLineInputValue);
                          if (!isNaN(v) && v >= 0) setTransportPriceOverride(v);
                          setEditingFixedLine(null);
                        }}>
                        <CheckCircle className="w-3 h-3" />
                      </Button>
                      {transportPriceOverride !== null && (
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground"
                          title="Réinitialiser (poids × 2)"
                          onClick={() => { setTransportPriceOverride(null); setEditingFixedLine(null); }}>
                          <RotateCcw className="w-3 h-3" />
                        </Button>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center justify-end gap-2 cursor-pointer group"
                      onClick={() => { setEditingFixedLine('transport'); setFixedLineInputValue(transportPrice.toFixed(2)); }}>
                      <span className={`font-semibold ${transportPriceOverride !== null ? 'text-primary' : ''}`}>
                        {transportPrice.toFixed(2)} €
                      </span>
                      <span className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </span>
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-center">
                  <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">Fixe</span>
                </TableCell>
              </TableRow>
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
          <div className="grid grid-cols-4 gap-6">
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
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Poids total</p>
              {totals.totalWeight > 0 ? (
                <p className="text-xl font-semibold text-foreground">
                  {totals.totalWeight.toFixed(3)} kg
                </p>
              ) : (
                <p className="text-xl font-semibold text-muted-foreground">—</p>
              )}
            </div>
            <div className="text-center p-4 bg-primary/10 rounded-lg border border-primary/20">
              <p className="text-sm text-muted-foreground mb-1">Total HT</p>
              {grandTotal > 0 ? (
                <p className="text-2xl font-bold text-foreground">
                  {grandTotal.toFixed(2)} €
                </p>
              ) : (
                <p className="text-2xl font-bold text-muted-foreground">
                  À calculer
                </p>
              )}
              {grandTotal > 0 && (
                <p className="text-xs text-success mt-1">Emballage + Transport inclus</p>
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

        </TabsContent>

        {/* Onglet Email source */}
        <TabsContent value="email" className="mt-4">
          <EmailSourceTab
            emailId={quote.email.id}
            fromName={quote.email.from.emailAddress.name}
            fromAddress={quote.email.from.emailAddress.address}
            subject={quote.email.subject}
            receivedDateTime={quote.email.receivedDateTime}
            bodyPreview={quote.email.bodyPreview}
          />
        </TabsContent>

        {/* Onglet Pièces jointes */}
        <TabsContent value="pieces-jointes" className="mt-4">
          <AttachmentsTab
            emailId={quote.email.id}
            hasAttachments={quote.email.hasAttachments}
          />
        </TabsContent>

        {/* Onglet Données extraites */}
        <TabsContent value="donnees" className="mt-4">
          <ExtractedDataTab
            emailId={quote.email.id}
            analysisResult={quote.analysisResult as any}
          />
        </TabsContent>
      </Tabs>

      {/* Bannière : devis SAP déjà créé */}
      {existingQuote?.found && (
        <div className="flex items-start gap-3 rounded-lg border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/20 px-4 py-3 text-sm">
          <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-yellow-800 dark:text-yellow-300">
              Devis déjà envoyé dans SAP
            </p>
            <p className="text-yellow-700 dark:text-yellow-400">
              Un devis a été créé le{' '}
              {existingQuote.created_at
                ? new Date(existingQuote.created_at).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                : '—'}{' '}
              {existingQuote.sap_doc_num ? `— N° SAP : ${existingQuote.sap_doc_num}` : ''}.
              Créer un nouveau devis produirait un doublon.
            </p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between items-center pt-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Retour
          </Button>
          {onReanalyze && (
            <Button
              variant="outline"
              onClick={onReanalyze}
              disabled={isReanalyzing}
              title="Relancer l'analyse complète de cet email (données fraîches)"
            >
              {isReanalyzing ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-2" />
              )}
              Réanalyser
            </Button>
          )}
        </div>
        {(() => {
          const hasUnresolved = articles.some((line: any) => {
            if (ignoredItems[line.LineNum]) return false;
            const st = articleStatus[line.LineNum];
            return line.not_found_in_sap === true && !(st?.found === true);
          });
          const alreadySent = existingQuote?.found === true;
          const isDisabled = !doc || articles.length === 0 || (!selectedClient && !createNewClient) || hasUnresolved || isPreviewing;
          const label = alreadySent
            ? `Recréer (N° ${existingQuote?.sap_doc_num ?? '?'})`
            : !selectedClient && !createNewClient
              ? 'Sélectionnez un client'
              : hasUnresolved
                ? 'Résolvez les articles non trouvés'
                : isPreviewing
                  ? 'Préparation...'
                  : articles.length > 0
                    ? 'Créer le devis SAP'
                    : 'Extraction incomplète';
          return (
            <Button
              onClick={handlePreviewQuote}
              size="lg"
              disabled={isDisabled}
              variant={alreadySent ? 'outline' : 'default'}
              className={alreadySent ? 'border-yellow-500 text-yellow-700 hover:bg-yellow-50' : ''}
            >
              {isPreviewing
                ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                : alreadySent
                  ? <AlertTriangle className="w-4 h-4 mr-2 text-yellow-600" />
                  : <CheckCircle className="w-4 h-4 mr-2" />
              }
              {label}
            </Button>
          );
        })()}
      </div>

      {/* Modale de prévisualisation SAP */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Prévisualisation du devis SAP
            </DialogTitle>
            <DialogDescription>
              Vérifiez les informations ci-dessous avant d'envoyer dans SAP Business One.
            </DialogDescription>
          </DialogHeader>

          {previewData && (
            <div className="space-y-4">
              {/* Client */}
              <div className="flex items-center gap-2 p-3 bg-muted rounded-md">
                <Building2 className="w-4 h-4 text-muted-foreground" />
                <span className="font-medium">{selectedClient?.CardName}</span>
                <Badge variant="outline">{selectedClient?.CardCode}</Badge>
              </div>

              {/* Lignes du devis */}
              <div>
                <p className="text-sm font-medium mb-2">
                  Lignes du devis ({previewData.totals.lines_count})
                </p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Réf. SAP</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead className="text-right">Qté</TableHead>
                      <TableHead className="text-right">Poids u.</TableHead>
                      <TableHead className="text-right">Poids total</TableHead>
                      <TableHead className="text-right">Prix unit. HT</TableHead>
                      <TableHead className="text-right">Total HT</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewData.lines.map((line, i) => {
                      const pLine = line as any;
                      const wTotal = pLine.weight_unit_value != null
                        ? pLine.weight_unit_value * (line.Quantity || 0)
                        : null;
                      return (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">
                          {line.ItemCode || <span className="text-muted-foreground italic">Texte libre</span>}
                        </TableCell>
                        <TableCell>{line.ItemDescription}</TableCell>
                        <TableCell className="text-right">{line.Quantity}</TableCell>
                        <TableCell className="text-right text-sm">
                          {pLine.weight_unit_value != null
                            ? `${pLine.weight_unit_value} ${pLine.weight_unit || 'kg'}`
                            : <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell className="text-right text-sm">
                          {wTotal != null
                            ? `${wTotal.toFixed(3)} kg`
                            : <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell className="text-right">
                          {line.UnitPrice != null ? `${line.UnitPrice.toFixed(2)} €` : '—'}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {line.UnitPrice != null
                            ? `${((line.Quantity || 0) * line.UnitPrice).toFixed(2)} €`
                            : '—'}
                        </TableCell>
                      </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              {/* Totaux */}
              <div className="flex justify-between items-center p-3 bg-muted rounded-md">
                <div className="flex gap-6 text-sm">
                  <span>
                    <span className="text-muted-foreground">Total HT : </span>
                    <span className="font-bold text-base">{previewData.totals.subtotal.toFixed(2)} €</span>
                  </span>
                  <span>
                    <span className="text-muted-foreground">Marge moy. : </span>
                    <span className="font-semibold">{totals.avgMargin.toFixed(1)} %</span>
                  </span>
                  <span>
                    <span className="text-muted-foreground">Devise : </span>
                    <span className="font-semibold">{previewData.currency}</span>
                  </span>
                </div>
                <Badge variant="default" className="text-xs">
                  {previewData.validation_status === 'ready_for_sap' ? '✓ Prêt pour SAP' : previewData.validation_status}
                </Badge>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowPreviewModal(false)} disabled={isCreating}>
              Annuler
            </Button>
            <Button onClick={handleConfirmCreate} disabled={isCreating}>
              {isCreating
                ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                : <CheckCircle className="w-4 h-4 mr-2" />
              }
              {isCreating ? 'Création en cours...' : 'Confirmer et créer dans SAP'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
