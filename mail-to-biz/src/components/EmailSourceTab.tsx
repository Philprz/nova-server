/**
 * EmailSourceTab.tsx
 * Onglet "Email source" dans la synthèse de devis.
 * Affiche les métadonnées + le corps HTML de l'email original.
 *
 * Approche : fetch() + dangerouslySetInnerHTML avec DOMPurify
 * (évite les problèmes d'iframe cross-origin/cookie en production)
 */

import { useState, useEffect } from 'react';
import DOMPurify from 'dompurify';
import { Mail, Loader2, AlertCircle, User, Calendar, FileText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface EmailSourceTabProps {
  emailId: string;
  fromName?: string;
  fromAddress?: string;
  subject?: string;
  receivedDateTime?: string;
  bodyPreview?: string; // fallback si body non chargé
}

export function EmailSourceTab({
  emailId,
  fromName,
  fromAddress,
  subject,
  receivedDateTime,
  bodyPreview,
}: EmailSourceTabProps) {
  const [bodyHtml, setBodyHtml] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!emailId) return;

    setLoading(true);
    setError(null);

    fetch(`/api/graph/emails/body?id=${encodeURIComponent(emailId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Erreur ${r.status}: impossible de charger le mail`);
        return r.text();
      })
      .then((html) => {
        // Sanitiser le HTML pour éviter XSS
        const clean = DOMPurify.sanitize(html, {
          ALLOWED_TAGS: [
            'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u',
            'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'table', 'tr', 'td', 'th', 'tbody', 'thead', 'tfoot',
            'a', 'img', 'hr', 'blockquote', 'pre', 'code',
          ],
          ALLOWED_ATTR: ['href', 'src', 'alt', 'style', 'class', 'width', 'height', 'colspan', 'rowspan'],
          FORBID_TAGS: ['script', 'iframe', 'form', 'input', 'object', 'embed'],
          FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
        });
        setBodyHtml(clean);
      })
      .catch((err) => {
        setError(err.message || 'Erreur lors du chargement du corps de l\'email');
      })
      .finally(() => setLoading(false));
  }, [emailId]);

  const formattedDate = receivedDateTime
    ? new Date(receivedDateTime).toLocaleString('fr-FR', {
        dateStyle: 'long',
        timeStyle: 'short',
      })
    : null;

  return (
    <div className="space-y-4">
      {/* Métadonnées */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" />
            Informations de l'email
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <User className="h-3.5 w-3.5" />
              <span>De</span>
            </div>
            <div className="font-medium">
              {fromName ? (
                <span>
                  {fromName}{' '}
                  {fromAddress && (
                    <span className="text-muted-foreground font-normal">&lt;{fromAddress}&gt;</span>
                  )}
                </span>
              ) : (
                <span className="text-muted-foreground">{fromAddress || '—'}</span>
              )}
            </div>

            <div className="flex items-center gap-1.5 text-muted-foreground">
              <FileText className="h-3.5 w-3.5" />
              <span>Sujet</span>
            </div>
            <div className="font-medium">{subject || '(Sans objet)'}</div>

            {formattedDate && (
              <>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  <span>Reçu le</span>
                </div>
                <div className="text-muted-foreground">{formattedDate}</div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Corps du mail */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Corps du message</CardTitle>
            {loading && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Chargement...
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              Chargement du message...
            </div>
          ) : bodyHtml ? (
            <div
              className="email-body max-h-[500px] overflow-auto text-sm border rounded-md p-4 bg-white dark:bg-gray-950"
              style={{ fontFamily: 'Arial, sans-serif', lineHeight: '1.5' }}
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{ __html: bodyHtml }}
            />
          ) : bodyPreview ? (
            /* Fallback sur bodyPreview si body non disponible */
            <div className="space-y-2">
              <Badge variant="secondary" className="text-xs">Aperçu (version tronquée)</Badge>
              <pre className="text-sm bg-muted/30 border rounded-md p-4 overflow-auto max-h-64 whitespace-pre-wrap font-sans">
                {bodyPreview}
              </pre>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm italic">Corps du message non disponible.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
