import { Mail, Paperclip, FileText, Clock, Loader2, CheckCircle2, RefreshCw, Phone, Archive, ArchiveRestore, Star } from 'lucide-react';
import { ProcessedEmail } from '@/types/email';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { format } from 'date-fns';
import { fr } from 'date-fns/locale';

interface EmailListProps {
  emails: ProcessedEmail[];
  onSelectQuote: (quote: ProcessedEmail) => void;
  onAnalyze?: (item: ProcessedEmail) => Promise<void>;
  analyzingEmailId?: string | null;
  processedIds?: Set<string>;
  processedMeta?: Record<string, { sapDocNum?: number; createdAt: string }>;
  onReanalyze?: (emailId: string) => Promise<void>;
  archivedIds?: Set<string>;
  starredIds?: Set<string>;
  onArchive?: (emailId: string, archived: boolean) => void;
  onStar?: (emailId: string, starred: boolean) => void;
}

export function EmailList({
  emails, onSelectQuote, onAnalyze, analyzingEmailId, processedIds, processedMeta, onReanalyze,
  archivedIds, starredIds, onArchive, onStar,
}: EmailListProps) {
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="space-y-2">
        {emails.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Mail className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">Aucun email ne correspond aux filtres sélectionnés.</p>
          </div>
        )}

        {emails.map((item) => {
          const isProcessed = processedIds?.has(item.email.id) ?? false;
          const isArchived  = archivedIds?.has(item.email.id) ?? false;
          const isStarred   = starredIds?.has(item.email.id) ?? false;
          const meta = processedMeta?.[item.email.id];
          const isManual = item.email.id.startsWith('manual_');

          return (
            <Card
              key={item.email.id}
              className={`card-elevated cursor-pointer transition-opacity ${
                isArchived ? 'opacity-60' : ''
              } ${
                isProcessed
                  ? 'border-l-4 border-l-success'
                  : item.isQuote
                    ? 'border-l-4 border-l-primary'
                    : ''
              }`}
            >
              {isProcessed && (
                <div className="flex items-center gap-2 px-4 py-2 bg-success/10 border-b border-success/20 rounded-t-lg">
                  <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                  <span className="text-sm font-semibold text-success">
                    Devis SAP créé{meta?.sapDocNum ? ` — N° ${meta.sapDocNum}` : ''}
                  </span>
                </div>
              )}
              {isArchived && (
                <div className="flex items-center gap-2 px-4 py-1.5 bg-muted/50 border-b border-muted rounded-t-lg">
                  <Archive className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                  <span className="text-xs text-muted-foreground">Archivé</span>
                </div>
              )}

              <div className="flex items-start gap-4 p-4">
                {/* Icône source */}
                <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${isManual ? 'bg-orange-100' : item.email.isRead ? 'bg-muted' : 'bg-primary/10'}`}>
                  {isManual
                    ? <Phone className="w-5 h-5 text-orange-600" />
                    : <Mail className={`w-5 h-5 ${item.email.isRead ? 'text-muted-foreground' : 'text-primary'}`} />
                  }
                </div>

                {/* Contenu email */}
                <div className="flex-1 min-w-0" onClick={() => {
                  if (item.isQuote) onSelectQuote(item);
                  else if (onAnalyze) onAnalyze(item);
                }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-medium ${item.email.isRead ? 'text-muted-foreground' : 'text-foreground'}`}>
                      {item.email.from.emailAddress.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      &lt;{item.email.from.emailAddress.address}&gt;
                    </span>
                  </div>

                  <h3 className={`text-sm mb-1 ${item.email.isRead ? 'font-normal' : 'font-semibold'}`}>
                    {item.email.subject}
                  </h3>

                  <p className="text-sm text-muted-foreground line-clamp-1">
                    {item.email.bodyPreview}
                  </p>

                  <div className="flex items-center gap-3 mt-2">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="w-3 h-3" />
                      {format(new Date(item.email.receivedDateTime), 'dd MMM HH:mm', { locale: fr })}
                    </span>
                    {item.email.hasAttachments && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Paperclip className="w-3 h-3" />
                        {item.email.attachments.length} pièce(s)
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions droite */}
                <div className="flex flex-col items-end gap-2">
                  {/* Badges statut devis */}
                  {item.isQuote ? (
                    <>
                      {isManual && (
                        <Badge variant="outline" className="border-orange-400 text-orange-600 text-xs">
                          <Phone className="w-3 h-3 mr-1" />
                          Source : Manuel
                        </Badge>
                      )}
                      {!isProcessed && (
                        item.analysisResult?.classification === 'PROBABLE_QUOTE' ? (
                          <Badge className="bg-amber-100 text-amber-700 border border-amber-300">
                            <FileText className="w-3 h-3 mr-1" />
                            Probable devis
                          </Badge>
                        ) : (
                          <Badge className="status-badge-quote">
                            <FileText className="w-3 h-3 mr-1" />
                            Devis détecté
                          </Badge>
                        )
                      )}
                      {!isProcessed && !isManual && (
                        <Badge
                          variant="outline"
                          className={
                            item.detection.confidence === 'high'   ? 'border-success text-success' :
                            item.detection.confidence === 'medium' ? 'border-warning text-warning' :
                            'border-muted-foreground'
                          }
                        >
                          Confiance: {item.detection.confidence}
                        </Badge>
                      )}
                      <Button
                        size="sm"
                        variant={isProcessed ? 'ghost' : item.analysisResult ? 'default' : 'outline'}
                        disabled={analyzingEmailId === item.email.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectQuote(item);
                        }}
                      >
                        {analyzingEmailId === item.email.id ? (
                          <>
                            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                            Analyse...
                          </>
                        ) : (
                          <>
                            <FileText className="w-3 h-3 mr-1" />
                            {isProcessed ? 'Consulter' : 'Visualiser'}
                          </>
                        )}
                      </Button>
                      {onReanalyze && item.analysisResult && !isManual && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={analyzingEmailId === item.email.id}
                          title="Relancer l'analyse complète"
                          onClick={(e) => {
                            e.stopPropagation();
                            onReanalyze(item.email.id);
                          }}
                        >
                          {analyzingEmailId === item.email.id
                            ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <RefreshCw className="w-3 h-3" />
                          }
                          <span className="ml-1">Réanalyser</span>
                        </Button>
                      )}
                    </>
                  ) : (
                    <>
                      <Badge variant="secondary">Non pertinent</Badge>
                      {onAnalyze && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={analyzingEmailId === item.email.id}
                          onClick={(e) => { e.stopPropagation(); onAnalyze(item); }}
                        >
                          {analyzingEmailId === item.email.id ? (
                            <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Analyse...</>
                          ) : (
                            <><RefreshCw className="w-3 h-3 mr-1" />Analyser</>
                          )}
                        </Button>
                      )}
                    </>
                  )}

                  {/* Ligne d'actions rapides : étoile + archive */}
                  <div className="flex items-center gap-1 mt-1">
                    {onStar && (
                      <button
                        title={isStarred ? 'Retirer des étoilés' : 'Marquer comme important'}
                        onClick={(e) => { e.stopPropagation(); onStar(item.email.id, !isStarred); }}
                        className={`p-1 rounded hover:bg-muted transition-colors ${isStarred ? 'text-yellow-500' : 'text-muted-foreground hover:text-yellow-500'}`}
                      >
                        <Star className={`w-4 h-4 ${isStarred ? 'fill-yellow-500' : ''}`} />
                      </button>
                    )}
                    {onArchive && (
                      <button
                        title={isArchived ? 'Désarchiver' : 'Archiver'}
                        onClick={(e) => { e.stopPropagation(); onArchive(item.email.id, !isArchived); }}
                        className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                      >
                        {isArchived
                          ? <ArchiveRestore className="w-4 h-4" />
                          : <Archive className="w-4 h-4" />
                        }
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
