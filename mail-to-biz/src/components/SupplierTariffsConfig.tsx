import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  FolderOpen,
  Loader2,
  CheckCircle,
  XCircle,
  RefreshCw,
  FileText,
  Database,
  FolderSearch,
  Play,
  Square
} from 'lucide-react';
import { toast } from 'sonner';

interface FolderConfig {
  folder_path: string;
  exists: boolean;
  configured: boolean;
}

interface IndexationStats {
  total_files: number;
  files_by_status: Record<string, number>;
  total_products: number;
  last_indexation: {
    started_at: string;
    completed_at: string;
    status: string;
    files_processed: number;
    files_success: number;
    files_error: number;
    items_extracted: number;
  } | null;
}

interface IndexationStatus {
  indexation_running: boolean;
  progress: number;
  current_file: string | null;
  stats: IndexationStats;
}

interface FolderContents {
  folder_path: string;
  total_files: number;
  files_by_type: Record<string, number>;
}

const API_BASE = '/api/supplier-tariffs';

export function SupplierTariffsConfig() {
  const [folderConfig, setFolderConfig] = useState<FolderConfig | null>(null);
  const [folderPath, setFolderPath] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [indexationStatus, setIndexationStatus] = useState<IndexationStatus | null>(null);
  const [folderContents, setFolderContents] = useState<FolderContents | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);

  // Charger la configuration au montage
  useEffect(() => {
    loadFolderConfig();
    loadIndexationStatus();
  }, []);

  // Polling pendant l'indexation
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;

    if (isIndexing || indexationStatus?.indexation_running) {
      interval = setInterval(() => {
        loadIndexationStatus();
      }, 2000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isIndexing, indexationStatus?.indexation_running]);

  const loadFolderConfig = async () => {
    try {
      const response = await fetch(`${API_BASE}/folder`);
      const data = await response.json();
      setFolderConfig(data);
      setFolderPath(data.folder_path || '');

      if (data.configured && data.exists) {
        loadFolderContents();
      }
    } catch (error) {
      console.error('Erreur chargement config:', error);
      toast.error('Erreur lors du chargement de la configuration');
    } finally {
      setIsLoading(false);
    }
  };

  const loadIndexationStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/status`);
      const data = await response.json();
      setIndexationStatus(data);

      // Mettre à jour l'état local si l'indexation est terminée
      if (!data.indexation_running && isIndexing) {
        setIsIndexing(false);
        toast.success('Indexation terminee !');
      }
    } catch (error) {
      console.error('Erreur chargement statut:', error);
    }
  };

  const loadFolderContents = async () => {
    try {
      const response = await fetch(`${API_BASE}/folder/contents`);
      if (response.ok) {
        const data = await response.json();
        setFolderContents(data);
      }
    } catch (error) {
      console.error('Erreur chargement contenu:', error);
    }
  };

  const handleBrowseFolder = async () => {
    setIsBrowsing(true);
    try {
      const response = await fetch(`${API_BASE}/browse?start_path=${encodeURIComponent(folderPath || 'C:\\')}`);
      const data = await response.json();

      if (data.success && data.folder_path) {
        setFolderPath(data.folder_path);
        toast.success('Dossier selectionne');
      } else if (!data.success) {
        toast.info('Selection annulee');
      }
    } catch (error) {
      console.error('Erreur browse:', error);
      toast.error('Erreur lors de l\'ouverture du dialogue');
    } finally {
      setIsBrowsing(false);
    }
  };

  const handleSaveFolder = async () => {
    if (!folderPath.trim()) {
      toast.error('Veuillez specifier un chemin de dossier');
      return;
    }

    setIsSaving(true);
    try {
      const response = await fetch(`${API_BASE}/folder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath.trim() })
      });

      const data = await response.json();

      if (response.ok) {
        toast.success('Dossier configure avec succes');
        setFolderConfig({ folder_path: folderPath, exists: true, configured: true });
        loadFolderContents();
      } else {
        toast.error(data.detail || 'Erreur lors de la sauvegarde');
      }
    } catch (error) {
      console.error('Erreur sauvegarde:', error);
      toast.error('Erreur lors de la sauvegarde');
    } finally {
      setIsSaving(false);
    }
  };

  const handleStartIndexation = async (clearExisting: boolean = false) => {
    setIsIndexing(true);
    try {
      const response = await fetch(`${API_BASE}/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clear_existing: clearExisting,
          recursive: true
        })
      });

      const data = await response.json();

      if (response.ok) {
        toast.success('Indexation demarree');
      } else {
        toast.error(data.detail || 'Erreur lors du demarrage');
        setIsIndexing(false);
      }
    } catch (error) {
      console.error('Erreur indexation:', error);
      toast.error('Erreur lors du demarrage de l\'indexation');
      setIsIndexing(false);
    }
  };

  const handleStopIndexation = async () => {
    try {
      const response = await fetch(`${API_BASE}/index/stop`, { method: 'POST' });
      const data = await response.json();

      if (data.success) {
        toast.info('Arret demande');
        setIsIndexing(false);
      }
    } catch (error) {
      console.error('Erreur arret:', error);
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString('fr-FR');
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const isRunning = indexationStatus?.indexation_running || isIndexing;

  return (
    <div className="space-y-6">
      {/* Configuration du dossier */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="w-5 h-5 text-primary" />
              Dossier Tarifs Fournisseurs
            </CardTitle>
            {folderConfig?.configured ? (
              <Badge className="bg-success text-success-foreground">
                <CheckCircle className="w-3 h-3 mr-1" /> Configure
              </Badge>
            ) : (
              <Badge variant="outline">
                <XCircle className="w-3 h-3 mr-1" /> Non configure
              </Badge>
            )}
          </div>
          <CardDescription>
            Selectionnez le dossier contenant les fichiers de tarifs fournisseurs (PDF, Excel, CSV, images)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Champ de saisie + bouton parcourir */}
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                placeholder="C:\Tarifs\Fournisseurs"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <Button
              variant="outline"
              onClick={handleBrowseFolder}
              disabled={isBrowsing}
            >
              {isBrowsing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FolderSearch className="w-4 h-4" />
              )}
              <span className="ml-2">Parcourir</span>
            </Button>
          </div>

          {/* Bouton sauvegarder */}
          <Button
            onClick={handleSaveFolder}
            disabled={isSaving || !folderPath.trim()}
            className="w-full"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Sauvegarde...
              </>
            ) : (
              <>
                <CheckCircle className="w-4 h-4 mr-2" />
                Enregistrer le chemin
              </>
            )}
          </Button>

          {/* Apercu du contenu du dossier */}
          {folderContents && (
            <div className="p-4 rounded-lg bg-muted border border-border">
              <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                <FileText className="w-4 h-4" />
                Contenu du dossier
              </h4>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total fichiers:</span>
                  <span className="font-medium">{folderContents.total_files}</span>
                </div>
                {Object.entries(folderContents.files_by_type).map(([type, count]) => (
                  <div key={type} className="flex justify-between">
                    <span className="text-muted-foreground">{type.toUpperCase()}:</span>
                    <span className="font-medium">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Indexation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Database className="w-5 h-5 text-primary" />
              Indexation des Tarifs
            </CardTitle>
            {isRunning && (
              <Badge className="bg-blue-500 text-white animate-pulse">
                <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> En cours
              </Badge>
            )}
          </div>
          <CardDescription>
            Parsez et indexez le contenu des fichiers pour permettre la recherche rapide
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Progression */}
          {isRunning && indexationStatus && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Progression</span>
                <span className="font-medium">{indexationStatus.progress}%</span>
              </div>
              <Progress value={indexationStatus.progress} />
              {indexationStatus.current_file && (
                <p className="text-xs text-muted-foreground truncate">
                  Fichier en cours: {indexationStatus.current_file}
                </p>
              )}
            </div>
          )}

          {/* Boutons d'action */}
          <div className="flex gap-2">
            {isRunning ? (
              <Button
                variant="destructive"
                onClick={handleStopIndexation}
                className="flex-1"
              >
                <Square className="w-4 h-4 mr-2" />
                Arreter
              </Button>
            ) : (
              <>
                <Button
                  onClick={() => handleStartIndexation(false)}
                  disabled={!folderConfig?.configured}
                  className="flex-1"
                >
                  <Play className="w-4 h-4 mr-2" />
                  Lancer l'indexation
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleStartIndexation(true)}
                  disabled={!folderConfig?.configured}
                >
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Reindexer tout
                </Button>
              </>
            )}
          </div>

          {/* Statistiques */}
          {indexationStatus?.stats && (
            <div className="p-4 rounded-lg bg-muted border border-border space-y-3">
              <h4 className="font-medium text-sm">Statistiques d'indexation</h4>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="p-2 rounded bg-background">
                  <span className="text-muted-foreground block text-xs">Fichiers indexes</span>
                  <span className="font-bold text-lg">{indexationStatus.stats.total_files}</span>
                </div>
                <div className="p-2 rounded bg-background">
                  <span className="text-muted-foreground block text-xs">Produits extraits</span>
                  <span className="font-bold text-lg">{indexationStatus.stats.total_products}</span>
                </div>
              </div>

              {indexationStatus.stats.last_indexation && (
                <div className="pt-2 border-t border-border text-xs text-muted-foreground">
                  <p>Derniere indexation: {formatDate(indexationStatus.stats.last_indexation.completed_at || indexationStatus.stats.last_indexation.started_at)}</p>
                  <p>
                    Resultat: {indexationStatus.stats.last_indexation.files_success} reussis,
                    {' '}{indexationStatus.stats.last_indexation.files_error} erreurs,
                    {' '}{indexationStatus.stats.last_indexation.items_extracted} produits
                  </p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
