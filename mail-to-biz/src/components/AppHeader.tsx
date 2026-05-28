import { Mail, Bell, LogOut, User, Sun, Moon } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { Button } from '@/components/ui/button';

interface AppHeaderProps {
  pendingCount: number;
}

export function AppHeader({ pendingCount }: AppHeaderProps) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="bg-header text-header-foreground px-6 py-3 flex items-center justify-between border-b-2 border-transparent [border-image:var(--gradient-main)_1]">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg its-logo-badge">
          <Mail className="w-5 h-5" />
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
        <button
          type="button"
          onClick={toggleTheme}
          className="theme-toggle"
          aria-label="Basculer le theme"
          title={theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        {user && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-sm text-sidebar-foreground/80">
              <User className="w-4 h-4" />
              <span>{user.sap_username}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent gap-1.5"
              title="Se déconnecter"
            >
              <LogOut className="w-4 h-4" />
              <span className="text-xs">Déconnexion</span>
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
