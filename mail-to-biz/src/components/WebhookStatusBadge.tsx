/**
 * Badge affichant le statut du traitement automatique des emails
 *
 * Affiche:
 * - Nombre d'emails traités automatiquement
 * - Indicateur d'activité (pulse animation)
 * - Tooltip avec dernière vérification
 */

import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Zap } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { fr } from 'date-fns/locale';

interface WebhookStatusBadgeProps {
  notifiedCount: number;
  lastCheck: number;
  isActive: boolean;
}

export function WebhookStatusBadge({
  notifiedCount,
  lastCheck,
  isActive
}: WebhookStatusBadgeProps) {
  if (!isActive) {
    return null;
  }

  const lastCheckText = formatDistanceToNow(new Date(lastCheck), {
    locale: fr,
    addSuffix: true
  });

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant={notifiedCount > 0 ? "default" : "secondary"}
            className="gap-1.5 cursor-help"
          >
            <Zap className={`w-3 h-3 ${isActive ? 'animate-pulse' : ''}`} />
            <span>{notifiedCount} traité{notifiedCount > 1 ? 's' : ''}</span>
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <div className="text-sm space-y-1">
            <p className="font-medium">Traitement automatique actif</p>
            <p className="text-muted-foreground">
              {notifiedCount} email{notifiedCount > 1 ? 's' : ''} traité{notifiedCount > 1 ? 's' : ''} en background
            </p>
            <p className="text-xs text-muted-foreground">
              Dernière vérification {lastCheckText}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
