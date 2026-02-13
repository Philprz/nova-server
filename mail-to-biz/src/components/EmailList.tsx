import { Mail, Paperclip, FileText, Clock, Loader2 } from 'lucide-react';
import { ProcessedEmail } from '@/types/email';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { format } from 'date-fns';
import { fr } from 'date-fns/locale';

interface EmailListProps {
  emails: ProcessedEmail[];
  onSelectQuote: (quote: ProcessedEmail) => void;
  analyzingEmailId?: string | null;
}

export function EmailList({ emails, onSelectQuote, analyzingEmailId }: EmailListProps) {
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h2 className="section-title">Emails reçus</h2>
        <Badge variant="secondary">{emails.length} messages</Badge>
      </div>

      <div className="space-y-2">
        {emails.map((item) => (
          <Card 
            key={item.email.id}
            className={`p-4 card-elevated cursor-pointer ${item.isQuote ? 'border-l-4 border-l-primary' : ''}`}
          >
            <div className="flex items-start gap-4">
              <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${item.email.isRead ? 'bg-muted' : 'bg-primary/10'}`}>
                <Mail className={`w-5 h-5 ${item.email.isRead ? 'text-muted-foreground' : 'text-primary'}`} />
              </div>
              
              <div className="flex-1 min-w-0">
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
              
              <div className="flex flex-col items-end gap-2">
                {item.isQuote ? (
                  <>
                    <Badge className="status-badge-quote">
                      <FileText className="w-3 h-3 mr-1" />
                      Devis détecté
                    </Badge>
                    <Badge 
                      variant="outline" 
                      className={
                        item.detection.confidence === 'high' ? 'border-success text-success' :
                        item.detection.confidence === 'medium' ? 'border-warning text-warning' :
                        'border-muted-foreground'
                      }
                    >
                      Confiance: {item.detection.confidence}
                    </Badge>
                    <Button
                      size="sm"
                      variant={item.analysisResult ? "default" : "outline"}
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
                      ) : item.analysisResult ? (
                        <>
                          <FileText className="w-3 h-3 mr-1" />
                          Synthèse
                        </>
                      ) : (
                        'Analyser'
                      )}
                    </Button>
                  </>
                ) : (
                  <Badge variant="secondary">Non pertinent</Badge>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
