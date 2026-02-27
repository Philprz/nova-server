/**
 * PriceEditorDialog - Wrapper du PriceEditor dans un Dialog
 * Permet d'éditer le prix d'un article depuis la table de synthèse
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PriceEditor } from './PriceEditor';
import { Edit, AlertCircle } from 'lucide-react';
import { updateDecisionPrice } from '@/lib/graphApi';
import { toast } from 'sonner';

interface ProductLine {
  ItemCode?: string;
  ItemDescription?: string;
  Quantity?: number;
  unit_price?: number;
  line_total?: number;
  pricing_case?: string;
  pricing_justification?: string;
  requires_validation?: boolean;
  historical_sales?: any[];
  supplier_price?: number;
  price_range_min?: number;
  price_range_max?: number;
  decision_id?: string;
}

interface PriceEditorDialogProps {
  line: ProductLine;
  onPriceUpdated?: (newPrice: number) => void;
  effectiveQuantity?: number;
}

export function PriceEditorDialog({ line, onPriceUpdated, effectiveQuantity }: PriceEditorDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);

  const hasPrice = line.unit_price != null;
  const supplierPrice = line.supplier_price || 0;

  // Un produit est "vraiment nouveau" uniquement s'il n'a pas de code SAP.
  // CAS_4_NP avec ItemCode = article SAP sans historique de vente (différent de "nouveau produit").
  const hasItemCode = !!(line.ItemCode && line.ItemCode !== 'À définir');

  const getCasVariant = (casType?: string) => {
    switch (casType) {
      case 'CAS_1_HC': return 'default';
      case 'CAS_2_HCM': return 'warning';
      case 'CAS_3_HA': return 'secondary';
      case 'CAS_4_NP': return hasItemCode ? 'secondary' : 'destructive';
      default: return 'default';
    }
  };

  const formatCasLabel = (casType?: string) => {
    switch (casType) {
      case 'CAS_1_HC': return 'Historique Client';
      case 'CAS_2_HCM': return 'Prix Modifié';
      case 'CAS_3_HA': return 'Prix Moyen';
      case 'CAS_4_NP': return hasItemCode ? 'Sans historique' : 'Nouveau Produit';
      case 'SAP_FUNCTION': return 'SAP Direct';
      case 'CAS_MANUAL': return 'Manuel';
      default: return 'Prix calculé';
    }
  };

  const handlePriceUpdate = async (newPrice: number, reason?: string) => {
    // Pas de decision_id → mise à jour locale uniquement (sans persistance backend)
    if (!line.decision_id) {
      if (onPriceUpdated) onPriceUpdated(newPrice);
      setIsOpen(false);
      return;
    }

    setIsUpdating(true);

    try {
      const result = await updateDecisionPrice(
        line.decision_id,
        newPrice,
        reason,
        'user@mail-to-biz'
      );

      // Callback pour mettre à jour la ligne dans le parent
      if (onPriceUpdated) {
        onPriceUpdated(newPrice);
      }

      setIsOpen(false);
    } catch (error: any) {
      console.error('Erreur modification prix:', error);
      // En cas d'échec backend, on applique quand même le prix localement
      if (onPriceUpdated) onPriceUpdated(newPrice);
      setIsOpen(false);
    } finally {
      setIsUpdating(false);
    }
  };

  if (!hasPrice) {
    return (
      <span className="text-muted-foreground">À calculer</span>
    );
  }

  return (
    <>
      {/* Affichage compact dans la table */}
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-lg">
            {line.unit_price!.toFixed(2)} €
          </span>

          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => setIsOpen(true)}
            title="Modifier le prix"
          >
            <Edit className="w-4 h-4" />
          </Button>
        </div>

        {line.pricing_case && (
          <Badge
            variant={getCasVariant(line.pricing_case)}
            className="text-xs"
          >
            {formatCasLabel(line.pricing_case)}
          </Badge>
        )}

        {line.unit_price != null && (
          <span className="text-sm text-muted-foreground">
            Total: {(line.unit_price * (effectiveQuantity ?? line.Quantity ?? 1)).toFixed(2)} €
            {effectiveQuantity != null && effectiveQuantity !== line.Quantity && (
              <span className="text-xs text-warning ml-1">(qté modifiée)</span>
            )}
          </span>
        )}

        {line.requires_validation && (
          <Badge variant="outline" className="text-xs text-orange-600 border-orange-600">
            <AlertCircle className="w-3 h-3 mr-1" />
            Validation requise
          </Badge>
        )}
      </div>

      {/* Dialog avec PriceEditor complet */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              Modifier le prix - {line.ItemCode}
            </DialogTitle>
          </DialogHeader>

          <PriceEditor
            currentPrice={line.unit_price || 0}
            supplierPrice={supplierPrice}
            sapAvgPrice={(line as any).sap_avg_price}
            quantity={line.Quantity || 1}
            currency="EUR"
            historicalSales={line.historical_sales || []}
            minMargin={35}
            maxMargin={45}
            targetMargin={40}
            decisionId={line.decision_id}
            itemCode={line.ItemCode || ''}
            itemName={line.ItemDescription}
            onPriceUpdate={handlePriceUpdate}
            isReadOnly={isUpdating}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
