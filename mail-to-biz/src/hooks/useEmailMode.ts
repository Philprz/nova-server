// Hook pour gérer le mode d'affichage des emails (démo vs live)
import { useState, useCallback } from 'react';

export type EmailMode = 'demo' | 'live';

export function useEmailMode() {
  // Mode LIVE par défaut - toujours démarrer en mode live (vraie boîte mail)
  const [mode, setModeState] = useState<EmailMode>('live');

  const setMode = useCallback((newMode: EmailMode) => {
    setModeState(newMode);
  }, []);

  const toggleMode = useCallback(() => {
    setModeState((current) => (current === 'demo' ? 'live' : 'demo'));
  }, []);

  return {
    mode,
    setMode,
    toggleMode,
    isDemoMode: mode === 'demo',
    isLiveMode: mode === 'live',
  };
}
