/**
 * PriceEditor - Composant d'édition de prix avec transparence complète
 *
 * Fonctionnalités :
 * - Affichage des 3 prix historiques (date, client, prix, document)
 * - Affichage du prix fournisseur
 * - Visualisation variance 35-45% (barre de progression)
 * - Champ éditable avec calcul marge temps réel
 * - Modal de confirmation avant sauvegarde
 */

import { useState, useEffect } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Calendar,
  FileText,
  User,
  Save,
  AlertCircle
} from 'lucide-react';
import { format } from 'date-fns';
import { fr } from 'date-fns/locale';
import { toast } from 'sonner';

interface HistoricalSale {
  doc_entry: number;
  doc_num: number;
  doc_date: string;
  card_code: string;
  item_code: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  discount_percent?: number;
}

interface PriceEditorProps {
  // Prix actuel et données de base
  currentPrice: number;
  supplierPrice: number;
  quantity: number;
  currency?: string;

  // Prix SAP moyen (AvgStdPrice) pour comparaison
  sapAvgPrice?: number;

  // Historique des 3 dernières ventes
  historicalSales?: HistoricalSale[];

  // Variance pricing (35-45%)
  minMargin?: number;
  maxMargin?: number;
  targetMargin?: number;

  // Métadonnées
  decisionId?: string;
  itemCode: string;
  itemName?: string;

  // Callbacks
  onPriceUpdate?: (newPrice: number, reason?: string) => void;
  isReadOnly?: boolean;
}

export function PriceEditor({
  currentPrice,
  supplierPrice,
  quantity = 1,
  currency = 'EUR',
  sapAvgPrice,
  historicalSales = [],
  minMargin = 35,
  maxMargin = 45,
  targetMargin = 40,
  decisionId,
  itemCode,
  itemName,
  onPriceUpdate,
  isReadOnly = false
}: PriceEditorProps) {
  const [editedPrice, setEditedPrice] = useState<number>(currentPrice);
  const [marginSlider, setMarginSlider] = useState<number>(targetMargin);
  const [modificationReason, setModificationReason] = useState<string>('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Calculer les prix min/max basés sur la variance
  const priceMin = supplierPrice * (1 + minMargin / 100);
  const priceMax = supplierPrice * (1 + maxMargin / 100);

  // Calculer la marge actuelle (sur le prix édité manuellement)
  const currentMargin = supplierPrice > 0
    ? ((editedPrice - supplierPrice) / supplierPrice) * 100
    : 0;

  // Calculer la position sur la barre de progression (0-100)
  const progressValue = supplierPrice > 0
    ? Math.min(100, Math.max(0, ((editedPrice - priceMin) / (priceMax - priceMin)) * 100))
    : 0;

  // Déterminer la couleur selon la position dans la variance
  const getProgressColor = () => {
    if (currentMargin < minMargin) return 'bg-red-500';
    if (currentMargin > maxMargin) return 'bg-orange-500';
    return 'bg-green-500';
  };

  // Quand le slider marge change → recalculer le prix
  const handleMarginSliderChange = (value: number) => {
    setMarginSlider(value);
    if (supplierPrice > 0) {
      const newPrice = parseFloat((supplierPrice * (1 + value / 100)).toFixed(2));
      setEditedPrice(newPrice);
    }
  };

  // Vérifier si le prix a changé
  const hasChanged = Math.abs(editedPrice - currentPrice) > 0.01;

  // Mettre à jour le prix édité quand le prix courant change
  useEffect(() => {
    setEditedPrice(currentPrice);
    // Synchroniser slider avec la marge actuelle
    if (supplierPrice > 0 && currentPrice > 0) {
      const currentMarg = ((currentPrice - supplierPrice) / supplierPrice) * 100;
      setMarginSlider(Math.round(currentMarg));
    }
  }, [currentPrice, supplierPrice]);

  const handleSaveClick = () => {
    if (!hasChanged) {
      toast.info('Aucune modification à enregistrer');
      return;
    }

    if (currentMargin < minMargin - 5 || currentMargin > maxMargin + 5) {
      // Marge hors variance importante → demander confirmation
      setShowConfirmDialog(true);
    } else {
      // Marge acceptable → sauvegarder directement
      handleConfirmSave();
    }
  };

  const handleConfirmSave = async () => {
    setShowConfirmDialog(false);
    setIsSaving(true);

    try {
      if (onPriceUpdate) {
        await onPriceUpdate(editedPrice, modificationReason || undefined);
        toast.success(`Prix modifié avec succès : ${editedPrice.toFixed(2)} ${currency}`);
        setModificationReason('');
      }
    } catch (error) {
      console.error('Erreur sauvegarde prix:', error);
      toast.error('Erreur lors de la sauvegarde du prix');
    } finally {
      setIsSaving(false);
    }
  };

  const handlePriceChange = (value: string) => {
    const numValue = parseFloat(value);
    if (!isNaN(numValue) && numValue >= 0) {
      setEditedPrice(numValue);
    }
  };

  return (
    <div className="space-y-6 border rounded-lg p-4 bg-card">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Pricing Editor</h3>
          <p className="text-sm text-muted-foreground">
            {itemCode} {itemName && `- ${itemName}`}
          </p>
        </div>
        {!isReadOnly && hasChanged && (
          <Badge variant="warning" className="animate-pulse">
            <AlertCircle className="w-3 h-3 mr-1" />
            Modifications non sauvegardées
          </Badge>
        )}
      </div>

      {/* Bloc synthèse des sources de prix */}
      <div className="rounded-lg border overflow-hidden">
        <div className="bg-muted/40 px-4 py-2 border-b">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sources de prix</p>
        </div>

        <div className="divide-y">
          {/* Prix fournisseur */}
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">Prix fournisseur (tarif indexé)</span>
            </div>
            <span className="text-base font-bold">{supplierPrice > 0 ? `${supplierPrice.toFixed(2)} ${currency}` : 'Non disponible'}</span>
          </div>

          {/* Séparateur calculs */}
          {supplierPrice > 0 && (
            <>
              <div className="flex items-center justify-between px-4 py-2 bg-red-50/50 dark:bg-red-950/20">
                <div className="flex items-center gap-2">
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-sm text-muted-foreground">Marge min {minMargin}%</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-red-700 dark:text-red-400">
                    {(supplierPrice * (1 + minMargin / 100)).toFixed(2)} {currency}
                  </span>
                  {!isReadOnly && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs px-2"
                      onClick={() => setEditedPrice(parseFloat((supplierPrice * (1 + minMargin / 100)).toFixed(2)))}
                    >
                      Utiliser
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between px-4 py-2 bg-green-50/60 dark:bg-green-950/20 border-l-4 border-green-500">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-green-600" />
                  <span className="text-sm font-semibold text-green-800 dark:text-green-300">
                    Marge cible {targetMargin}% ← recommandé
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-green-700 dark:text-green-400 text-base">
                    {(supplierPrice * (1 + targetMargin / 100)).toFixed(2)} {currency}
                  </span>
                  {!isReadOnly && (
                    <Button
                      size="sm"
                      className="h-6 text-xs px-2 bg-green-600 hover:bg-green-700"
                      onClick={() => setEditedPrice(parseFloat((supplierPrice * (1 + targetMargin / 100)).toFixed(2)))}
                    >
                      Utiliser
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between px-4 py-2 bg-orange-50/50 dark:bg-orange-950/20">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-orange-500" />
                  <span className="text-sm text-muted-foreground">Marge max {maxMargin}%</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-orange-700 dark:text-orange-400">
                    {(supplierPrice * (1 + maxMargin / 100)).toFixed(2)} {currency}
                  </span>
                  {!isReadOnly && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs px-2"
                      onClick={() => setEditedPrice(parseFloat((supplierPrice * (1 + maxMargin / 100)).toFixed(2)))}
                    >
                      Utiliser
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Prix SAP moyen */}
          {sapAvgPrice && sapAvgPrice > 0 && (
            <div className="flex items-center justify-between px-4 py-3 bg-blue-50/30 dark:bg-blue-950/20">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-500" />
                <span className="text-sm text-muted-foreground">Prix moyen SAP (AvgStdPrice)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-blue-700 dark:text-blue-400">
                  {sapAvgPrice.toFixed(2)} {currency}
                </span>
                {!isReadOnly && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-xs px-2"
                    onClick={() => setEditedPrice(sapAvgPrice)}
                  >
                    Utiliser
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Prix éditable */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">Prix de vente unitaire</label>
          <Badge variant={currentMargin >= minMargin && currentMargin <= maxMargin ? 'default' : 'destructive'}>
            Marge: {currentMargin.toFixed(1)}%
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Input
            type="number"
            step="0.01"
            min="0"
            value={editedPrice.toFixed(2)}
            onChange={(e) => handlePriceChange(e.target.value)}
            disabled={isReadOnly || isSaving}
            className="text-2xl font-bold h-14"
          />
          <span className="text-2xl font-semibold text-muted-foreground">{currency}</span>
        </div>

        {/* Slider de marge (si prix fournisseur disponible) */}
        {supplierPrice > 0 && (
          <div className="space-y-2 p-3 bg-muted/30 rounded-md border">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Ajuster la marge</label>
              <Badge variant={currentMargin >= minMargin && currentMargin <= maxMargin ? 'default' : 'destructive'}>
                {marginSlider.toFixed(1)}%
              </Badge>
            </div>

            <input
              type="range"
              min={0}
              max={60}
              step={0.5}
              value={marginSlider}
              onChange={(e) => handleMarginSliderChange(parseFloat(e.target.value))}
              disabled={isReadOnly || isSaving}
              className="w-full accent-green-600"
            />

            <div className="flex justify-between text-xs text-muted-foreground">
              <span className="text-red-500">Min {minMargin}%: {priceMin.toFixed(2)} €</span>
              <span className="text-green-600 font-semibold">Cible {targetMargin}%: {(supplierPrice * (1 + targetMargin / 100)).toFixed(2)} €</span>
              <span className="text-orange-500">Max {maxMargin}%: {priceMax.toFixed(2)} €</span>
            </div>

            {/* Barre de position */}
            <div className="relative h-2 bg-muted rounded-full overflow-hidden">
              <div className="absolute inset-0 flex">
                <div className="bg-red-200 dark:bg-red-900" style={{ width: `${(minMargin / 60) * 100}%` }} />
                <div className="bg-green-200 dark:bg-green-900" style={{ width: `${((maxMargin - minMargin) / 60) * 100}%` }} />
                <div className="bg-orange-200 dark:bg-orange-900 flex-1" />
              </div>
              <div
                className={`absolute top-0 h-2 w-1 rounded-full transition-all ${getProgressColor()}`}
                style={{ left: `${Math.min(98, (marginSlider / 60) * 100)}%` }}
              />
            </div>

            <div className="flex items-center gap-2 text-xs">
              {currentMargin < minMargin ? (
                <span className="text-red-600 flex items-center gap-1">
                  <TrendingDown className="w-3 h-3" />
                  Marge insuffisante — risque sur rentabilité
                </span>
              ) : currentMargin > maxMargin ? (
                <span className="text-orange-600 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  Marge élevée — risque compétitivité
                </span>
              ) : (
                <span className="text-green-600 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  Marge dans la fourchette cible
                </span>
              )}
            </div>
          </div>
        )}

        {/* Total ligne */}
        <div className="flex justify-between items-center p-3 bg-primary/5 rounded-md border border-primary/20">
          <span className="text-sm font-medium">Total ligne (× {quantity})</span>
          <span className="text-xl font-bold text-primary">
            {(editedPrice * quantity).toFixed(2)} {currency}
          </span>
        </div>
      </div>

      {/* Historique des 3 dernières ventes */}
      {historicalSales.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Historique des {historicalSales.length} dernières vente(s) à ce client
          </h4>

          <div className="border rounded-md overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Document</TableHead>
                  <TableHead className="text-right">Prix unitaire</TableHead>
                  <TableHead className="text-right">Qté</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {historicalSales.map((sale, index) => (
                  <TableRow key={sale.doc_entry}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Calendar className="w-3 h-3 text-muted-foreground" />
                        <span className="text-sm">
                          {format(new Date(sale.doc_date), 'dd MMM yyyy', { locale: fr })}
                        </span>
                        {index === 0 && (
                          <Badge variant="outline" className="text-xs">Plus récent</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm font-mono">#{sale.doc_num}</span>
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {sale.unit_price.toFixed(2)} {currency}
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      {sale.quantity}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {sale.line_total.toFixed(2)} {currency}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Boutons d'action */}
      {!isReadOnly && (
        <div className="flex gap-3 pt-4 border-t">
          <Button
            onClick={handleSaveClick}
            disabled={!hasChanged || isSaving}
            className="flex-1"
          >
            <Save className="w-4 h-4 mr-2" />
            {isSaving ? 'Enregistrement...' : 'Enregistrer le prix'}
          </Button>

          {hasChanged && (
            <Button
              variant="outline"
              onClick={() => setEditedPrice(currentPrice)}
              disabled={isSaving}
            >
              Annuler
            </Button>
          )}
        </div>
      )}

      {/* Modal de confirmation (si marge hors variance) */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirmer la modification de prix</DialogTitle>
            <DialogDescription>
              La marge appliquée ({currentMargin.toFixed(1)}%) est{' '}
              {currentMargin < minMargin ? 'inférieure' : 'supérieure'} à la fourchette
              recommandée ({minMargin}-{maxMargin}%).
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4 p-4 bg-muted/50 rounded-md">
              <div>
                <p className="text-sm text-muted-foreground">Prix actuel</p>
                <p className="text-lg font-bold">{currentPrice.toFixed(2)} {currency}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Nouveau prix</p>
                <p className="text-lg font-bold text-primary">{editedPrice.toFixed(2)} {currency}</p>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block">
                Raison de la modification (optionnel)
              </label>
              <Input
                placeholder="Ex: Ajustement commercial sur demande client"
                value={modificationReason}
                onChange={(e) => setModificationReason(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfirmDialog(false)}
            >
              Annuler
            </Button>
            <Button onClick={handleConfirmSave} disabled={isSaving}>
              {isSaving ? 'Enregistrement...' : 'Confirmer'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
