/**
 * ExtractedDataTab.tsx
 * Onglet "Données extraites" dans la synthèse de devis.
 *
 * Affiche un tableau comparatif des données extraites par l'IA,
 * avec la possibilité de corriger chaque champ manuellement.
 * Les corrections sont persistées via PUT /api/graph/emails/{id}/corrections.
 */

import { useState, useEffect } from 'react';
import { Pencil, Check, X, Loader2, AlertCircle, RotateCcw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import {
  fetchCorrections,
  saveCorrections,
  QuoteCorrection,
} from '@/lib/graphApi';
import { EmailAnalysisResult } from '@/lib/graphApi';

interface ExtractedDataTabProps {
  emailId: string;
  analysisResult?: EmailAnalysisResult;
}

interface FieldRow {
  label: string;
  value: string;
  fieldType: QuoteCorrection['field_type'];
  fieldName: string;
  fieldIndex?: number;
}

/** Construit la liste des champs éditables depuis analysisResult. */
function buildFieldRows(analysis?: EmailAnalysisResult): FieldRow[] {
  if (!analysis) return [];
  const rows: FieldRow[] = [];

  // --- Client ---
  const ed = analysis.extracted_data;
  if (ed?.client_name) {
    rows.push({
      label: 'Client (nom)',
      value: ed.client_name,
      fieldType: 'client',
      fieldName: 'client_name',
    });
  }
  if (ed?.client_card_code) {
    rows.push({
      label: 'Client (code SAP)',
      value: ed.client_card_code,
      fieldType: 'client',
      fieldName: 'client_card_code',
    });
  }
  if (ed?.client_email) {
    rows.push({
      label: 'Email client',
      value: ed.client_email,
      fieldType: 'client',
      fieldName: 'client_email',
    });
  }

  // --- Produits ---
  const products = analysis.product_matches ?? [];
  products.forEach((p, idx) => {
    const num = idx + 1;

    if (p.item_code) {
      rows.push({
        label: `Produit ${num} — Référence SAP`,
        value: p.item_code,
        fieldType: 'product',
        fieldName: 'item_code',
        fieldIndex: idx,
      });
    }
    if (p.item_name) {
      rows.push({
        label: `Produit ${num} — Description`,
        value: p.item_name,
        fieldType: 'product',
        fieldName: 'item_name',
        fieldIndex: idx,
      });
    }
    rows.push({
      label: `Produit ${num} — Quantité`,
      value: String(p.quantity ?? 1),
      fieldType: 'product',
      fieldName: 'quantity',
      fieldIndex: idx,
    });
    if ((p as any).unit_price != null) {
      rows.push({
        label: `Produit ${num} — Prix unitaire (€)`,
        value: String((p as any).unit_price),
        fieldType: 'product',
        fieldName: 'unit_price',
        fieldIndex: idx,
      });
    }
  });

  // --- Livraison ---
  if (ed?.delivery_requirement) {
    rows.push({
      label: 'Délai de livraison',
      value: ed.delivery_requirement,
      fieldType: 'delivery',
      fieldName: 'delivery_requirement',
    });
  }
  if (ed?.urgency && ed.urgency !== 'normal') {
    rows.push({
      label: 'Urgence',
      value: ed.urgency,
      fieldType: 'delivery',
      fieldName: 'urgency',
    });
  }
  if (ed?.notes) {
    rows.push({
      label: 'Notes',
      value: ed.notes,
      fieldType: 'delivery',
      fieldName: 'notes',
    });
  }

  return rows;
}

/** Clé unique pour identifier une correction. */
function correctionKey(c: Pick<QuoteCorrection, 'field_type' | 'field_name' | 'field_index'>): string {
  return `${c.field_type}:${c.field_index ?? ''}:${c.field_name}`;
}

export function ExtractedDataTab({ emailId, analysisResult }: ExtractedDataTabProps) {
  const { toast } = useToast();
  const [corrections, setCorrections] = useState<Map<string, QuoteCorrection>>(new Map());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [loadingCorrections, setLoadingCorrections] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fieldRows = buildFieldRows(analysisResult);

  // Charger les corrections existantes depuis le backend
  useEffect(() => {
    if (!emailId) return;
    setLoadingCorrections(true);
    fetchCorrections(emailId)
      .then((resp) => {
        const map = new Map<string, QuoteCorrection>();
        resp.corrections.forEach((c) => {
          map.set(correctionKey(c), c);
        });
        setCorrections(map);
      })
      .catch((err) => {
        console.error('Erreur chargement corrections:', err);
      })
      .finally(() => setLoadingCorrections(false));
  }, [emailId]);

  const startEdit = (row: FieldRow) => {
    const key = correctionKey(row);
    const existingCorrection = corrections.get(key);
    setEditValue(existingCorrection?.corrected_value ?? row.value);
    setEditingKey(key);
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditValue('');
  };

  const saveEdit = async (row: FieldRow) => {
    const key = correctionKey(row);
    if (!editValue.trim() || editValue === row.value) {
      cancelEdit();
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await saveCorrections(emailId, [
        {
          field_type: row.fieldType,
          field_name: row.fieldName,
          field_index: row.fieldIndex ?? null,
          corrected_value: editValue.trim(),
          original_value: row.value,
        },
      ]);

      // Mettre à jour le state local
      setCorrections((prev) => {
        const next = new Map(prev);
        next.set(key, {
          email_id: emailId,
          field_type: row.fieldType,
          field_name: row.fieldName,
          field_index: row.fieldIndex,
          corrected_value: editValue.trim(),
          original_value: row.value,
        });
        return next;
      });

      toast({
        title: 'Correction sauvegardée',
        description: `${row.label} : "${editValue.trim()}"`,
      });
      cancelEdit();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la sauvegarde');
    } finally {
      setSaving(false);
    }
  };

  const resetCorrection = async (row: FieldRow) => {
    const key = correctionKey(row);
    try {
      // Supprimer via DELETE endpoint (query params pour éviter les problèmes d'encodage email_id)
      const delParams = new URLSearchParams({
        email_id: emailId,
        field_type: row.fieldType,
        field_name: row.fieldName,
      });
      if (row.fieldIndex != null) delParams.set('field_index', String(row.fieldIndex));
      await fetch(`/api/graph/emails/corrections?${delParams.toString()}`, { method: 'DELETE' });
      setCorrections((prev) => {
        const next = new Map(prev);
        next.delete(key);
        return next;
      });
      toast({ title: 'Correction annulée', description: `${row.label} réinitialisé` });
    } catch (err) {
      console.error('Erreur suppression correction:', err);
    }
  };

  if (!analysisResult) {
    return (
      <div className="text-center py-12 text-muted-foreground text-sm">
        <p>Aucune analyse disponible. Analysez d'abord cet email.</p>
      </div>
    );
  }

  if (loadingCorrections) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Chargement des corrections...
      </div>
    );
  }

  const correctionCount = corrections.size;

  return (
    <div className="space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Données extraites par l'IA</p>
          <p className="text-xs text-muted-foreground">
            Cliquez sur le crayon pour corriger une valeur incorrecte.
          </p>
        </div>
        {correctionCount > 0 && (
          <Badge variant="secondary">
            {correctionCount} correction{correctionCount > 1 ? 's' : ''}
          </Badge>
        )}
      </div>

      {/* Tableau */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th className="text-left px-4 py-2.5 font-medium text-xs text-muted-foreground w-1/3">
                    Champ
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-xs text-muted-foreground">
                    Valeur extraite
                  </th>
                  <th className="text-right px-4 py-2.5 font-medium text-xs text-muted-foreground w-32">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {fieldRows.map((row) => {
                  const key = correctionKey(row);
                  const correction = corrections.get(key);
                  const isEditing = editingKey === key;
                  const isCorrected = !!correction;
                  const displayValue = correction?.corrected_value ?? row.value;

                  return (
                    <tr
                      key={key}
                      className={`border-b last:border-0 hover:bg-muted/20 transition-colors ${
                        isCorrected ? 'bg-amber-50/50 dark:bg-amber-950/20' : ''
                      }`}
                    >
                      {/* Champ */}
                      <td className="px-4 py-2.5 text-muted-foreground font-medium text-xs">
                        {row.label}
                        {isCorrected && (
                          <Badge variant="outline" className="ml-1.5 text-[10px] text-amber-600 border-amber-300">
                            Corrigé
                          </Badge>
                        )}
                      </td>

                      {/* Valeur */}
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <Input
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveEdit(row);
                              if (e.key === 'Escape') cancelEdit();
                            }}
                            className="h-7 text-sm"
                            autoFocus
                          />
                        ) : (
                          <div>
                            <span className={isCorrected ? 'font-medium text-amber-700 dark:text-amber-400' : ''}>
                              {displayValue}
                            </span>
                            {isCorrected && (
                              <span className="ml-2 text-xs text-muted-foreground line-through">
                                {row.value}
                              </span>
                            )}
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-1">
                          {isEditing ? (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => saveEdit(row)}
                                disabled={saving}
                                className="h-7 w-7 p-0 text-green-600 hover:text-green-700"
                              >
                                {saving ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Check className="h-3.5 w-3.5" />
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={cancelEdit}
                                className="h-7 w-7 p-0 text-red-500 hover:text-red-600"
                              >
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => startEdit(row)}
                                className="h-7 w-7 p-0"
                                title="Corriger"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              {isCorrected && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => resetCorrection(row)}
                                  className="h-7 w-7 p-0 text-muted-foreground"
                                  title="Réinitialiser"
                                >
                                  <RotateCcw className="h-3.5 w-3.5" />
                                </Button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {fieldRows.length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                Aucune donnée extraite disponible.
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Note de bas de page */}
      <p className="text-xs text-muted-foreground">
        Les corrections sont appliquées automatiquement lors de l'envoi du devis dans SAP.
      </p>
    </div>
  );
}
