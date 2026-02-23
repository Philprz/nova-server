/**
 * AttachmentsTab.tsx
 * Onglet "Pièces jointes" dans la synthèse de devis.
 *
 * Les PJ sont servies depuis le stockage local NOVA (data/attachments/).
 * Avantage vs stream direct Graph : pas de ré-authentification, plus fiable.
 *
 * Si les PJ ne sont pas encore stockées localement, propose de les télécharger.
 */

import { useState, useEffect } from 'react';
import {
  File, FileText, Image, Download, Eye, Loader2,
  AlertCircle, RefreshCw, Paperclip
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  fetchStoredAttachments,
  triggerAttachmentStorage,
  getStoredAttachmentUrl,
  StoredAttachment,
} from '@/lib/graphApi';

interface AttachmentsTabProps {
  emailId: string;
  /** Indique si l'email a des PJ (pour afficher le bon état vide) */
  hasAttachments?: boolean;
}

function getFileIcon(contentType: string) {
  if (contentType?.startsWith('image/')) return <Image className="h-4 w-4 text-blue-500" />;
  if (contentType === 'application/pdf') return <FileText className="h-4 w-4 text-red-500" />;
  return <File className="h-4 w-4 text-gray-500" />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function getTypeBadgeVariant(contentType: string): 'default' | 'secondary' | 'outline' {
  if (contentType === 'application/pdf') return 'default';
  if (contentType?.startsWith('image/')) return 'secondary';
  return 'outline';
}

function getTypeLabel(contentType: string): string {
  const map: Record<string, string> = {
    'application/pdf': 'PDF',
    'image/jpeg': 'Image',
    'image/jpg': 'Image',
    'image/png': 'PNG',
    'image/gif': 'GIF',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
    'application/vnd.ms-excel': 'Excel',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
    'text/plain': 'Texte',
    'text/csv': 'CSV',
  };
  return map[contentType] || contentType?.split('/')[1]?.toUpperCase() || 'Fichier';
}

export function AttachmentsTab({ emailId, hasAttachments = true }: AttachmentsTabProps) {
  const [attachments, setAttachments] = useState<StoredAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [storing, setStoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewingAtt, setViewingAtt] = useState<StoredAttachment | null>(null);

  const loadAttachments = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchStoredAttachments(emailId);
      setAttachments(result.attachments);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAttachments();
  }, [emailId]);

  const handleStore = async () => {
    setStoring(true);
    setError(null);
    try {
      const result = await triggerAttachmentStorage(emailId);
      setAttachments(result.attachments);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du téléchargement');
    } finally {
      setStoring(false);
    }
  };

  if (!hasAttachments) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Paperclip className="h-8 w-8 mx-auto mb-3 opacity-40" />
        <p className="text-sm">Cet email ne contient pas de pièces jointes.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        Vérification des pièces jointes...
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      {attachments.length === 0 ? (
        /* PJ pas encore stockées localement */
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-6 space-y-4">
              <Paperclip className="h-10 w-10 mx-auto text-muted-foreground opacity-50" />
              <div>
                <p className="font-medium text-sm">Pièces jointes non encore téléchargées</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Les fichiers n'ont pas encore été stockés localement.
                  Cela se fait automatiquement lors de l'analyse.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleStore}
                disabled={storing}
              >
                {storing ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Téléchargement...</>
                ) : (
                  <><Download className="h-4 w-4 mr-2" />Télécharger maintenant</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* En-tête avec compteur */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {attachments.length} pièce{attachments.length > 1 ? 's jointes' : ' jointe'}
            </p>
            <Button variant="ghost" size="sm" onClick={loadAttachments}>
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
              Actualiser
            </Button>
          </div>

          {/* Liste des PJ */}
          <div className="space-y-2">
            {attachments.map((att) => {
              const serveUrl = getStoredAttachmentUrl(emailId, att.attachment_id);
              const downloadUrl = getStoredAttachmentUrl(emailId, att.attachment_id, true);

              return (
                <Card key={att.attachment_id} className="overflow-hidden">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between gap-3">
                      {/* Icône + nom + taille */}
                      <div className="flex items-center gap-3 min-w-0">
                        {getFileIcon(att.content_type)}
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate" title={att.filename}>
                            {att.filename}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatFileSize(att.size)}
                          </p>
                        </div>
                        <Badge
                          variant={getTypeBadgeVariant(att.content_type)}
                          className="shrink-0 text-xs"
                        >
                          {getTypeLabel(att.content_type)}
                        </Badge>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {att.is_previewable && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setViewingAtt(att)}
                          >
                            <Eye className="h-3.5 w-3.5 mr-1.5" />
                            Visualiser
                          </Button>
                        )}
                        <a href={downloadUrl} download={att.filename}>
                          <Button variant="ghost" size="sm">
                            <Download className="h-3.5 w-3.5 mr-1.5" />
                            Télécharger
                          </Button>
                        </a>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {/* Dialog visualisation */}
      <Dialog
        open={!!viewingAtt}
        onOpenChange={(open) => { if (!open) setViewingAtt(null); }}
      >
        {viewingAtt && (
          <DialogContent className="max-w-4xl w-full h-[85vh] flex flex-col">
            <DialogHeader>
              <div className="flex items-center justify-between pr-8">
                <DialogTitle className="truncate text-sm font-semibold">
                  {viewingAtt.filename}
                </DialogTitle>
                <a
                  href={getStoredAttachmentUrl(emailId, viewingAtt.attachment_id, true)}
                  download={viewingAtt.filename}
                  className="shrink-0"
                >
                  <Button variant="ghost" size="sm">
                    <Download className="h-4 w-4 mr-1.5" />
                    Télécharger
                  </Button>
                </a>
              </div>
            </DialogHeader>
            <div className="flex-1 overflow-hidden rounded-md border">
              {viewingAtt.content_type?.startsWith('image/') ? (
                <img
                  src={getStoredAttachmentUrl(emailId, viewingAtt.attachment_id)}
                  alt={viewingAtt.filename}
                  className="w-full h-full object-contain"
                />
              ) : (
                <iframe
                  src={getStoredAttachmentUrl(emailId, viewingAtt.attachment_id)}
                  className="w-full h-full border-0"
                  title={viewingAtt.filename}
                />
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
