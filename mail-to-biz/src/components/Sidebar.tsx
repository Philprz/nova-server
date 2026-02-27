import { Inbox, FileCheck, Settings, FileText, Plug, Download } from 'lucide-react';
import { cn } from '@/lib/utils';

type View = 'account-selection' | 'inbox' | 'quotes' | 'config' | 'connectors' | 'summary';

interface SidebarProps {
  currentView: View;
  onViewChange: (view: 'inbox' | 'quotes' | 'config' | 'connectors') => void;
  quotesCount: number;
  pendingCount: number;
}

export function Sidebar({ currentView, onViewChange, quotesCount, pendingCount }: SidebarProps) {
  type NavView = 'inbox' | 'quotes' | 'config' | 'connectors';
  const navItems: { id: NavView; label: string; icon: typeof Inbox; badge?: number }[] = [
    { id: 'inbox', label: 'Boîte de réception', icon: Inbox },
    { id: 'quotes', label: 'Demandes de devis', icon: FileText, badge: pendingCount > 0 ? pendingCount : undefined },
    { id: 'connectors', label: 'Connecteurs', icon: Plug },
    { id: 'config', label: 'Configuration', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-sidebar border-r border-sidebar-border flex flex-col">
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
              currentView === item.id
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/50"
            )}
          >
            <item.icon className="w-5 h-5" />
            <span className="flex-1 text-left">{item.label}</span>
            {item.badge && (
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-warning text-warning-foreground">
                {item.badge}
              </span>
            )}
          </button>
        ))}
      </nav>
      
      <div className="p-4 border-t border-sidebar-border space-y-2">
        <div className="flex items-center gap-2 text-xs text-sidebar-foreground/60">
          <FileCheck className="w-4 h-4" />
          <span>{quotesCount} devis détectés</span>
        </div>
        <a
          href="/api/sap/items/export"
          download
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors"
          title="Télécharger le catalogue articles SAP (.xlsx)"
        >
          <Download className="w-4 h-4 flex-shrink-0" />
          <span>Exporter catalogue SAP</span>
        </a>
      </div>
    </aside>
  );
}
