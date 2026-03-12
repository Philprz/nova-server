import { Search, Star, Paperclip, MailOpen, X, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export type StatusFilter     = 'all' | 'pending' | 'processed' | 'archived';
export type TypeFilter       = 'all' | 'quote' | 'other';
export type SourceFilter     = 'all' | 'email' | 'manual';
export type ConfidenceFilter = 'all' | 'high' | 'medium' | 'low';

export interface EmailFiltersState {
  search:      string;
  status:      StatusFilter;
  type:        TypeFilter;
  source:      SourceFilter;
  confidence:  ConfidenceFilter;
  unreadOnly:  boolean;
  withAttachments: boolean;
  starredOnly: boolean;
}

export const DEFAULT_FILTERS: EmailFiltersState = {
  search:         '',
  status:         'all',
  type:           'all',
  source:         'all',
  confidence:     'all',
  unreadOnly:     false,
  withAttachments: false,
  starredOnly:    false,
};

interface EmailFiltersProps {
  filters:   EmailFiltersState;
  onChange:  (f: EmailFiltersState) => void;
  totalCount: number;
  filteredCount: number;
}

const STATUS_LABELS: Record<StatusFilter, string> = {
  all:       'Tous les statuts',
  pending:   'Non traités',
  processed: 'Traités',
  archived:  'Archivés',
};

const TYPE_LABELS: Record<TypeFilter, string> = {
  all:   'Tous types',
  quote: 'Devis uniquement',
  other: 'Non devis',
};

const SOURCE_LABELS: Record<SourceFilter, string> = {
  all:    'Toutes sources',
  email:  'Email',
  manual: 'Saisie manuelle',
};

const CONFIDENCE_LABELS: Record<ConfidenceFilter, string> = {
  all:    'Toutes confiances',
  high:   'Confiance : Haute',
  medium: 'Confiance : Moyenne',
  low:    'Confiance : Faible',
};

export function EmailFilters({ filters, onChange, totalCount, filteredCount }: EmailFiltersProps) {
  const set = (patch: Partial<EmailFiltersState>) => onChange({ ...filters, ...patch });

  const activeCount = [
    filters.search !== '',
    filters.status !== 'all',
    filters.type !== 'all',
    filters.source !== 'all',
    filters.confidence !== 'all',
    filters.unreadOnly,
    filters.withAttachments,
    filters.starredOnly,
  ].filter(Boolean).length;

  const reset = () => onChange(DEFAULT_FILTERS);

  return (
    <div className="space-y-2 mb-4">
      {/* Ligne 1 : recherche + filtres dropdown */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Recherche texte */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <Input
            className="pl-8 h-8 text-sm"
            placeholder="Rechercher… (objet, expéditeur)"
            value={filters.search}
            onChange={e => set({ search: e.target.value })}
          />
          {filters.search && (
            <button
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              onClick={() => set({ search: '' })}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Statut */}
        <DropdownFilter
          label={filters.status !== 'all' ? STATUS_LABELS[filters.status] : 'Statut'}
          active={filters.status !== 'all'}
          value={filters.status}
          options={Object.entries(STATUS_LABELS) as [StatusFilter, string][]}
          onChange={v => set({ status: v as StatusFilter })}
        />

        {/* Type */}
        <DropdownFilter
          label={filters.type !== 'all' ? TYPE_LABELS[filters.type] : 'Type'}
          active={filters.type !== 'all'}
          value={filters.type}
          options={Object.entries(TYPE_LABELS) as [TypeFilter, string][]}
          onChange={v => set({ type: v as TypeFilter })}
        />

        {/* Source */}
        <DropdownFilter
          label={filters.source !== 'all' ? SOURCE_LABELS[filters.source] : 'Source'}
          active={filters.source !== 'all'}
          value={filters.source}
          options={Object.entries(SOURCE_LABELS) as [SourceFilter, string][]}
          onChange={v => set({ source: v as SourceFilter })}
        />

        {/* Confiance */}
        <DropdownFilter
          label={filters.confidence !== 'all' ? CONFIDENCE_LABELS[filters.confidence] : 'Confiance'}
          active={filters.confidence !== 'all'}
          value={filters.confidence}
          options={Object.entries(CONFIDENCE_LABELS) as [ConfidenceFilter, string][]}
          onChange={v => set({ confidence: v as ConfidenceFilter })}
        />
      </div>

      {/* Ligne 2 : toggles rapides + compteur */}
      <div className="flex flex-wrap items-center gap-2">
        <ToggleChip
          icon={<Star className="w-3 h-3" />}
          label="Étoilés"
          active={filters.starredOnly}
          onClick={() => set({ starredOnly: !filters.starredOnly })}
        />
        <ToggleChip
          icon={<MailOpen className="w-3 h-3" />}
          label="Non lus"
          active={filters.unreadOnly}
          onClick={() => set({ unreadOnly: !filters.unreadOnly })}
        />
        <ToggleChip
          icon={<Paperclip className="w-3 h-3" />}
          label="Avec PJ"
          active={filters.withAttachments}
          onClick={() => set({ withAttachments: !filters.withAttachments })}
        />

        <div className="flex-1" />

        {/* Compteur */}
        <span className="text-xs text-muted-foreground">
          {filteredCount === totalCount
            ? `${totalCount} message${totalCount > 1 ? 's' : ''}`
            : `${filteredCount} / ${totalCount} message${totalCount > 1 ? 's' : ''}`}
        </span>

        {/* Réinitialiser */}
        {activeCount > 0 && (
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs gap-1" onClick={reset}>
            <X className="w-3 h-3" />
            Effacer filtres
            <Badge variant="secondary" className="ml-1 h-4 px-1 text-xs">{activeCount}</Badge>
          </Button>
        )}
      </div>
    </div>
  );
}

// ---- Sous-composants ----

function DropdownFilter<T extends string>({
  label, active, value, options, onChange,
}: {
  label: string;
  active: boolean;
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={active ? 'default' : 'outline'}
          size="sm"
          className="h-8 text-xs gap-1 pr-2"
        >
          {label}
          <ChevronDown className="w-3 h-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[180px]">
        <DropdownMenuRadioGroup value={value} onValueChange={v => onChange(v as T)}>
          {options.map(([val, lbl]) => (
            <DropdownMenuRadioItem key={val} value={val} className="text-sm">
              {lbl}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ToggleChip({
  icon, label, active, onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors ${
        active
          ? 'bg-primary text-primary-foreground border-primary'
          : 'bg-background border-border text-muted-foreground hover:border-primary hover:text-foreground'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
