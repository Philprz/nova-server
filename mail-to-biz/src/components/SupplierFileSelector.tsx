import { useState } from 'react';
import { FileSpreadsheet, FileText, Check, AlertCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmailAttachment, extractFromSingleFile, SingleFileExtractionResult } from '@/lib/supplierFileExtractor';

interface SupplierFileSelectorProps {
  attachments: EmailAttachment[];
  onExtractionComplete: (result: SingleFileExtractionResult) => void;
  isOpen: boolean;
  onClose: () => void;
}

export function SupplierFileSelector({
  attachments,
  onExtractionComplete,
  isOpen,
  onClose,
}: SupplierFileSelectorProps) {
  const [selectedFile, setSelectedFile] = useState<EmailAttachment | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionResult, setExtractionResult] = useState<SingleFileExtractionResult | null>(null);

  // Filter for exploitable files (PDF and Excel only)
  const exploitableFiles = attachments.filter(att => {
    const name = att.name.toLowerCase();
    const type = att.contentType.toLowerCase();
    return (
      type === 'application/pdf' ||
      name.endsWith('.pdf') ||
      type.includes('excel') ||
      type.includes('spreadsheet') ||
      name.endsWith('.xlsx') ||
      name.endsWith('.xls')
    );
  });

  const getFileIcon = (attachment: EmailAttachment) => {
    const name = attachment.name.toLowerCase();
    if (name.endsWith('.xlsx') || name.endsWith('.xls') || attachment.contentType.includes('excel')) {
      return <FileSpreadsheet className="w-5 h-5 text-success" />;
    }
    return <FileText className="w-5 h-5 text-destructive" />;
  };

  const getFileType = (attachment: EmailAttachment): 'excel' | 'pdf' => {
    const name = attachment.name.toLowerCase();
    if (name.endsWith('.xlsx') || name.endsWith('.xls') || attachment.contentType.includes('excel')) {
      return 'excel';
    }
    return 'pdf';
  };

  const handleSelectFile = (file: EmailAttachment) => {
    setSelectedFile(file);
    setExtractionResult(null);
  };

  const handleExtract = async () => {
    if (!selectedFile) return;

    setIsExtracting(true);
    
    // Simulate async extraction (in production this would be real parsing)
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    const result = extractFromSingleFile(selectedFile);
    setExtractionResult(result);
    setIsExtracting(false);
  };

  const handleConfirm = () => {
    if (extractionResult) {
      onExtractionComplete(extractionResult);
      onClose();
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setExtractionResult(null);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-warning" />
            Produit non trouvé dans SAP
          </DialogTitle>
          <DialogDescription>
            Sélectionnez le fichier fournisseur à analyser pour extraire les informations produit.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          {/* File Selection */}
          {!extractionResult && (
            <>
              <div className="space-y-2">
                <p className="text-sm font-medium text-foreground">
                  Fichiers fournisseurs disponibles ({exploitableFiles.length})
                </p>
                
                {exploitableFiles.length === 0 ? (
                  <Card className="border-dashed">
                    <CardContent className="py-8 text-center">
                      <AlertCircle className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                      <p className="text-muted-foreground">
                        Aucun fichier exploitable trouvé (PDF ou Excel requis)
                      </p>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-2">
                    {exploitableFiles.map((file) => (
                      <Card
                        key={file.id}
                        className={`cursor-pointer transition-all hover:border-primary/50 ${
                          selectedFile?.id === file.id
                            ? 'border-primary bg-primary/5'
                            : ''
                        }`}
                        onClick={() => handleSelectFile(file)}
                      >
                        <CardContent className="py-3 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            {getFileIcon(file)}
                            <div>
                              <p className="font-medium text-sm">{file.name}</p>
                              <p className="text-xs text-muted-foreground">
                                {(file.size / 1024).toFixed(1)} Ko
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs">
                              {getFileType(file).toUpperCase()}
                            </Badge>
                            {selectedFile?.id === file.id && (
                              <Check className="w-4 h-4 text-primary" />
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>

              {selectedFile && (
                <Button
                  onClick={handleExtract}
                  disabled={isExtracting}
                  className="w-full"
                >
                  {isExtracting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Extraction en cours...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 mr-2" />
                      Analyser ce fichier
                    </>
                  )}
                </Button>
              )}
            </>
          )}

          {/* Extraction Results */}
          {extractionResult && (
            <div className="space-y-4">
              <Card className="border-primary/30 bg-primary/5">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Check className="w-4 h-4 text-primary" />
                    Extraction terminée
                  </CardTitle>
                  <CardDescription>
                    Fichier analysé : {extractionResult.supplier_file.filename}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {extractionResult.extracted_product_data ? (
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-muted-foreground">Référence fournisseur</p>
                        <p className="font-medium">
                          {extractionResult.extracted_product_data.supplier_reference || (
                            <span className="text-warning">Non trouvé</span>
                          )}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Désignation</p>
                        <p className="font-medium">
                          {extractionResult.extracted_product_data.designation || (
                            <span className="text-warning">Non trouvé</span>
                          )}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Prix unitaire</p>
                        <p className="font-medium">
                          {extractionResult.extracted_product_data.unit_price != null ? (
                            `${extractionResult.extracted_product_data.unit_price.toFixed(2)} ${
                              extractionResult.extracted_product_data.currency || ''
                            }`
                          ) : (
                            <span className="text-warning">Non trouvé</span>
                          )}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Délai de livraison</p>
                        <p className="font-medium">
                          {extractionResult.extracted_product_data.delivery_time || (
                            <span className="text-warning">Non trouvé</span>
                          )}
                        </p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-muted-foreground">Fournisseur</p>
                        <p className="font-medium">
                          {extractionResult.extracted_product_data.supplier_name || (
                            <span className="text-warning">Non trouvé</span>
                          )}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4">
                      <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-2" />
                      <p className="text-destructive font-medium">
                        Impossible d'extraire les données
                      </p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {extractionResult.extraction_notes}
                      </p>
                    </div>
                  )}

                  {extractionResult.missing_fields.length > 0 && (
                    <div className="pt-2 border-t">
                      <p className="text-xs text-muted-foreground mb-1">
                        Champs manquants :
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {extractionResult.missing_fields.map((field) => (
                          <Badge key={field} variant="outline" className="text-xs text-warning">
                            {field}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <div className="flex gap-2">
                <Button variant="outline" onClick={handleReset} className="flex-1">
                  Sélectionner un autre fichier
                </Button>
                <Button onClick={handleConfirm} className="flex-1">
                  <Check className="w-4 h-4 mr-2" />
                  Confirmer l'extraction
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
