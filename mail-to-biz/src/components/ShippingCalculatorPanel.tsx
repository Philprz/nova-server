import { fetchWithAuth } from '@/lib/fetchWithAuth';
/**
 * ShippingCalculatorPanel
 * ─────────────────────────────────────────────────────────────────────────────
 * Panneau de calcul transport DHL Express intégré dans QuoteSummary.
 *
 * Flux utilisateur :
 *   1. L'utilisateur voit la ligne Transport avec le tarif estimé (poids × 2)
 *   2. Il clique "Calculer avec DHL Express"
 *   3. Un dialog s'ouvre avec les champs destination
 *   4. L'API /api/packing/calculate-and-ship est appelée
 *   5. La suggestion de colisage s'affiche
 *   6. Les tarifs DHL apparaissent (sélectionnables)
 *   7. "Valider ce tarif" → met à jour la ligne Transport du devis
 */

import { useState, useEffect } from 'react';
import { Truck, Package, ChevronRight, Loader2, CheckCircle, AlertTriangle, X, Percent } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';


// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface PackageResult {
  box_type: string;
  label: string;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  weight_kg: number;
  items_count: number;
}

interface DHLRate {
  carrier: string;
  service_code: string;
  service_name: string;
  price: number;
  currency: string;
  delivery_days: number;
  delivery_date?: string;
}

interface PackingResult {
  packages: PackageResult[];
  total_weight_kg: number;
  total_volume_m3: number;
  box_count: number;
  summary: string;
  warnings: string[];
}

interface ShippingResult {
  success: boolean;
  rates: DHLRate[];
  best_rate?: DHLRate;
  errors?: string[];
}

interface ArticleForPacking {
  item_code: string;
  quantity: number;
  weight_kg?: number;
  length_cm?: number;
  width_cm?: number;
  height_cm?: number;
}

interface ShippingCalculatorPanelProps {
  /** Articles enrichis du devis (avec weight_unit_value) */
  articles: any[];
  /** Substitutions de quantités saisies manuellement */
  quantityOverrides: Record<number, number>;
  /** Articles exclus du devis */
  ignoredItems: Record<number, boolean>;
  /** Poids total déjà calculé (kg) */
  totalWeight: number;
  /** Prix transport actuellement affiché */
  currentTransportPrice: number;
  /** Callback pour mettre à jour le prix transport validé */
  onTransportPriceSet: (price: number) => void;
  /** Indique si un tarif DHL a déjà été validé (depuis le state parent, persiste les remontages) */
  isDhlActive?: boolean;
  /** Adresse client pré-remplie (depuis SAP) */
  defaultCity?: string;
  defaultCountry?: string;
  defaultPostalCode?: string;
  /** Désactiver le calcul DHL si aucune adresse de livraison résolue */
  disabled?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pays les plus fréquents pour RONDOT-SAS
// ─────────────────────────────────────────────────────────────────────────────

const COMMON_COUNTRIES = [
  { code: 'FR', label: 'France' },
  { code: 'BE', label: 'Belgique' },
  { code: 'DE', label: 'Allemagne' },
  { code: 'GB', label: 'Royaume-Uni' },
  { code: 'ES', label: 'Espagne' },
  { code: 'IT', label: 'Italie' },
  { code: 'NL', label: 'Pays-Bas' },
  { code: 'CH', label: 'Suisse' },
  { code: 'PT', label: 'Portugal' },
  { code: 'AE', label: 'Émirats Arabes Unis' },
  { code: 'US', label: 'États-Unis' },
  { code: 'CN', label: 'Chine' },
  { code: 'AU', label: 'Australie' },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatPrice(price: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency }).format(price);
}

function boxTypeIcon(boxType: string): string {
  switch (boxType) {
    case 'S': return '📦';
    case 'M': return '📦';
    case 'L': return '🗳️';
    case 'PALLET': return '🏗️';
    case 'CUSTOM': return '📐';
    default: return '📦';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Composant principal
// ─────────────────────────────────────────────────────────────────────────────

export function ShippingCalculatorPanel({
  articles,
  quantityOverrides,
  ignoredItems,
  totalWeight,
  currentTransportPrice,
  onTransportPriceSet,
  isDhlActive = false,
  defaultCity,
  defaultCountry,
  defaultPostalCode,
  disabled = false,
}: ShippingCalculatorPanelProps) {
  const [dialogOpen, setDialogOpen] = useState(false);

  // Formulaire destination — pré-rempli avec l'adresse client SAP
  const [postalCode, setPostalCode] = useState(defaultPostalCode ?? '');
  const [city, setCity] = useState(defaultCity ?? '');
  const [country, setCountry] = useState(defaultCountry ?? 'FR');

  // Sync si le client change
  useEffect(() => {
    if (defaultPostalCode !== undefined) setPostalCode(defaultPostalCode);
  }, [defaultPostalCode]);
  useEffect(() => {
    if (defaultCity !== undefined) setCity(defaultCity);
  }, [defaultCity]);
  useEffect(() => {
    if (defaultCountry !== undefined) setCountry(defaultCountry);
  }, [defaultCountry]);

  // Résultats
  const [isCalculating, setIsCalculating] = useState(false);
  const [packingResult, setPackingResult] = useState<PackingResult | null>(null);
  const [shippingResult, setShippingResult] = useState<ShippingResult | null>(null);
  const [selectedRate, setSelectedRate] = useState<DHLRate | null>(null);

  // Marge transport (%)
  const [transportMargin, setTransportMargin] = useState(40);

  // Prix validé
  const [validatedPrice, setValidatedPrice] = useState<number | null>(null);

  // Saisie manuelle des dimensions colis (mode "Recalculer")
  const [showDimensionEdit, setShowDimensionEdit] = useState(false);
  const [customLength, setCustomLength] = useState<string>('');
  const [customWidth, setCustomWidth] = useState<string>('');
  const [customHeight, setCustomHeight] = useState<string>('');

  // ─────────────────────────────────────────────────────
  // Construction du payload packing depuis les articles
  // ─────────────────────────────────────────────────────

  const buildPackingItems = (): ArticleForPacking[] => {
    return articles
      .filter((a: any) => !ignoredItems[a.LineNum])
      .map((a: any) => {
        const qty = quantityOverrides[a.LineNum] ?? a.Quantity ?? 1;
        return {
          item_code: a.ItemCode || a.item_code || 'UNKNOWN',
          quantity: qty,
          weight_kg: a.weight_unit_value ?? undefined,
        };
      })
      .filter((item) => item.quantity > 0);
  };

  // ─────────────────────────────────────────────────────
  // Appel API calculate-and-ship
  // ─────────────────────────────────────────────────────

  const handleCalculate = async () => {
    if (!postalCode.trim() || !city.trim()) {
      toast.error('Veuillez saisir le code postal et la ville de destination');
      return;
    }

    const items = buildPackingItems();
    if (items.length === 0) {
      toast.error('Aucun article valide dans le devis');
      return;
    }

    setIsCalculating(true);
    setPackingResult(null);
    setShippingResult(null);
    setSelectedRate(null);
    setShowDimensionEdit(false);

    try {
      const params = new URLSearchParams({
        destination_postal_code: postalCode.trim(),
        destination_city: city.trim().toUpperCase(),
        destination_country: country,
        declared_value: '100',
      });

      const response = await fetchWithAuth(
        `/api/packing/calculate-and-ship?${params.toString()}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Erreur ${response.status}`);
      }

      if (data.packing) {
        setPackingResult(data.packing);
      }

      if (data.shipping) {
        setShippingResult(data.shipping);
        // Pré-sélectionner le meilleur tarif
        if (data.shipping.best_rate) {
          setSelectedRate(data.shipping.best_rate);
        }
      }

      if (!data.success) {
        toast.warning('Calcul partiel — vérifiez les résultats');
      }
    } catch (err: any) {
      console.error('Erreur calculate-and-ship:', err);
      toast.error(`Erreur : ${err.message || 'Impossible de contacter le serveur'}`);
    } finally {
      setIsCalculating(false);
    }
  };

  // ─────────────────────────────────────────────────────
  // Validation du tarif sélectionné
  // ─────────────────────────────────────────────────────

  const handleValidateRate = () => {
    if (!selectedRate) return;
    const clientPrice = Math.round(selectedRate.price * (1 + transportMargin / 100) * 100) / 100;
    setValidatedPrice(clientPrice);
    onTransportPriceSet(clientPrice);
    setDialogOpen(false);
    toast.success(
      `Transport DHL validé : ${formatPrice(clientPrice)} (marge ${transportMargin}%) — ${selectedRate.service_name} (${selectedRate.delivery_days}j)`
    );
  };

  const handleReset = () => {
    // Pré-remplir avec les dimensions du 1er colis suggéré
    if (packingResult && packingResult.packages.length > 0) {
      const pkg = packingResult.packages[0];
      setCustomLength(String(pkg.length_cm));
      setCustomWidth(String(pkg.width_cm));
      setCustomHeight(String(pkg.height_cm));
    } else {
      setCustomLength('');
      setCustomWidth('');
      setCustomHeight('');
    }
    setShowDimensionEdit(true);
  };

  const handleCustomCalculate = async () => {
    const l = parseFloat(customLength);
    const w = parseFloat(customWidth);
    const h = parseFloat(customHeight);

    if (!l || !w || !h || l <= 0 || w <= 0 || h <= 0) {
      toast.error('Veuillez saisir des dimensions valides (L, l, H > 0)');
      return;
    }
    if (!postalCode.trim() || !city.trim()) {
      toast.error('Veuillez saisir le code postal et la ville de destination');
      return;
    }

    setIsCalculating(true);
    setShippingResult(null);
    setSelectedRate(null);

    try {
      const params = new URLSearchParams({
        destination_postal_code: postalCode.trim(),
        destination_city: city.trim().toUpperCase(),
        destination_country: country,
        declared_value: '100',
      });

      const response = await fetchWithAuth(
        `/api/packing/custom-and-ship?${params.toString()}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            weight_kg: totalWeight > 0 ? totalWeight : 1,
            length_cm: l,
            width_cm: w,
            height_cm: h,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Erreur ${response.status}`);
      }

      // Mettre à jour le packingResult avec les dimensions manuelles
      if (data.package) {
        const volume_m3 = (l * w * h) / 1_000_000;
        setPackingResult({
          packages: [{
            box_type: 'CUSTOM',
            label: 'Colis personnalisé',
            length_cm: l,
            width_cm: w,
            height_cm: h,
            weight_kg: data.package.weight_kg,
            items_count: 1,
          }],
          total_weight_kg: data.package.weight_kg,
          total_volume_m3: volume_m3,
          box_count: 1,
          summary: `1 colis ${l}×${w}×${h} cm — ${data.package.weight_kg} kg`,
          warnings: [],
        });
      }

      if (data.shipping) {
        setShippingResult(data.shipping);
        if (data.shipping.best_rate) {
          setSelectedRate(data.shipping.best_rate);
        }
      }

      setShowDimensionEdit(false);
    } catch (err: any) {
      console.error('Erreur custom-and-ship:', err);
      toast.error(`Erreur : ${err.message || 'Impossible de contacter le serveur'}`);
    } finally {
      setIsCalculating(false);
    }
  };

  // ─────────────────────────────────────────────────────
  // Rendu de la ligne Transport dans le tableau devis
  // ─────────────────────────────────────────────────────

  return (
    <>
      {/* ── Bouton DHL intégré dans la ligne Transport ── */}
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs gap-1 border-blue-200 text-blue-700 hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed"
        onClick={() => !disabled && setDialogOpen(true)}
        disabled={disabled}
        title={disabled ? "Confirmez d'abord l'adresse de livraison" : undefined}
      >
        <Truck className="h-3 w-3" />
        {(isDhlActive || validatedPrice !== null) ? 'Recalculer DHL' : 'Calculer avec DHL Express'}
      </Button>

      {/* ── Dialog principal ── */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Truck className="h-4 w-4 text-blue-600" />
              Calcul transport DHL Express
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">

            {/* ── Résumé poids ── */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/40 rounded-md px-3 py-2">
              <Package className="h-4 w-4" />
              <span>
                Poids total estimé : <strong>{totalWeight.toFixed(2)} kg</strong>
                {totalWeight === 0 && (
                  <span className="text-amber-600 ml-2">
                    — Poids non renseigné dans les tarifs fournisseurs
                  </span>
                )}
              </span>
            </div>

            {/* ── Formulaire destination ── */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Adresse de livraison</h4>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="ship-postal" className="text-xs">Code postal</Label>
                  <Input
                    id="ship-postal"
                    placeholder="ex: 75001, DUBAI, SW1A..."
                    value={postalCode}
                    onChange={(e) => setPostalCode(e.target.value)}
                    className="h-8 text-sm"
                    disabled={isCalculating}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="ship-city" className="text-xs">Ville</Label>
                  <Input
                    id="ship-city"
                    placeholder="ex: PARIS"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    className="h-8 text-sm"
                    disabled={isCalculating}
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Pays</Label>
                <Select value={country} onValueChange={setCountry} disabled={isCalculating}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {/* Si le pays du client n'est pas dans la liste, l'afficher en premier */}
                    {country && !COMMON_COUNTRIES.find((c) => c.code === country) && (
                      <SelectItem key={country} value={country}>
                        {country}
                      </SelectItem>
                    )}
                    {COMMON_COUNTRIES.map((c) => (
                      <SelectItem key={c.code} value={c.code}>
                        {c.label} ({c.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Button
                onClick={handleCalculate}
                disabled={isCalculating || !postalCode || !city}
                className="w-full h-9"
              >
                {isCalculating ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Calcul en cours…
                  </>
                ) : (
                  <>
                    <Truck className="h-4 w-4 mr-2" />
                    Calculer le transport DHL
                  </>
                )}
              </Button>
            </div>

            {/* ── Résultat colisage ── */}
            {packingResult && (
              <>
                <Separator />
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium flex items-center gap-1">
                      <Package className="h-4 w-4 text-orange-500" />
                      Suggestion de colisage
                    </h4>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs text-muted-foreground"
                      onClick={handleReset}
                      disabled={isCalculating}
                    >
                      <X className="h-3 w-3 mr-1" />
                      Recalculer
                    </Button>
                  </div>

                  {/* Formulaire dimensions manuelles */}
                  {showDimensionEdit && (
                    <div className="bg-blue-50 border border-blue-200 rounded-md p-3 space-y-2">
                      <p className="text-xs font-medium text-blue-800">Dimensions du colis (cm)</p>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                          <Label htmlFor="dim-l" className="text-xs text-blue-700">Longueur</Label>
                          <Input
                            id="dim-l"
                            type="number"
                            min={1}
                            placeholder="60"
                            value={customLength}
                            onChange={(e) => setCustomLength(e.target.value)}
                            className="h-8 text-sm"
                            disabled={isCalculating}
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="dim-w" className="text-xs text-blue-700">Largeur</Label>
                          <Input
                            id="dim-w"
                            type="number"
                            min={1}
                            placeholder="40"
                            value={customWidth}
                            onChange={(e) => setCustomWidth(e.target.value)}
                            className="h-8 text-sm"
                            disabled={isCalculating}
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="dim-h" className="text-xs text-blue-700">Hauteur</Label>
                          <Input
                            id="dim-h"
                            type="number"
                            min={1}
                            placeholder="40"
                            value={customHeight}
                            onChange={(e) => setCustomHeight(e.target.value)}
                            className="h-8 text-sm"
                            disabled={isCalculating}
                          />
                        </div>
                      </div>
                      {customLength && customWidth && customHeight && (() => {
                        const l = parseFloat(customLength), w = parseFloat(customWidth), h = parseFloat(customHeight);
                        if (!l || !w || !h) return null;
                        const volDm3 = (l * w * h) / 1000;
                        const volWeight = (l * w * h) / 5000;
                        return (
                          <p className="text-xs text-blue-600 flex gap-3">
                            <span>Volume : <strong>{volDm3.toFixed(1)} dm³</strong></span>
                            <span>· Poids vol. DHL : <strong>{volWeight.toFixed(2)} kg</strong></span>
                          </p>
                        );
                      })()}
                      <div className="flex gap-2 pt-1">
                        <Button
                          size="sm"
                          className="h-8 text-xs flex-1"
                          onClick={handleCustomCalculate}
                          disabled={isCalculating || !customLength || !customWidth || !customHeight}
                        >
                          {isCalculating ? (
                            <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Calcul…</>
                          ) : (
                            <><Truck className="h-3 w-3 mr-1" />Recalculer DHL</>
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 text-xs"
                          onClick={() => setShowDimensionEdit(false)}
                          disabled={isCalculating}
                        >
                          Annuler
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Colis */}
                  <div className="grid grid-cols-2 gap-2">
                    {(() => {
                      // Grouper par type
                      const counts: Record<string, { label: string; count: number; dims: string; weight: number }> = {};
                      packingResult.packages.forEach((pkg) => {
                        const k = pkg.box_type;
                        if (!counts[k]) {
                          counts[k] = {
                            label: pkg.label,
                            count: 0,
                            dims: `${pkg.length_cm}×${pkg.width_cm}×${pkg.height_cm} cm`,
                            weight: 0,
                          };
                        }
                        counts[k].count += 1;
                        counts[k].weight += pkg.weight_kg;
                      });
                      return Object.entries(counts).map(([type, info]) => (
                        <div
                          key={type}
                          className="flex items-center gap-2 bg-orange-50 border border-orange-100 rounded-md p-2 text-sm"
                        >
                          <span className="text-lg">{boxTypeIcon(type)}</span>
                          <div>
                            <div className="font-medium">{info.count} × {info.label}</div>
                            <div className="text-xs text-muted-foreground">
                              {info.dims} — {info.weight.toFixed(1)} kg
                            </div>
                          </div>
                        </div>
                      ));
                    })()}
                  </div>

                  {/* Récapitulatif */}
                  <div className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1 space-y-0.5">
                    <div>Poids total : <strong>{packingResult.total_weight_kg.toFixed(2)} kg</strong></div>
                    <div>Volume total : <strong>{(packingResult.total_volume_m3 * 1000).toFixed(1)} dm³</strong></div>
                    {packingResult.warnings.length > 0 && (
                      <div className="text-amber-600 flex items-center gap-1 mt-1">
                        <AlertTriangle className="h-3 w-3" />
                        {packingResult.warnings[0]}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* ── Tarifs DHL ── */}
            {shippingResult && (
              <>
                <Separator />
                <div className="space-y-2">
                  <h4 className="text-sm font-medium flex items-center gap-1">
                    <Truck className="h-4 w-4 text-blue-600" />
                    Tarifs DHL Express disponibles
                  </h4>

                  {shippingResult.success && shippingResult.rates.length > 0 ? (
                    <>
                      {/* Contrôle marge */}
                      <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                        <Percent className="h-4 w-4 text-amber-600 shrink-0" />
                        <Label className="text-sm font-medium text-amber-800 whitespace-nowrap">
                          Marge transport
                        </Label>
                        <div className="flex items-center gap-1.5 ml-auto">
                          <Input
                            type="number"
                            min={0}
                            max={200}
                            step={1}
                            value={transportMargin}
                            onChange={(e) => setTransportMargin(Math.max(0, Number(e.target.value)))}
                            className="h-7 w-20 text-sm text-center font-medium border-amber-300 focus:border-amber-500"
                          />
                          <span className="text-sm font-medium text-amber-800">%</span>
                        </div>
                      </div>

                      {/* Liste des tarifs */}
                      <div className="space-y-1.5">
                        {shippingResult.rates.map((rate) => {
                          const isSelected = selectedRate?.service_code === rate.service_code;
                          const clientPrice = rate.price * (1 + transportMargin / 100);
                          return (
                            <button
                              key={rate.service_code}
                              onClick={() => setSelectedRate(rate)}
                              className={`w-full text-left flex items-center justify-between p-3 rounded-md border text-sm transition-colors ${
                                isSelected
                                  ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-400'
                                  : 'border-border hover:border-blue-200 hover:bg-blue-50/40'
                              }`}
                            >
                              <div className="flex items-center gap-3">
                                {isSelected ? (
                                  <CheckCircle className="h-4 w-4 text-blue-600 shrink-0" />
                                ) : (
                                  <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/40 shrink-0" />
                                )}
                                <div>
                                  <div className="font-medium">{rate.service_name}</div>
                                  <div className="text-xs text-muted-foreground">
                                    Délai : {rate.delivery_days} jour{rate.delivery_days > 1 ? 's' : ''}
                                    {rate.delivery_date && (
                                      <span> — Livraison estimée : {new Date(rate.delivery_date).toLocaleDateString('fr-FR')}</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="text-right shrink-0">
                                <div className={`font-semibold ${isSelected ? 'text-blue-700' : ''}`}>
                                  {formatPrice(clientPrice, rate.currency)}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  DHL : {formatPrice(rate.price, rate.currency)}
                                </div>
                                {rate.service_code === shippingResult.best_rate?.service_code && (
                                  <Badge variant="secondary" className="text-[10px] h-4">
                                    Meilleur prix
                                  </Badge>
                                )}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 border border-amber-100 rounded-md p-3">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      <div>
                        <div>Aucun tarif DHL disponible pour cette destination.</div>
                        {shippingResult.errors && shippingResult.errors.length > 0 && (
                          <div className="text-xs text-muted-foreground mt-1">
                            {shippingResult.errors[0]}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* ── Footer ── */}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDialogOpen(false)}
            >
              Annuler
            </Button>
            {selectedRate && (
              <Button
                size="sm"
                onClick={handleValidateRate}
                className="bg-blue-600 hover:bg-blue-700 text-white gap-1"
              >
                <CheckCircle className="h-4 w-4" />
                Valider {formatPrice(selectedRate.price * (1 + transportMargin / 100), selectedRate.currency)}
                <span className="text-blue-200 text-xs">(marge {transportMargin}%)</span>
                <ChevronRight className="h-3 w-3" />
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
