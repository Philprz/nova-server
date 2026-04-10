import { fetchWithAuth } from '@/lib/fetchWithAuth';
import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, CheckCircle, Calculator, FileText, TrendingUp, Building2, Package, Search, Loader2, UserCheck, UserPlus, AlertCircle, AlertTriangle, RefreshCw, Mail, Paperclip, RotateCcw, X, Pencil, Plus, XCircle, MapPin } from 'lucide-react';
import { ClientRiskBadge } from './ClientRiskBadge';
import { ProcessedEmail } from '@/types/email';
import { CreateItemDialog } from './CreateItemDialog';
import { PriceEditorDialog } from './PriceEditorDialog';
import { ShippingCalculatorPanel } from './ShippingCalculatorPanel';
import { EmailSourceTab } from './EmailSourceTab';
import { AttachmentsTab } from './AttachmentsTab';
import { ExtractedDataTab } from './ExtractedDataTab';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { recalculatePricing, excludeProduct, setManualCode, retrySearchProduct, updateProductQuantity, loadDraftState, saveDraftState, resolveProductAmbiguity } from '@/lib/graphApi';
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
  Street?: string;
  City?: string;
  Country?: string;
  ZipCode?: string;
  similarity?: number;
}

interface ShipToAddress {
  street?: string;
  city?: string;
  zipCode?: string;
  country?: string;
}

function isAddressComplete(addr: ShipToAddress): boolean {
  return !!(addr.city && addr.country);
}

function ShipToAddressBlock({ addr, className = '' }: { addr: ShipToAddress; className?: string }) {
  if (!addr.street && !addr.city && !addr.zipCode && !addr.country) {
    return (
      <p className={`text-xs text-warning flex items-center gap-1 ${className}`}>
        Adresse non structurée — vérification requise
      </p>
    );
  }
  return (
    <div className={`text-xs text-muted-foreground leading-relaxed ${className}`}>
      {addr.street && <div>{addr.street}</div>}
      {(addr.zipCode || addr.city) && (
        <div>{[addr.zipCode, addr.city].filter(Boolean).join(' ')}</div>
      )}
      {addr.country && <div>{addr.country}</div>}
    </div>
  );
}

interface ShipToState {
  text: string;
  sapCode?: string;
  address?: ShipToAddress;
  source: 'client' | 'supplier' | 'llm' | 'sap' | 'user' | 'manual';
  validated: boolean;
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
  onReanalyze?: () => Promise<any>;
  isReanalyzing?: boolean;
  isProcessed?: boolean;
}

export function QuoteSummary({ quote, onValidate, onBack, onReanalyze, isReanalyzing = false, isProcessed = false }: QuoteSummaryProps) {
  // State local pour l'analysisResult — mis à jour directement après re-analyse
  const [localAnalysisResult, setLocalAnalysisResult] = useState<any>(quote.analysisResult);

  // Synchroniser si le parent change (ex: premier chargement)
  useEffect(() => { setLocalAnalysisResult(quote.analysisResult); }, [quote.email.id]);

  const handleReanalyzeLocal = async () => {
    if (!onReanalyze) return;
    const result = await onReanalyze();
    if (result) setLocalAnalysisResult(result);
  };

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

  // État pour l'ouverture des options de gestion sur les lignes déjà trouvées automatiquement
  const [showOverrideOptions, setShowOverrideOptions] = useState<{[lineNum: number]: boolean}>({});

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

  // État structuré pour l'adresse de livraison
  const [shipToState, setShipToState] = useState<ShipToState>({
    text: '',
    source: 'client',
    validated: false,
  });
  const [shipToSearchQuery, setShipToSearchQuery] = useState('');
  const [shipToSearching, setShipToSearching] = useState(false);
  const [shipToResults, setShipToResults] = useState<SapClient[]>([]);
  // Proposition automatique (1 seul résultat SAP) — en attente de confirmation utilisateur
  const [shipToProposal, setShipToProposal] = useState<SapClient | null>(null);
  // Formulaire de saisie manuelle (affiché si aucun résultat SAP)
  const [showManualShipTo, setShowManualShipTo] = useState(false);
  const [manualShipTo, setManualShipTo] = useState({ name: '', street: '', zip: '', city: '', country: '' });

  // Prix manuellement fixés (protège contre Recalculer)
  const [manualPriceOverrides, setManualPriceOverrides] = useState<{[itemCode: string]: number}>({});

  // Commentaires libres du devis (envoyés dans le champ Comments SAP)
  const DEFAULT_DELIVERY_COMMENT = 'Délai de livraison : 6 SEMAINES A RECEPTION DE COMMANDE';
  const [comments, setComments] = useState<string>(DEFAULT_DELIVERY_COMMENT);

  // Lignes ajoutées manuellement (non issues de l'analyse email)
  interface ManualLine {
    id: number;
    ItemCode: string;
    ItemDescription: string;
    Quantity: number;
    UnitPrice: number | null;
  }
  const [manualLines, setManualLines] = useState<ManualLine[]>([]);
  const manualLineCounter = useRef(0);

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

  const [resolveLoading, setResolveLoading] = useState<{[key: string]: boolean}>({});

  // Map directe originalCode/itemCode → candidats (source unique : analysisResult)
  const pendingByCode = new Map<string, any[]>();
  const _allPm = (localAnalysisResult?.product_matches as any[]) || [];
  console.log('[DIAG] product_matches count:', _allPm.length, '| pending:', _allPm.filter((p:any) => p.status === 'pending_selection').length);
  console.log('[DIAG] product_matches:', JSON.stringify(_allPm.map((p:any) => ({ code: p.item_code, status: p.status, candidates: p.candidates?.length }))));
  _allPm.forEach((pm: any) => {
    if (pm.status === 'pending_selection' && pm.candidates?.length > 0) {
      pendingByCode.set(pm.item_code, pm.candidates);
      if (pm.original_code) pendingByCode.set(pm.original_code, pm.candidates);
    }
  });
  console.log('[DIAG] enrichedArticles ItemCodes:', enrichedArticles.map((a:any) => a.ItemCode));
  console.log('[DIAG] pendingByCode keys:', [...pendingByCode.keys()]);

  // État pour le blocage client en liquidation judiciaire
  const [forceBlocked, setForceBlocked] = useState(false);
  const [showBlockedConfirm, setShowBlockedConfirm] = useState(false);

  // Marge par défaut RONDOT-SAS (min 35%, cible 40%, max 45%)
  const margin = 40;

  /** Sauvegarde l'état UI courant (debounce 800ms) */
  const triggerDraftSave = (
    overrides: {[lineNum: number]: number},
    ignored: {[lineNum: number]: boolean},
    client: SapClient | null,
    transportOverride?: number | null,
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
          transport_price_override: transportOverride ?? null,
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
        // Enrichir depuis le cache SAP pour corriger CardName/adresse si le draft a un nom obsolète
        fetchWithAuth(`/api/clients/by-code?card_code=${encodeURIComponent(draft.selected_client_code)}`)
          .then((r) => r.json())
          .then((data) => {
            if (data.success && data.client) {
              setSelectedClient((prev) =>
                prev ? { ...prev, CardName: data.client.CardName || prev.CardName, Street: data.client.Street, City: data.client.City, Country: data.client.Country, ZipCode: data.client.ZipCode } : prev
              );
            }
          })
          .catch(() => {});
      }
      if (draft.transport_price_override != null) {
        setTransportPriceOverride(draft.transport_price_override);
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
    const productMatches = (localAnalysisResult?.product_matches as any[]) || [];

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
          // Désambiguïsation
          pending_candidates: pm.status === 'pending_selection' ? (pm.candidates || []) : undefined,
          original_code: pm.original_code,
        };
        priceMap.set(pm.item_code, entry);
        // Fallback sur le code externe original (si le code a été corrigé manuellement)
        if (pm.original_item_code && pm.original_item_code !== pm.item_code) {
          priceMap.set(pm.original_item_code, entry);
        }
        // Fallback sur original_code (désambiguïsation — item_code = code non résolu)
        if (pm.original_code && pm.original_code !== pm.item_code) {
          priceMap.set(pm.original_code, entry);
        }
      });

      // Enrichir les articles avec les prix et toutes les métadonnées pricing
      const enriched = baseArticles.map((article: any) => {
        const pricing = priceMap.get(article.ItemCode);
        if (pricing) {
          // Si le code SAP a changé (ambiguïté résolue), mettre à jour la description aussi
          const codeChanged = pricing.ItemCode && pricing.ItemCode !== article.ItemCode;
          return {
            ...article,
            ...pricing,  // Copie TOUS les champs pricing + le code SAP corrigé via ItemCode
            ItemDescription: (codeChanged && pricing.item_name) ? pricing.item_name : article.ItemDescription,
          };
        }
        return article;
      });

      setEnrichedArticles(enriched);
    } else {
      setEnrichedArticles(baseArticles);
    }
  }, [doc?.documentLines, localAnalysisResult?.product_matches]);

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

        // Calculer la marge réelle depuis le prix actuel et le prix fournisseur
        if (line.supplier_price > 0) {
          totalMargin += ((line.unit_price - line.supplier_price) / line.supplier_price) * 100;
          count++;
        } else if (line.margin_applied) {
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
    const productMatches = (localAnalysisResult?.product_matches as any[]) || [];
    const baseArticles = doc?.documentLines || [];

    if (productMatches.length > 0 && baseArticles.length > 0) {
      const initialStatus: {[key: number]: {found: boolean, message: string, itemCode?: string}} = {};

      // Créer une map des product_matches par item_code (SAP) ET par original_item_code (code externe)
      const matchMap = new Map();
      productMatches.forEach((pm: any) => {
        if (pm.item_code && !pm.not_found_in_sap && pm.status !== 'pending_selection') {
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
          // Fallback : désambiguïsation — original_code est l'ancien code fournisseur
          if (pm.original_code && pm.original_code !== pm.item_code) {
            matchMap.set(pm.original_code, status);
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
  }, [localAnalysisResult?.product_matches, doc?.documentLines]);

  // Auto-sélection si le client SAP est déjà identifié par le matching backend
  // Ignoré si le draft a déjà chargé un client (draftClientLoaded)
  useEffect(() => {
    if (draftClientLoaded.current) return;
    if (doc?.businessPartner.CardCode) {
      // Auto-sélection de base (sans adresse) — le backend a validé un candidat unique et fiable
      setSelectedClient({
        CardCode: doc.businessPartner.CardCode,
        CardName: doc.businessPartner.CardName,
        EmailAddress: doc.businessPartner.ContactEmail,
      });
      setSearchPerformed(true);
      // Enrichissement asynchrone avec CardName/City/Country depuis le cache SAP
      fetchWithAuth(`/api/clients/by-code?card_code=${encodeURIComponent(doc.businessPartner.CardCode)}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.success && data.client) {
            setSelectedClient((prev) =>
              prev ? { ...prev, CardName: data.client.CardName || prev.CardName, Street: data.client.Street, City: data.client.City, Country: data.client.Country, ZipCode: data.client.ZipCode } : prev
            );
          }
        })
        .catch(() => {});
    } else {
      // Pas d'auto-sélection backend : pré-peupler avec les candidats du matching si disponibles
      const candidates = localAnalysisResult?.client_matches;
      if (candidates && candidates.length > 0) {
        // Afficher directement les candidats triés par score — l'utilisateur choisit
        const candidateSapClients = candidates.map((c: any) => ({
          CardCode: c.card_code,
          CardName: c.card_name,
          EmailAddress: c.email_address,
          Country: c.country,
          City: c.city,
          similarity: c.score,
          _matchReason: c.match_reason,
          strong_signal_score: c.strong_signal_score ?? 0,
          nominal_score: c.nominal_score ?? c.score,
        }));
        setSapClients(candidateSapClients);
        setSearchPerformed(true);
        if (candidates[0]?.card_name) setSearchQuery(candidates[0].card_name);
      } else if (clientName && clientName !== 'Client inconnu') {
        setSearchQuery(clientName);
        searchClients(clientName);
      }
    }
  }, [clientName, doc?.businessPartner.CardCode, localAnalysisResult?.client_auto_validated]);

  // ── Sync ship_to par défaut depuis le client sélectionné ────────
  // Quand le client change (enrichissement inclus) et qu'aucune source LLM/SAP/user n'est active,
  // utiliser son adresse comme destination par défaut.
  useEffect(() => {
    if (shipToState.source !== 'client') return; // ne pas écraser une valeur déjà définie par l'utilisateur
    if (!selectedClient) return;
    setShipToState({
      text: selectedClient.CardName,
      sapCode: selectedClient.CardCode,
      address: {
        street: selectedClient.Street,
        city: selectedClient.City,
        zipCode: selectedClient.ZipCode,
        country: selectedClient.Country,
      },
      source: 'client',
      validated: false,
    });
  }, [selectedClient?.CardCode, selectedClient?.Street, selectedClient?.City, selectedClient?.Country]);

  // ── Auto-search SAP quand le LLM a extrait un ship_to ────────────
  const shipToLlmText = doc?.shipTo;
  useEffect(() => {
    if (!shipToLlmText) return;
    // Indiquer immédiatement qu'on a un texte LLM (non résolu)
    setShipToState({ text: shipToLlmText, source: 'llm', validated: false });
    setShipToProposal(null);
    setShipToResults([]);

    // Lancer la recherche SAP automatiquement
    setShipToSearching(true);
    fetchWithAuth(`/api/clients/search_ship_to?q=${encodeURIComponent(shipToLlmText)}&limit=10`)
      .then((r) => r.json())
      .then((data) => {
        const results: SapClient[] = (data.success && data.results?.length > 0)
          ? data.results.map((c: any) => ({ CardCode: c.CardCode, CardName: c.CardName, Street: c.Street, City: c.City, Country: c.Country, ZipCode: c.ZipCode }))
          : [];

        if (results.length === 1) {
          // 1 résultat : proposer sans valider
          setShipToProposal(results[0]);
          setShipToResults([]);
        } else if (results.length > 1) {
          // Plusieurs : afficher la liste
          setShipToResults(results);
          setShipToProposal(null);
        } else {
          // Aucun : garder texte libre LLM
          setShipToResults([]);
          setShipToProposal(null);
        }
      })
      .catch(() => {
        setShipToResults([]);
        setShipToProposal(null);
      })
      .finally(() => setShipToSearching(false));
  }, [shipToLlmText]);

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

    // Lignes ajoutées manuellement
    const manualDocLines = manualLines
      .filter((l) => l.ItemDescription.trim() !== '')
      .map((l) => ({
        ItemCode: l.ItemCode.trim() || undefined,
        ItemDescription: l.ItemDescription,
        Quantity: l.Quantity,
        UnitPrice: l.UnitPrice ?? undefined,
        DiscountPercent: 0,
      }));

    // Lignes fixes toujours ajoutées
    const fixedLines = [
      { ItemCode: 'A06572', ItemDescription: 'Emballage', Quantity: 1, UnitPrice: emballagePrice, DiscountPercent: 0 },
      { ItemCode: 'A07042', ItemDescription: 'Transport', Quantity: 1, UnitPrice: transportPrice, DiscountPercent: 0 },
    ];

    // Référence commande client (Form No, PO, etc.) → NumAtCard SAP
    const customerRef = localAnalysisResult?.customer_reference ?? undefined;

    const baseComments = comments || `Devis suite email: ${quote.email.subject || ''}`;
    const shipToNote = shipToState.text.trim() ? `\nLivraison : ${shipToState.text.trim()}` : '';

    return {
      CardCode: selectedClient!.CardCode,
      Comments: baseComments + shipToNote,
      NumAtCard: customerRef,
      ship_to: shipToState.text.trim() || undefined,
      email_id: quote.email.id,
      email_subject: quote.email.subject,
      DocumentLines: [...activeLines, ...manualDocLines, ...fixedLines],
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
      const response = await fetchWithAuth(`/api/clients/search_clients?q=${encodeURIComponent(query)}&source=sap&limit=10`);

      if (response.ok) {
        const data = await response.json();

        if (data.success && data.results && data.results.length > 0) {
          // Adapter le format de réponse
          const sapClients = data.results.map((client: any) => ({
            CardCode: client.CardCode,
            CardName: client.CardName,
            EmailAddress: client.EmailAddress || client.Email,
            Phone1: client.Phone1,
            City: client.City,
            Country: client.Country,
            ZipCode: client.ZipCode,
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

  // Recherche SAP ship_to (clients + fournisseurs)
  const searchShipTo = async (query: string) => {
    if (!query || query.length < 2) return;
    setShipToSearching(true);
    setShipToProposal(null);
    setShowManualShipTo(false);
    try {
      const response = await fetchWithAuth(`/api/clients/search_ship_to?q=${encodeURIComponent(query)}&limit=10`);
      if (response.ok) {
        const data = await response.json();
        const results: SapClient[] = (data.success && data.results?.length > 0)
          ? data.results.map((c: any) => ({
              CardCode: c.CardCode, CardName: c.CardName,
              Street: c.Street, City: c.City, Country: c.Country, ZipCode: c.ZipCode,
              // stocker CardType dans similarity pour ne pas modifier l'interface SapClient
              _cardType: c.CardType,
            } as any))
          : [];
        if (results.length === 1) {
          setShipToProposal(results[0]);
          setShipToResults([]);
        } else if (results.length > 1) {
          setShipToResults(results);
        } else {
          // Aucun résultat → proposer saisie manuelle
          setShipToResults([]);
          setShowManualShipTo(true);
          setManualShipTo({ name: query, street: '', zip: '', city: '', country: '' });
        }
      } else {
        setShipToResults([]);
        setShowManualShipTo(true);
        setManualShipTo({ name: query, street: '', zip: '', city: '', country: '' });
      }
    } catch {
      setShipToResults([]);
    } finally {
      setShipToSearching(false);
    }
  };

  // Confirmer une proposition SAP (1 résultat ou sélection dans la liste)
  const handleConfirmShipTo = (client: SapClient & { _cardType?: string }) => {
    const source = client._cardType === 'S' ? 'supplier' : 'sap';
    setShipToState({
      text: client.CardName,
      sapCode: client.CardCode,
      address: { street: client.Street, city: client.City, zipCode: client.ZipCode, country: client.Country },
      source,
      validated: true,
    });
    setShipToProposal(null);
    setShipToResults([]);
    setShipToSearchQuery('');
    setShowManualShipTo(false);
  };

  // Valider la saisie manuelle
  const handleManualShipTo = () => {
    setShipToState({
      text: manualShipTo.name || 'Destination manuelle',
      address: { street: manualShipTo.street, city: manualShipTo.city, zipCode: manualShipTo.zip, country: manualShipTo.country },
      source: 'manual',
      validated: true,
    });
    setShowManualShipTo(false);
    setShipToResults([]);
  };

  // L'utilisateur modifie manuellement le texte → source devient 'user', adresse perdue
  const handleShipToTextChange = (text: string) => {
    setShipToState({ text, source: 'user', validated: false });
    setShipToProposal(null);
    setShipToResults([]);
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
      setShowOverrideOptions(prev => ({ ...prev, [lineNum]: false }));
      triggerDraftSave(quantityOverrides, updated, selectedClient);
      toast.success('Article ignoré et exclu du devis');
    } catch (error: any) {
      toast.error(error.message || "Erreur lors de l'exclusion");
    }
  };

  // Résoudre une ambiguïté : l'utilisateur choisit un candidat parmi plusieurs
  const handleResolveAmbiguity = async (originalCode: string, chosenItemCode: string, chosenItemName: string) => {
    setResolveLoading(prev => ({ ...prev, [originalCode]: true }));
    try {
      const apiResult = await resolveProductAmbiguity(quote.email.id, originalCode, chosenItemCode);
      // Utiliser les product_matches retournés par l'API (contiennent poids + prix enrichis)
      const updatedPm = apiResult.product_matches || [];
      setLocalAnalysisResult((prev: any) => {
        if (!prev) return prev;
        return { ...prev, product_matches: updatedPm };
      });
      toast.success(`Article sélectionné : ${chosenItemCode} — ${chosenItemName}`);
    } catch (err: any) {
      toast.error(err.message || 'Erreur lors de la sélection');
    } finally {
      setResolveLoading(prev => ({ ...prev, [originalCode]: false }));
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
      setShowOverrideOptions(prev => ({ ...prev, [lineNum]: false }));
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
      setShowOverrideOptions(prev => ({ ...prev, [lineNum]: false }));
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
      const response = await fetchWithAuth(`/api/sap/items?search=${encodeURIComponent(itemCode)}&limit=1`);

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
    <div className="space-y-6 animate-fade-in w-full max-w-none">
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
          {/* Vérification solvabilité */}
          <ClientRiskBadge risk={(localAnalysisResult as any)?.client_risk} />
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

          {/* Bannière ambiguïté : plusieurs candidats détectés, sélection requise */}
          {searchPerformed && !selectedClient && sapClients.length > 1 && !localAnalysisResult?.client_auto_validated && (
            <div className="flex items-start gap-2 p-3 rounded-lg border border-amber-400 bg-amber-50 dark:bg-amber-950/20 text-sm">
              <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-800 dark:text-amber-300">
                  {sapClients.length} clients candidats détectés — sélection requise
                </p>
                <p className="text-amber-700 dark:text-amber-400 text-xs mt-0.5">
                  Le système ne peut pas choisir automatiquement. Sélectionnez le bon client ci-dessous.
                </p>
                {/* Signaux géographiques disponibles mais insuffisants pour trancher */}
                {(localAnalysisResult?.detected_country || localAnalysisResult?.detected_city) && (
                  <p className="text-amber-600 dark:text-amber-500 text-xs mt-1">
                    Signal géo détecté :
                    {localAnalysisResult.detected_city && ` ville=${localAnalysisResult.detected_city}`}
                    {localAnalysisResult.detected_country && ` pays=${localAnalysisResult.detected_country}`}
                    {' '}— vérifiez le pays du client dans la liste.
                  </p>
                )}
              </div>
            </div>
          )}

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
                      <div className="flex-1 min-w-0">
                        <p className="font-medium">{client.CardName}</p>
                        <p className="text-xs text-muted-foreground">
                          Code: {client.CardCode}
                          {client.City && ` • ${client.City}`}
                          {client.Country && ` (${client.Country})`}
                          {client.EmailAddress && ` • ${client.EmailAddress}`}
                        </p>
                        {/* Raisons de matching (explicabilité) */}
                        {(client as any)._matchReason && (
                          <p className="text-xs text-muted-foreground/70 mt-0.5 italic truncate">
                            {(client as any)._matchReason}
                          </p>
                        )}
                        {/* Badge signal géographique fort */}
                        {(client as any).strong_signal_score > 0 && (
                          <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 mt-0.5">
                            Signal géo +{(client as any).strong_signal_score}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                        {(client as any).similarity != null && (
                          <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                            (client as any).similarity >= 90
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : (client as any).similarity >= 70
                              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                              : 'bg-muted text-muted-foreground'
                          }`}>
                            {(client as any).similarity}%
                          </span>
                        )}
                        {selectedClient?.CardCode === client.CardCode && (
                          <CheckCircle className="w-5 h-5 text-primary" />
                        )}
                      </div>
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
                {localAnalysisResult?.client_auto_validated
                  ? 'Client auto-sélectionné'
                  : 'Client SAP sélectionné'}
              </p>
              <p className="font-medium mt-1">{selectedClient.CardName}</p>
              <p className="text-xs text-muted-foreground">Code: {selectedClient.CardCode}</p>
              {/* Raison de l'auto-sélection (explicabilité) */}
              {localAnalysisResult?.client_auto_validated && localAnalysisResult?.auto_select_reason && (
                <p className="text-xs text-success/80 mt-1 italic">
                  {localAnalysisResult.auto_select_reason}
                </p>
              )}
              {/* Signaux géographiques détectés */}
              {(localAnalysisResult?.detected_country || localAnalysisResult?.detected_city) && (
                <p className="text-xs text-muted-foreground mt-1">
                  Signal géo :
                  {localAnalysisResult.detected_city && ` ville=${localAnalysisResult.detected_city}`}
                  {localAnalysisResult.detected_country && ` pays=${localAnalysisResult.detected_country}`}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Adresse de livraison */}
      <Card className="card-elevated">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <MapPin className="w-5 h-5 text-primary" />
            Adresse de livraison
            {shipToState.validated && (
              <Badge variant="outline" className="ml-auto text-xs border-success text-success">Confirmée</Badge>
            )}
            {!shipToState.validated && shipToState.source === 'client' && (
              <Badge variant="outline" className="ml-auto text-xs text-muted-foreground">Adresse client par défaut</Badge>
            )}
            {!shipToState.validated && shipToState.source === 'llm' && (
              <Badge variant="outline" className="ml-auto text-xs border-warning text-warning">Extrait — à confirmer</Badge>
            )}
          </CardTitle>
          <p className="text-xs text-muted-foreground">Toujours vérifier avant envoi. Utilisé pour le calcul DHL.</p>
        </CardHeader>
        <CardContent className="space-y-3">

          {/* Champ texte éditable */}
          <div className="relative">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Destination (ex: BDF, Site Lyon…)"
              value={shipToState.text}
              onChange={(e) => handleShipToTextChange(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Adresse résolue (SAP) */}
          {shipToState.address && (
            <div className="p-3 bg-success/10 border border-success/20 rounded-lg flex items-start justify-between gap-2">
              <div className="space-y-1">
                <p className="text-xs font-medium text-success">
                  {shipToState.source === 'client' ? 'Adresse client (par défaut)' : 'Adresse de livraison confirmée'}
                </p>
                <p className="text-sm font-medium">{shipToState.text}</p>
                <ShipToAddressBlock addr={shipToState.address} />
                {!isAddressComplete(shipToState.address) && (
                  <p className="text-xs text-warning flex items-center gap-1 mt-1">
                    <AlertTriangle className="w-3 h-3" />
                    Adresse incomplète — calcul DHL bloqué
                  </p>
                )}
                {shipToState.sapCode && (
                  <p className="text-xs text-muted-foreground opacity-60">{shipToState.sapCode}</p>
                )}
              </div>
              <button
                className="text-muted-foreground hover:text-destructive flex-shrink-0 mt-1"
                onClick={() => setShipToState((s) => ({ ...s, address: undefined, sapCode: undefined, source: 'user', validated: false }))}
                title="Effacer l'adresse"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          )}

          {/* Avertissement : adresse manquante → DHL bloqué */}
          {!shipToState.address && (
            <p className="text-xs text-warning flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Adresse non structurée — vérification requise. Calcul DHL désactivé.
            </p>
          )}

          {/* Recherche dans SAP */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Rechercher une adresse (client / fournisseur)…"
                value={shipToSearchQuery}
                onChange={(e) => setShipToSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchShipTo(shipToSearchQuery)}
                className="pl-10"
              />
            </div>
            <Button
              variant="outline"
              onClick={() => searchShipTo(shipToSearchQuery)}
              disabled={shipToSearching || shipToSearchQuery.length < 2}
            >
              {shipToSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Rechercher'}
            </Button>
          </div>

          {/* Recherche auto en cours */}
          {shipToSearching && !shipToSearchQuery && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="w-3 h-3 animate-spin" />
              Recherche SAP automatique en cours…
            </div>
          )}

          {/* Proposition automatique (1 résultat) */}
          {shipToProposal && (
            <div className="border border-primary/30 rounded-lg p-3 bg-primary/5 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-xs font-medium text-primary">Suggestion SAP automatique</p>
                {(shipToProposal as any)?._cardType === 'S' && (
                  <Badge variant="outline" className="text-xs">Fournisseur</Badge>
                )}
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm">{shipToProposal.CardName}</p>
                  <ShipToAddressBlock
                    addr={{ street: shipToProposal.Street, city: shipToProposal.City, zipCode: shipToProposal.ZipCode, country: shipToProposal.Country }}
                    className="mt-1"
                  />
                  <p className="text-xs text-muted-foreground opacity-60 mt-1">{shipToProposal.CardCode}</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => handleConfirmShipTo(shipToProposal)}>
                    <CheckCircle className="w-3 h-3 mr-1" /> Confirmer
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShipToProposal(null)}>
                    <X className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Liste de suggestions (plusieurs résultats) */}
          {shipToResults.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-muted/50 px-3 py-2 text-sm font-medium">
                {shipToResults.length} résultat{shipToResults.length > 1 ? 's' : ''} SAP — sélectionnez
              </div>
              <div className="divide-y max-h-48 overflow-y-auto">
                {shipToResults.map((c) => (
                  <div
                    key={c.CardCode}
                    className="p-3 cursor-pointer hover:bg-muted/50 transition-colors flex items-center justify-between"
                    onClick={() => handleConfirmShipTo(c)}
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-sm">{c.CardName}</p>
                        {(c as any)._cardType === 'S' && (
                          <Badge variant="outline" className="text-xs">Fournisseur</Badge>
                        )}
                      </div>
                      <ShipToAddressBlock
                        addr={{ street: c.Street, city: c.City, zipCode: c.ZipCode, country: c.Country }}
                        className="mt-1"
                      />
                      <p className="text-xs text-muted-foreground opacity-60 mt-1">{c.CardCode}</p>
                    </div>
                    <CheckCircle className="w-4 h-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Formulaire saisie manuelle (aucun résultat SAP) */}
          {showManualShipTo && (
            <div className="border border-dashed rounded-lg p-3 space-y-2 bg-muted/20">
              <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <AlertTriangle className="w-3 h-3 text-warning" />
                Aucun résultat SAP — saisie manuelle
              </p>
              <div className="grid grid-cols-2 gap-2">
                <div className="col-span-2">
                  <Input placeholder="Nom / société" value={manualShipTo.name}
                    onChange={(e) => setManualShipTo((p) => ({ ...p, name: e.target.value }))} className="text-sm" />
                </div>
                <div className="col-span-2">
                  <Input placeholder="Rue" value={manualShipTo.street}
                    onChange={(e) => setManualShipTo((p) => ({ ...p, street: e.target.value }))} className="text-sm" />
                </div>
                <Input placeholder="Code postal" value={manualShipTo.zip}
                  onChange={(e) => setManualShipTo((p) => ({ ...p, zip: e.target.value }))} className="text-sm" />
                <Input placeholder="Ville" value={manualShipTo.city}
                  onChange={(e) => setManualShipTo((p) => ({ ...p, city: e.target.value }))} className="text-sm" />
                <div className="col-span-2">
                  <Input placeholder="Pays (ex: FR, DE, IT…)" value={manualShipTo.country}
                    onChange={(e) => setManualShipTo((p) => ({ ...p, country: e.target.value }))} className="text-sm" />
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <Button size="sm" onClick={handleManualShipTo}
                  disabled={!manualShipTo.city || !manualShipTo.country}>
                  <CheckCircle className="w-3 h-3 mr-1" /> Valider
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowManualShipTo(false)}>
                  <X className="w-3 h-3" />
                </Button>
              </div>
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
            <Button
              variant="outline"
              size="sm"
              className="ml-auto h-7 text-xs"
              onClick={() => {
                manualLineCounter.current += 1;
                setManualLines(prev => [...prev, { id: manualLineCounter.current, ItemCode: '', ItemDescription: '', Quantity: 1, UnitPrice: null }]);
              }}
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              Ajouter une ligne
            </Button>
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
                            // Calculer la marge réelle depuis le prix fournisseur
                            const sp = (line as any).supplier_price;
                            const actualMargin = sp > 0 ? ((newPrice - sp) / sp) * 100 : undefined;
                            // Mettre à jour le state React (déclenche re-render)
                            setEnrichedArticles(prev => prev.map((a: any) =>
                              a.LineNum === line.LineNum
                                ? { ...a, unit_price: newPrice, line_total: newPrice * (quantityOverrides[a.LineNum] ?? a.Quantity ?? 1), pricing_case: 'CAS_MANUAL', margin_applied: actualMargin ?? a.margin_applied }
                                : a
                            ));
                          }}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        {(() => {
                          const isIgnored = !!ignoredItems[line.LineNum];
                          const isNotFound = line.not_found_in_sap === true || (status && !status.found);
                          const candidates = pendingByCode.get(line.ItemCode) || pendingByCode.get(line.original_code);
                          const isPendingSelection = !!candidates && candidates.length > 0;

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

                          // Désambiguïsation : priorité absolue sur "Trouvé"
                          if (isPendingSelection) {
                            return (
                              <div className="space-y-1.5">
                                <Badge variant="outline" className="text-amber-600 border-amber-400 bg-amber-50">
                                  <AlertCircle className="w-3 h-3 mr-1" />
                                  {candidates!.length} candidats
                                </Badge>
                                <div className="space-y-1 text-left max-w-[200px]">
                                  {candidates!.map((c: any) => (
                                    <button
                                      key={c.item_code}
                                      disabled={!!resolveLoading[line.original_code || line.ItemCode]}
                                      onClick={() => handleResolveAmbiguity(line.original_code || line.ItemCode, c.item_code, c.item_name)}
                                      className="flex flex-col w-full text-left px-1.5 py-1 rounded border border-transparent hover:border-amber-400 hover:bg-amber-50 transition-colors text-xs disabled:opacity-50"
                                    >
                                      <span className="font-mono font-semibold text-primary">{c.item_code}</span>
                                      <span className="text-muted-foreground truncate">{c.item_name}</span>
                                    </button>
                                  ))}
                                  {resolveLoading[line.original_code || line.ItemCode] && (
                                    <div className="flex items-center gap-1 text-xs text-muted-foreground px-1">
                                      <Loader2 className="w-3 h-3 animate-spin" /> Sélection...
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          }

                          if (status?.found) {
                            // Mode normal : badge + icône crayon pour ouvrir les options
                            if (!showOverrideOptions[line.LineNum]) {
                              return (
                                <div className="flex flex-col items-center gap-1">
                                  <div className="flex items-center gap-1">
                                    <Badge className="bg-success/10 text-success border-success/20">
                                      <CheckCircle className="w-3 h-3 mr-1" />
                                      Trouvé
                                    </Badge>
                                    <Button
                                      size="icon"
                                      variant="ghost"
                                      className="h-5 w-5 text-muted-foreground hover:text-foreground"
                                      title="Modifier la correspondance"
                                      onClick={() => setShowOverrideOptions(prev => ({ ...prev, [line.LineNum]: true }))}
                                    >
                                      <Pencil className="w-3 h-3" />
                                    </Button>
                                  </div>
                                  {status.message && (
                                    <p className="text-xs text-muted-foreground mt-1">{status.message}</p>
                                  )}
                                </div>
                              );
                            }

                            // Mode override : mêmes contrôles que "Non trouvé"
                            if (showManualInput[line.LineNum]) {
                              return (
                                <div className="space-y-1.5">
                                  <Badge className="bg-success/10 text-success border-success/20">
                                    <CheckCircle className="w-3 h-3 mr-1" />
                                    Trouvé
                                  </Badge>
                                  <div className="flex items-center gap-1">
                                    <Input
                                      placeholder="Code SAP..."
                                      value={manualCodeInput[line.LineNum] || ''}
                                      onChange={(e) => setManualCodeInput(prev => ({ ...prev, [line.LineNum]: e.target.value }))}
                                      onKeyDown={(e) => e.key === 'Enter' && handleManualCodeSubmit(line.LineNum, status?.itemCode || line.ItemCode || '')}
                                      className="h-7 text-xs w-24 px-1"
                                      autoFocus
                                    />
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 w-7 p-0"
                                      onClick={() => handleManualCodeSubmit(line.LineNum, status?.itemCode || line.ItemCode || '')}
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
                                </div>
                              );
                            }

                            if (showRetryResults[line.LineNum]) {
                              return (
                                <div className="space-y-1.5">
                                  <Badge className="bg-success/10 text-success border-success/20">
                                    <CheckCircle className="w-3 h-3 mr-1" />
                                    Trouvé
                                  </Badge>
                                  <div className="space-y-1 text-left max-w-[180px]">
                                    {(retryResults[line.LineNum] || []).length > 0 ? (
                                      retryResults[line.LineNum].map((item: any) => (
                                        <button
                                          key={item.item_code}
                                          className="flex flex-col w-full text-left px-1.5 py-1 rounded hover:bg-muted/60 transition-colors text-xs"
                                          onClick={() => handleSelectRetryResult(line.LineNum, status?.itemCode || line.ItemCode || '', item.item_code, item.item_name)}
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
                                </div>
                              );
                            }

                            // Boutons d'action override
                            return (
                              <div className="space-y-1.5">
                                <Badge className="bg-success/10 text-success border-success/20">
                                  <CheckCircle className="w-3 h-3 mr-1" />
                                  Trouvé
                                </Badge>
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
                                    onClick={() => handleRetrySearch(line.LineNum, status?.itemCode || line.ItemCode || '', line.ItemDescription)}
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
                                    onClick={() => handleIgnoreItem(line.LineNum, status?.itemCode || line.ItemCode || '')}
                                  >
                                    <X className="w-3 h-3 mr-1 flex-shrink-0" />
                                    Ignorer
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 text-xs justify-start px-2 text-muted-foreground"
                                    onClick={() => setShowOverrideOptions(prev => ({ ...prev, [line.LineNum]: false }))}
                                  >
                                    <X className="w-3 h-3 mr-1 flex-shrink-0" />
                                    Annuler
                                  </Button>
                                </div>
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

              {/* ── Lignes manuelles ── */}
              {manualLines.map((ml) => (
                <TableRow key={ml.id} className="bg-blue-50/40 dark:bg-blue-950/20">
                  <TableCell>
                    <Input
                      value={ml.ItemCode}
                      onChange={(e) => setManualLines(prev => prev.map(l => l.id === ml.id ? { ...l, ItemCode: e.target.value } : l))}
                      placeholder="Code SAP"
                      className="h-7 text-sm font-mono w-28 px-1"
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      value={ml.ItemDescription}
                      onChange={(e) => setManualLines(prev => prev.map(l => l.id === ml.id ? { ...l, ItemDescription: e.target.value } : l))}
                      placeholder="Désignation"
                      className="h-7 text-sm px-1 w-full"
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <Input
                      type="number"
                      min="1"
                      value={ml.Quantity}
                      onChange={(e) => setManualLines(prev => prev.map(l => l.id === ml.id ? { ...l, Quantity: Math.max(1, Number(e.target.value) || 1) } : l))}
                      className="h-7 text-sm text-right w-16 px-1"
                    />
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground text-sm">—</TableCell>
                  <TableCell className="text-right text-muted-foreground text-sm">—</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={ml.UnitPrice ?? ''}
                        onChange={(e) => setManualLines(prev => prev.map(l => l.id === ml.id ? { ...l, UnitPrice: e.target.value === '' ? null : Number(e.target.value) } : l))}
                        placeholder="0.00"
                        className="h-7 text-sm text-right w-24 px-1"
                      />
                      <span className="text-xs text-muted-foreground">€</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex flex-col items-center gap-1">
                      <Badge variant="secondary" className="text-xs">Manuel</Badge>
                      <button
                        onClick={() => setManualLines(prev => prev.filter(l => l.id !== ml.id))}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                        title="Supprimer cette ligne"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}

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
                  <div className="flex items-center gap-2 flex-wrap">
                    <span>Transport</span>
                    {transportPriceOverride === null && totals.totalWeight > 0 && (
                      <span className="text-xs text-muted-foreground">({totals.totalWeight?.toFixed(3)} kg × 2)</span>
                    )}
                    {transportPriceOverride !== null && (
                      <span className="text-xs text-blue-600 font-medium">DHL validé</span>
                    )}
                    <ShippingCalculatorPanel
                      articles={enrichedArticles}
                      quantityOverrides={quantityOverrides}
                      ignoredItems={ignoredItems}
                      totalWeight={totals.totalWeight ?? 0}
                      currentTransportPrice={transportPrice}
                      isDhlActive={transportPriceOverride !== null}
                      onTransportPriceSet={(price) => {
                        setTransportPriceOverride(price);
                        triggerDraftSave(quantityOverrides, ignoredItems, selectedClient, price);
                      }}
                      defaultCity={shipToState.address?.city ?? selectedClient?.City}
                      defaultCountry={shipToState.address?.country ?? selectedClient?.Country}
                      defaultPostalCode={shipToState.address?.zipCode ?? selectedClient?.ZipCode}
                      disabled={!shipToState.address || !isAddressComplete(shipToState.address)}
                    />
                  </div>
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
                          onClick={() => {
                            setTransportPriceOverride(null);
                            setEditingFixedLine(null);
                            triggerDraftSave(quantityOverrides, ignoredItems, selectedClient, null);
                          }}>
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
            analysisResult={localAnalysisResult as any}
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

      {/* Commentaires du devis */}
      <Card>
        <CardContent className="pt-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Commentaires du devis</label>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground h-auto py-0.5 px-2"
                onClick={() => setComments(DEFAULT_DELIVERY_COMMENT)}
              >
                Réinitialiser
              </Button>
            </div>
            <Textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Commentaires transmis à SAP (délai livraison, conditions, remarques…)"
              rows={3}
              className="resize-y text-sm"
            />
          </div>
        </CardContent>
      </Card>

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
              onClick={handleReanalyzeLocal}
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
          const hasUncalculatedPrices = articles.some((line: any) => {
            if (ignoredItems[line.LineNum]) return false;
            if (line.not_found_in_sap === true) return false; // déjà bloqué par hasUnresolved
            return line.unit_price == null;
          });
          const alreadySent = existingQuote?.found === true;
          const clientRisk = (localAnalysisResult as any)?.client_risk;
          const isClientBlocked = clientRisk?.status === 'BLOCKED';
          const isDisabled = !doc || articles.length === 0 || (!selectedClient && !createNewClient) || hasUnresolved || hasUncalculatedPrices || isPreviewing || (isClientBlocked && !forceBlocked);
          const label = isClientBlocked && !forceBlocked
            ? 'Client en liquidation – création bloquée'
            : alreadySent
              ? `Recréer (N° ${existingQuote?.sap_doc_num ?? '?'})`
              : !selectedClient && !createNewClient
                ? 'Sélectionnez un client'
                : hasUnresolved
                  ? 'Résolvez les articles non trouvés'
                  : hasUncalculatedPrices
                    ? 'Saisissez les prix manquants'
                    : isPreviewing
                      ? 'Préparation...'
                      : articles.length > 0
                        ? 'Créer le devis SAP'
                        : 'Extraction incomplète';
          return (
            <div className="flex flex-col items-end gap-2">
              {isClientBlocked && !forceBlocked && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground underline underline-offset-2 hover:text-destructive transition-colors"
                  onClick={() => setShowBlockedConfirm(true)}
                >
                  Forcer la création malgré la liquidation
                </button>
              )}
              <Button
                onClick={handlePreviewQuote}
                size="lg"
                disabled={isDisabled}
                variant={isClientBlocked && !forceBlocked ? 'destructive' : alreadySent ? 'outline' : 'default'}
                className={alreadySent && !(isClientBlocked && !forceBlocked) ? 'border-yellow-500 text-yellow-700 hover:bg-yellow-50' : ''}
              >
                {isPreviewing
                  ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  : isClientBlocked && !forceBlocked
                    ? <XCircle className="w-4 h-4 mr-2" />
                    : alreadySent
                      ? <AlertTriangle className="w-4 h-4 mr-2 text-yellow-600" />
                      : <CheckCircle className="w-4 h-4 mr-2" />
                }
                {label}
              </Button>
              {/* Modale de confirmation forçage */}
              <Dialog open={showBlockedConfirm} onOpenChange={setShowBlockedConfirm}>
                <DialogContent className="max-w-sm">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-destructive">
                      <AlertTriangle className="w-5 h-5" />
                      Confirmation requise
                    </DialogTitle>
                    <DialogDescription>
                      Ce client est en <strong>liquidation judiciaire</strong> selon Pappers.
                      Créer un devis présente un risque financier élevé.
                      <br /><br />
                      Confirmez-vous la création malgré ce risque ?
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter className="gap-2">
                    <Button variant="outline" onClick={() => setShowBlockedConfirm(false)}>Annuler</Button>
                    <Button
                      variant="destructive"
                      onClick={() => { setForceBlocked(true); setShowBlockedConfirm(false); }}
                    >
                      Forcer la création
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
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
                {localAnalysisResult?.customer_reference && (
                  <Badge variant="secondary" className="ml-auto font-mono text-xs">
                    Réf. client : {localAnalysisResult.customer_reference}
                  </Badge>
                )}
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
