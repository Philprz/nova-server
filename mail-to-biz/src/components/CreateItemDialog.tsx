import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Loader2, Package, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface CreateItemDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (itemCode: string) => void;
  initialItemCode?: string;
  initialDescription?: string;
}

interface CreateItemData {
  item_code: string;
  item_name: string;
  item_group_code?: number;
  default_price?: number;
  purchase_item: boolean;
  sales_item: boolean;
  inventory_item: boolean;
  manufacturer?: string;
  bar_code?: string;
  remarks?: string;
}

export function CreateItemDialog({
  open,
  onClose,
  onSuccess,
  initialItemCode = '',
  initialDescription = ''
}: CreateItemDialogProps) {
  const [formData, setFormData] = useState<CreateItemData>({
    item_code: initialItemCode,
    item_name: initialDescription,
    item_group_code: 100,
    default_price: undefined,
    purchase_item: true,
    sales_item: true,
    inventory_item: true,
    manufacturer: '',
    bar_code: '',
    remarks: ''
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!formData.item_code || !formData.item_name) {
      setError('Le code et le nom de l\'article sont obligatoires');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch('/api/sap/items/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (data.success) {
        onSuccess(data.item_code);
        onClose();
      } else {
        setError(data.error || 'Erreur lors de la création de l\'article');
      }
    } catch (err) {
      console.error('Erreur création article:', err);
      setError('Erreur de connexion au serveur');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field: keyof CreateItemData, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="w-5 h-5 text-primary" />
            Créer un nouvel article dans SAP
          </DialogTitle>
          <DialogDescription>
            Remplissez les informations de l'article à créer dans SAP Business One
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Erreur */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Informations de base */}
          <div className="space-y-4">
            <h3 className="font-medium text-sm">Informations de base</h3>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="item_code">
                  Code article <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="item_code"
                  value={formData.item_code}
                  onChange={(e) => handleChange('item_code', e.target.value)}
                  placeholder="ex: ART-001"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="item_group_code">Catégorie</Label>
                <Select
                  value={formData.item_group_code?.toString()}
                  onValueChange={(value) => handleChange('item_group_code', parseInt(value))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Sélectionner une catégorie" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="100">Général</SelectItem>
                    <SelectItem value="101">Moteurs</SelectItem>
                    <SelectItem value="102">Pièces détachées</SelectItem>
                    <SelectItem value="103">Consommables</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="item_name">
                Nom de l'article <span className="text-destructive">*</span>
              </Label>
              <Input
                id="item_name"
                value={formData.item_name}
                onChange={(e) => handleChange('item_name', e.target.value)}
                placeholder="ex: Moteur 5kW triphasé"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="default_price">Prix par défaut (EUR)</Label>
              <Input
                id="default_price"
                type="number"
                step="0.01"
                min="0"
                value={formData.default_price || ''}
                onChange={(e) => handleChange('default_price', e.target.value ? parseFloat(e.target.value) : undefined)}
                placeholder="ex: 150.00"
              />
            </div>
          </div>

          {/* Informations complémentaires */}
          <div className="space-y-4">
            <h3 className="font-medium text-sm">Informations complémentaires</h3>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="manufacturer">Fabricant</Label>
                <Input
                  id="manufacturer"
                  value={formData.manufacturer}
                  onChange={(e) => handleChange('manufacturer', e.target.value)}
                  placeholder="ex: Siemens"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="bar_code">Code-barres</Label>
                <Input
                  id="bar_code"
                  value={formData.bar_code}
                  onChange={(e) => handleChange('bar_code', e.target.value)}
                  placeholder="ex: 1234567890123"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="remarks">Remarques</Label>
              <Textarea
                id="remarks"
                value={formData.remarks}
                onChange={(e) => handleChange('remarks', e.target.value)}
                placeholder="Notes ou informations supplémentaires..."
                rows={3}
              />
            </div>
          </div>

          {/* Options */}
          <div className="space-y-4">
            <h3 className="font-medium text-sm">Options</h3>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="purchase_item" className="cursor-pointer">
                  Article achetable
                </Label>
                <Switch
                  id="purchase_item"
                  checked={formData.purchase_item}
                  onCheckedChange={(checked) => handleChange('purchase_item', checked)}
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="sales_item" className="cursor-pointer">
                  Article vendable
                </Label>
                <Switch
                  id="sales_item"
                  checked={formData.sales_item}
                  onCheckedChange={(checked) => handleChange('sales_item', checked)}
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="inventory_item" className="cursor-pointer">
                  Article de stock
                </Label>
                <Switch
                  id="inventory_item"
                  checked={formData.inventory_item}
                  onCheckedChange={(checked) => handleChange('inventory_item', checked)}
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Annuler
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Création en cours...
                </>
              ) : (
                <>
                  <Package className="w-4 h-4 mr-2" />
                  Créer l'article
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
