import { Mail, Bell } from 'lucide-react';

interface AppHeaderProps {
  pendingCount: number;
}

export function AppHeader({ pendingCount }: AppHeaderProps) {
  return (
    <header className="bg-header text-header-foreground px-6 py-3 flex items-center justify-between border-b border-sidebar-border">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary">
          <Mail className="w-5 h-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Devis Entrants</h1>
          <p className="text-xs text-sidebar-foreground/70">Office 365 → Pré-SAP B1</p>
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        {pendingCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-warning/20 text-warning">
            <Bell className="w-4 h-4" />
            <span className="text-sm font-medium">{pendingCount} en attente</span>
          </div>
        )}
      </div>
    </header>
  );
}
