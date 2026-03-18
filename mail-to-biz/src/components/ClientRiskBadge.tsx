/**
 * ClientRiskBadge — affiche le résultat de la vérification solvabilité client (Pappers).
 *
 * Règles d'affichage :
 *  - Pays != FR            → badge gris  "Client non français – non vérifié"
 *  - OK                    → badge vert  "Client vérifié – aucune procédure"
 *  - WARNING               → badge orange "Risque détecté : redressement judiciaire"
 *  - BLOCKED               → badge rouge  "Client en liquidation judiciaire"
 *  - UNKNOWN / absent      → badge gris   "Vérification indisponible"
 *
 * Tooltip : source, date de vérification, raison détaillée.
 */

import { ClientRisk } from '@/lib/graphApi';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { CheckCircle, AlertTriangle, XCircle, HelpCircle, Globe } from 'lucide-react';

interface ClientRiskBadgeProps {
  risk?: ClientRisk | null;
}

interface RiskConfig {
  icon: React.ReactNode;
  text: string;
  bg: string;
  text_color: string;
  border: string;
}

function getRiskConfig(risk?: ClientRisk | null): RiskConfig {
  if (!risk) {
    return {
      icon: <HelpCircle className="w-3.5 h-3.5" />,
      text: 'Non vérifié',
      bg: 'bg-gray-100',
      text_color: 'text-gray-600',
      border: 'border-gray-200',
    };
  }

  if (risk.country !== 'FR') {
    return {
      icon: <Globe className="w-3.5 h-3.5" />,
      text: 'Client non français – non vérifié',
      bg: 'bg-gray-100',
      text_color: 'text-gray-500',
      border: 'border-gray-200',
    };
  }

  switch (risk.status) {
    case 'OK':
      return {
        icon: <CheckCircle className="w-3.5 h-3.5" />,
        text: 'Client vérifié – aucune procédure',
        bg: 'bg-green-50',
        text_color: 'text-green-700',
        border: 'border-green-200',
      };
    case 'WARNING':
      return {
        icon: <AlertTriangle className="w-3.5 h-3.5" />,
        text: risk.reason ?? 'Risque détecté',
        bg: 'bg-orange-50',
        text_color: 'text-orange-700',
        border: 'border-orange-300',
      };
    case 'BLOCKED':
      return {
        icon: <XCircle className="w-3.5 h-3.5" />,
        text: 'Client en liquidation judiciaire',
        bg: 'bg-red-50',
        text_color: 'text-red-700',
        border: 'border-red-300',
      };
    default: // UNKNOWN
      return {
        icon: <HelpCircle className="w-3.5 h-3.5" />,
        text: 'Vérification indisponible',
        bg: 'bg-gray-100',
        text_color: 'text-gray-500',
        border: 'border-gray-200',
      };
  }
}

function formatCheckedAt(iso?: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function ClientRiskBadge({ risk }: ClientRiskBadgeProps) {
  const cfg = getRiskConfig(risk);

  const badge = (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${cfg.bg} ${cfg.text_color} ${cfg.border} select-none`}
    >
      {cfg.icon}
      {cfg.text}
    </span>
  );

  // Pas de tooltip si pas de données Pappers exploitables
  if (!risk || risk.country !== 'FR') {
    return badge;
  }

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs text-xs space-y-1 p-3">
          <p className="font-semibold mb-1">Vérification solvabilité</p>
          <p><span className="text-muted-foreground">Source :</span> {risk.source ?? 'Pappers'}</p>
          <p><span className="text-muted-foreground">Vérifié le :</span> {formatCheckedAt(risk.checked_at)}</p>
          {risk.reason && (
            <p><span className="text-muted-foreground">Détail :</span> {risk.reason}</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
