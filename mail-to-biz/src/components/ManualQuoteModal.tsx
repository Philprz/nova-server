import { useState, useEffect, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Loader2, Plus, Trash2, Search } from 'lucide-react';
import { createManualQuoteRequest, ManualQuoteResult } from '@/lib/graphApi';

interface SapClient {
  CardCode: string;
  CardName: string;
  EmailAddress?: string;
  City?: string;
}

interface SapItem {
  ItemCode: string;
  ItemName: string;
}

interface ProductLine {
  id: number;
  item_code: string;
  item_name: string;
  quantity: number;
  searchQuery: string;
  suggestions: SapItem[];
  loadingSuggestions: boolean;
  showSuggestions: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (result: ManualQuoteResult) => void;
}

export function ManualQuoteModal({ open, onClose, onCreated }: Props) {
  const [clientQuery, setClientQuery] = useState('');
  const [clientSuggestions, setClientSuggestions] = useState<SapClient[]>([]);
  const [loadingClients, setLoadingClients] = useState(false);
  const [showClientSuggestions, setShowClientSuggestions] = useState(false);
  const [selectedClient, setSelectedClient] = useState<SapClient | null>(null);

  const [lines, setLines] = useState<ProductLine[]>([
    { id: 1, item_code: '', item_name: '', quantity: 1, searchQuery: '', suggestions: [], loadingSuggestions: false, showSuggestions: false },
  ]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clientDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const itemDebounces = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const nextId = useRef(2);

  // Reset on open
  useEffect(() => {
    if (open) {
      setClientQuery('');
      setClientSuggestions([]);
      setShowClientSuggestions(false);
      setSelectedClient(null);
      setLines([{ id: 1, item_code: '', item_name: '', quantity: 1, searchQuery: '', suggestions: [], loadingSuggestions: false, showSuggestions: false }]);
      setError(null);
    }
  }, [open]);

  // Search clients with debounce
  const handleClientInput = (value: string) => {
    setClientQuery(value);
    setSelectedClient(null);
    if (clientDebounce.current) clearTimeout(clientDebounce.current);
    if (value.length < 2) { setClientSuggestions([]); setShowClientSuggestions(false); return; }
    clientDebounce.current = setTimeout(async () => {
      setLoadingClients(true);
      try {
        const res = await fetch(`/api/sap-rondot/clients?search=${encodeURIComponent(value)}&limit=10`);
        const data = await res.json();
        setClientSuggestions(data.clients || []);
        setShowClientSuggestions(true);
      } catch { setClientSuggestions([]); }
      finally { setLoadingClients(false); }
    }, 300);
  };

  const selectClient = (client: SapClient) => {
    setSelectedClient(client);
    setClientQuery(client.CardName);
    setShowClientSuggestions(false);
  };

  // Search items for a line with debounce
  const handleItemInput = (lineId: number, value: string) => {
    setLines(prev => prev.map(l => l.id === lineId ? { ...l, searchQuery: value, item_code: '', item_name: '' } : l));
    if (itemDebounces.current[lineId]) clearTimeout(itemDebounces.current[lineId]);
    if (value.length < 2) {
      setLines(prev => prev.map(l => l.id === lineId ? { ...l, suggestions: [], showSuggestions: false } : l));
      return;
    }
    itemDebounces.current[lineId] = setTimeout(async () => {
      setLines(prev => prev.map(l => l.id === lineId ? { ...l, loadingSuggestions: true } : l));
      try {
        const res = await fetch(`/api/sap-rondot/products?search=${encodeURIComponent(value)}&limit=10`);
        const data = await res.json();
        setLines(prev => prev.map(l => l.id === lineId
          ? { ...l, suggestions: data.products || [], showSuggestions: true, loadingSuggestions: false }
          : l));
      } catch {
        setLines(prev => prev.map(l => l.id === lineId ? { ...l, loadingSuggestions: false } : l));
      }
    }, 300);
  };

  const selectItem = (lineId: number, item: SapItem) => {
    setLines(prev => prev.map(l => l.id === lineId
      ? { ...l, item_code: item.ItemCode, item_name: item.ItemName, searchQuery: `${item.ItemCode} — ${item.ItemName}`, suggestions: [], showSuggestions: false }
      : l));
  };

  const setQuantity = (lineId: number, qty: number) => {
    setLines(prev => prev.map(l => l.id === lineId ? { ...l, quantity: Math.max(1, qty) } : l));
  };

  const addLine = () => {
    setLines(prev => [...prev, {
      id: nextId.current++,
      item_code: '', item_name: '', quantity: 1, searchQuery: '',
      suggestions: [], loadingSuggestions: false, showSuggestions: false,
    }]);
  };

  const removeLine = (lineId: number) => {
    setLines(prev => prev.filter(l => l.id !== lineId));
  };

  const canSubmit = selectedClient && lines.some(l => l.item_code);

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createManualQuoteRequest({
        source: 'manual',
        client: selectedClient!.CardCode,
        client_name: selectedClient!.CardName,
        items: lines
          .filter(l => l.item_code)
          .map(l => ({ item_code: l.item_code, item_name: l.item_name, quantity: l.quantity })),
      });
      onCreated(result);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur inconnue');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Nouvelle demande de devis</DialogTitle>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Client */}
          <div className="space-y-1.5">
            <Label>Client <span className="text-destructive">*</span></Label>
            <div className="relative">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="Rechercher un client SAP…"
                  value={clientQuery}
                  onChange={e => handleClientInput(e.target.value)}
                  onFocus={() => clientSuggestions.length > 0 && setShowClientSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowClientSuggestions(false), 150)}
                />
                {loadingClients && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />}
              </div>
              {showClientSuggestions && clientSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto">
                  {clientSuggestions.map(c => (
                    <button
                      key={c.CardCode}
                      type="button"
                      className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center justify-between"
                      onMouseDown={() => selectClient(c)}
                    >
                      <span className="font-medium">{c.CardName}</span>
                      <span className="text-xs text-muted-foreground ml-2">{c.CardCode}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {selectedClient && (
              <Badge variant="secondary" className="text-xs">
                {selectedClient.CardCode} — {selectedClient.CardName}
                {selectedClient.City && ` (${selectedClient.City})`}
              </Badge>
            )}
          </div>

          {/* Lignes produits */}
          <div className="space-y-2">
            <Label>Produits <span className="text-destructive">*</span></Label>
            {lines.map((line, idx) => (
              <div key={line.id} className="flex gap-2 items-start">
                <div className="flex-1 relative">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      className="pl-8 text-sm"
                      placeholder="Rechercher un article SAP…"
                      value={line.searchQuery}
                      onChange={e => handleItemInput(line.id, e.target.value)}
                      onFocus={() => line.suggestions.length > 0 && setLines(prev => prev.map(l => l.id === line.id ? { ...l, showSuggestions: true } : l))}
                      onBlur={() => setTimeout(() => setLines(prev => prev.map(l => l.id === line.id ? { ...l, showSuggestions: false } : l)), 150)}
                    />
                    {line.loadingSuggestions && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />}
                  </div>
                  {line.showSuggestions && line.suggestions.length > 0 && (
                    <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto">
                      {line.suggestions.map(item => (
                        <button
                          key={item.ItemCode}
                          type="button"
                          className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center justify-between"
                          onMouseDown={() => selectItem(line.id, item)}
                        >
                          <span className="font-medium truncate">{item.ItemName}</span>
                          <span className="text-xs text-muted-foreground ml-2 flex-shrink-0">{item.ItemCode}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <Input
                  type="number"
                  min={1}
                  className="w-20 text-sm"
                  value={line.quantity}
                  onChange={e => setQuantity(line.id, parseInt(e.target.value) || 1)}
                  placeholder="Qté"
                />
                {lines.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="flex-shrink-0 text-destructive hover:text-destructive"
                    onClick={() => removeLine(line.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={addLine} className="mt-1">
              <Plus className="h-4 w-4 mr-1" />
              Ajouter une ligne
            </Button>
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>Annuler</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
            {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Créer la demande
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
