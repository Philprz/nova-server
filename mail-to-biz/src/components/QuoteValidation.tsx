import { useState } from 'react';
import { ProcessedEmail } from '@/types/email';
import { PreSapDocument, validateDocument, rejectDocument, exportToJson } from '@/lib/preSapNormalizer';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Check, X, Download, AlertTriangle, Building, Package, Truck, FileJson } from 'lucide-react';
import { toast } from 'sonner';

interface QuoteValidationProps {
  quotes: ProcessedEmail[];
  selectedQuote: ProcessedEmail | null;
  onSelectQuote: (quote: ProcessedEmail | null) => void;
  onValidate: (quote: ProcessedEmail) => void;
}

export function QuoteValidation({ quotes, selectedQuote, onSelectQuote, onValidate }: QuoteValidationProps) {
  const [editedDoc, setEditedDoc] = useState<PreSapDocument | null>(null);

  // Devis en attente : pas de preSapDocument OU status pending
  const pendingQuotes = quotes.filter(q => {
    const status = q.preSapDocument?.meta.validationStatus;
    return status !== 'validated' && status !== 'rejected';
  });
  const validatedQuotes = quotes.filter(q => q.preSapDocument?.meta.validationStatus === 'validated');

  const handleSelectQuote = (quote: ProcessedEmail) => {
    onSelectQuote(quote);
    setEditedDoc(quote.preSapDocument ? { ...quote.preSapDocument } : null);
  };

  const handleValidate = () => {
    if (!selectedQuote || !editedDoc) return;
    const validated = validateDocument(editedDoc);
    onValidate({ ...selectedQuote, preSapDocument: validated });
    toast.success('Devis validé avec succès');
  };

  const handleReject = () => {
    if (!selectedQuote || !editedDoc) return;
    const rejected = rejectDocument(editedDoc);
    onValidate({ ...selectedQuote, preSapDocument: rejected });
    toast.error('Devis refusé');
  };

  const handleExport = () => {
    if (!editedDoc) return;
    const json = exportToJson(editedDoc);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pre-sap-quote-${editedDoc.meta.emailId}.json`;
    a.click();
    toast.success('JSON exporté');
  };

  const updateClientName = (name: string) => {
    if (!editedDoc) return;
    setEditedDoc({
      ...editedDoc,
      businessPartner: { ...editedDoc.businessPartner, CardName: name }
    });
  };

  const updateArticle = (index: number, field: 'ItemDescription' | 'Quantity', value: string | number) => {
    if (!editedDoc) return;
    const lines = [...editedDoc.documentLines];
    lines[index] = { ...lines[index], [field]: value };
    setEditedDoc({ ...editedDoc, documentLines: lines });
  };

  return (
    <div className="grid grid-cols-3 gap-6 animate-fade-in">
      {/* Quote list */}
      <div className="space-y-4">
        <h2 className="section-title">En attente ({pendingQuotes.length})</h2>
        {pendingQuotes.map(quote => (
          <Card
            key={quote.email.id}
            className={`p-3 cursor-pointer transition-all ${selectedQuote?.email.id === quote.email.id ? 'ring-2 ring-primary' : 'hover:bg-muted/50'}`}
            onClick={() => handleSelectQuote(quote)}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">
                  {quote.preSapDocument?.businessPartner.CardName || quote.email.from.emailAddress.name}
                </p>
                <p className="text-xs text-muted-foreground">{quote.email.subject}</p>
              </div>
              <Badge className="status-badge-pending">
                {quote.preSapDocument ? 'En attente' : 'À traiter'}
              </Badge>
            </div>
          </Card>
        ))}

        {validatedQuotes.length > 0 && (
          <>
            <Separator />
            <h2 className="section-title text-success">Validés ({validatedQuotes.length})</h2>
            {validatedQuotes.map(quote => (
              <Card key={quote.email.id} className="p-3 opacity-60">
                <div className="flex items-center justify-between">
                  <p className="font-medium text-sm">{quote.preSapDocument?.businessPartner.CardName}</p>
                  <Badge className="status-badge-validated">Validé</Badge>
                </div>
              </Card>
            ))}
          </>
        )}
      </div>

      {/* Validation form */}
      <div className="col-span-2">
        {selectedQuote && editedDoc ? (
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <FileJson className="w-5 h-5 text-primary" />
                  Validation du devis
                </CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={handleExport}>
                    <Download className="w-4 h-4 mr-1" /> Exporter JSON
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Warnings */}
              {editedDoc.meta.sourceConflicts.length > 0 && (
                <div className="p-3 rounded-lg bg-warning/10 border border-warning/20">
                  <div className="flex items-center gap-2 text-warning">
                    <AlertTriangle className="w-4 h-4" />
                    <span className="font-medium text-sm">Conflits de source</span>
                  </div>
                  <ul className="mt-2 text-xs text-muted-foreground">
                    {editedDoc.meta.sourceConflicts.map((c, i) => <li key={i}>• {c}</li>)}
                  </ul>
                </div>
              )}

              {/* Client */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Building className="w-4 h-4 text-muted-foreground" />
                  <h3 className="font-semibold">Client</h3>
                  {editedDoc.businessPartner.ToBeCreated && (
                    <Badge variant="outline" className="text-warning border-warning">À créer dans SAP</Badge>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="form-label">Nom de la société</Label>
                    <Input 
                      value={editedDoc.businessPartner.CardName}
                      onChange={(e) => updateClientName(e.target.value)}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label className="form-label">Email</Label>
                    <Input value={editedDoc.businessPartner.ContactEmail} disabled className="mt-1 bg-muted" />
                  </div>
                </div>
              </div>

              <Separator />

              {/* Articles */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Package className="w-4 h-4 text-muted-foreground" />
                  <h3 className="font-semibold">Articles ({editedDoc.documentLines.length})</h3>
                </div>
                <div className="space-y-3">
                  {editedDoc.documentLines.map((line, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-3 items-end p-3 rounded-lg bg-muted/30">
                      <div className="col-span-7">
                        <Label className="text-xs text-muted-foreground">Désignation</Label>
                        <Input 
                          value={line.ItemDescription}
                          onChange={(e) => updateArticle(idx, 'ItemDescription', e.target.value)}
                          className="mt-1"
                        />
                      </div>
                      <div className="col-span-2">
                        <Label className="text-xs text-muted-foreground">Quantité</Label>
                        <Input 
                          type="number"
                          value={line.Quantity}
                          onChange={(e) => updateArticle(idx, 'Quantity', parseInt(e.target.value) || 0)}
                          className="mt-1"
                        />
                      </div>
                      <div className="col-span-2">
                        <Label className="text-xs text-muted-foreground">Unité</Label>
                        <Input value={line.UnitOfMeasure || 'pcs'} disabled className="mt-1 bg-muted" />
                      </div>
                      <div className="col-span-1">
                        <Badge variant="outline" className="text-xs">
                          {line.SourceType === 'pdf' ? 'PDF' : 'Email'}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Delivery */}
              {editedDoc.deliveryLeadTimeDays && (
                <>
                  <Separator />
                  <div className="flex items-center gap-4">
                    <Truck className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm">Délai souhaité: <strong>{editedDoc.deliveryLeadTimeDays} jours</strong></span>
                    {editedDoc.requestedDeliveryDate && (
                      <Badge variant="secondary">Livraison: {editedDoc.requestedDeliveryDate}</Badge>
                    )}
                  </div>
                </>
              )}

              <Separator />

              {/* Actions */}
              <div className="flex justify-end gap-3">
                <Button variant="destructive" onClick={handleReject}>
                  <X className="w-4 h-4 mr-1" /> Refuser
                </Button>
                <Button onClick={handleValidate}>
                  <Check className="w-4 h-4 mr-1" /> Valider et préparer pour SAP
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="flex items-center justify-center h-96 text-muted-foreground">
            Sélectionnez un devis à valider
          </div>
        )}
      </div>
    </div>
  );
}
