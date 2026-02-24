// API Client pour Microsoft Graph (via backend NOVA-SERVER)

const GRAPH_API_BASE = '/api/graph';

// Types pour les emails Graph
export interface GraphEmailAddress {
  name: string;
  address: string;
}

export interface GraphAttachment {
  id: string;
  name: string;
  content_type: string;
  size: number;
  content_bytes?: string;
}

export interface GraphEmail {
  id: string;
  subject: string;
  from_name: string;
  from_address: string;
  received_datetime: string;
  body_preview: string;
  body_content?: string;
  body_content_type?: string;
  has_attachments: boolean;
  is_read: boolean;
  attachments: GraphAttachment[];
  /** Détection côté serveur : true si le sujet contient "chiffrage", "devis", etc. */
  is_quote_by_subject?: boolean;
}

export interface GraphEmailsResponse {
  emails: GraphEmail[];
  total_count: number;
  next_link?: string;
}

// Types pour l'analyse
export interface ExtractedProduct {
  description: string;
  quantity?: number;
  unit?: string;
  reference?: string;
}

export interface ExtractedQuoteData {
  client_name?: string;
  client_email?: string;
  client_card_code?: string; // CardCode SAP si matché
  products: ExtractedProduct[];
  delivery_requirement?: string;
  urgency: string;
  notes?: string;
}

// Types pour le matching SAP (backend)
export interface ClientMatch {
  card_code: string;
  card_name: string;
  email_address?: string;
  score: number;
  match_reason: string;
}

export interface ProductMatch {
  // Champs existants
  item_code: string;
  item_name?: string;
  quantity: number;
  score: number;
  match_reason: string;
  not_found_in_sap?: boolean;

  // ✨ Nouveaux champs pricing (Phase 5 - Automatisation complète)
  unit_price?: number;
  line_total?: number;
  pricing_case?: 'CAS_1_HC' | 'CAS_2_HCM' | 'CAS_3_HA' | 'CAS_4_NP' | 'SAP_FUNCTION';
  pricing_justification?: string;
  requires_validation?: boolean;
  validation_reason?: string;
  supplier_price?: number;
  margin_applied?: number;
  confidence_score?: number;
  alerts?: string[];
}

export interface EmailAnalysisResult {
  classification: 'QUOTE_REQUEST' | 'INFORMATION' | 'OTHER';
  confidence: 'high' | 'medium' | 'low';
  is_quote_request: boolean;
  reasoning: string;
  extracted_data?: ExtractedQuoteData;
  quick_filter_passed: boolean;
  // Nouveaux champs du backend (matching SAP amélioré)
  client_matches?: ClientMatch[];
  product_matches?: ProductMatch[];
  client_auto_validated?: boolean;
  products_auto_validated?: boolean;
  requires_user_choice?: boolean;
  user_choice_reason?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// Test de connexion Graph
export async function testGraphConnection(): Promise<{
  success: boolean;
  step: string;
  details: {
    tenantId: boolean;
    clientId: boolean;
    clientSecret: boolean;
    mailboxAddress: boolean;
    tokenAcquired: boolean;
    mailboxAccessible: boolean;
  };
  error?: string;
  mailboxInfo?: {
    displayName: string;
    mail: string;
  };
}> {
  try {
    const response = await fetch(`${GRAPH_API_BASE}/test-connection`);
    return await response.json();
  } catch (error) {
    return {
      success: false,
      step: 'network_error',
      details: {
        tenantId: false,
        clientId: false,
        clientSecret: false,
        mailboxAddress: false,
        tokenAcquired: false,
        mailboxAccessible: false,
      },
      error: `Erreur réseau: ${error}`,
    };
  }
}

// Récupérer les emails
export async function fetchGraphEmails(options?: {
  top?: number;
  skip?: number;
  unreadOnly?: boolean;
}): Promise<ApiResponse<GraphEmailsResponse>> {
  try {
    const params = new URLSearchParams();
    if (options?.top) params.append('top', options.top.toString());
    if (options?.skip) params.append('skip', options.skip.toString());
    if (options?.unreadOnly) params.append('unread_only', 'true');

    const response = await fetch(`${GRAPH_API_BASE}/emails?${params}`);

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Récupérer un email complet
export async function fetchGraphEmail(messageId: string): Promise<ApiResponse<GraphEmail>> {
  try {
    const response = await fetch(`${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}`);

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Récupérer les pièces jointes d'un email
export async function fetchGraphAttachments(
  messageId: string
): Promise<ApiResponse<GraphAttachment[]>> {
  try {
    const response = await fetch(
      `${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}/attachments`
    );

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Récupérer le contenu d'une pièce jointe
export async function fetchAttachmentContent(
  messageId: string,
  attachmentId: string
): Promise<ApiResponse<{ content_base64: string; content_type: string; filename: string; size: number }>> {
  try {
    const response = await fetch(
      `${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentId)}/content`
    );

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Analyser un email (avec LLM)
export async function analyzeGraphEmail(
  messageId: string,
  force: boolean = false
): Promise<ApiResponse<EmailAnalysisResult>> {
  try {
    const params = force ? '?force=true' : '';
    const response = await fetch(
      `${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}/analyze${params}`,
      { method: 'POST' }
    );

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Récupérer le résultat d'analyse en cache
export async function getGraphEmailAnalysis(
  messageId: string
): Promise<ApiResponse<EmailAnalysisResult | null>> {
  try {
    const response = await fetch(
      `${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}/analysis`
    );

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Marquer un email comme lu
export async function markGraphEmailAsRead(messageId: string): Promise<ApiResponse<boolean>> {
  try {
    const response = await fetch(
      `${GRAPH_API_BASE}/emails/${encodeURIComponent(messageId)}/mark-read`,
      { method: 'POST' }
    );

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || `Erreur ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data: data.success };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Convertir un GraphEmail en EmailMessage (pour compatibilité avec les types existants)
export function graphEmailToEmailMessage(graphEmail: GraphEmail): import('@/types/email').EmailMessage {
  return {
    id: graphEmail.id,
    subject: graphEmail.subject,
    from: {
      emailAddress: {
        name: graphEmail.from_name,
        address: graphEmail.from_address,
      },
    },
    receivedDateTime: graphEmail.received_datetime,
    bodyPreview: graphEmail.body_preview,
    body: {
      contentType: graphEmail.body_content_type || 'text',
      content: graphEmail.body_content || graphEmail.body_preview,
    },
    hasAttachments: graphEmail.has_attachments,
    isRead: graphEmail.is_read,
    attachments: graphEmail.attachments.map((att) => ({
      id: att.id,
      name: att.name,
      contentType: att.content_type,
      size: att.size,
      contentBytes: att.content_bytes,
    })),
  };
}

// ============================================
// ✨ PRICING API - Modification de prix
// ============================================

export interface PriceUpdateRequest {
  decision_id: string;
  new_price: number;
  modification_reason?: string;
  modified_by?: string;
}

export interface PriceUpdateResult {
  success: boolean;
  decision_id: string;
  old_price: number;
  new_price: number;
  margin_applied: number;
  message: string;
}

/**
 * Met à jour le prix d'une décision pricing
 */
export async function updateDecisionPrice(
  decisionId: string,
  newPrice: number,
  reason?: string,
  modifiedBy?: string
): Promise<PriceUpdateResult> {
  const response = await fetch(`/api/validations/decisions/${decisionId}/update-price`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision_id: decisionId,
      new_price: newPrice,
      modification_reason: reason,
      modified_by: modifiedBy,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(error.detail || `Erreur HTTP ${response.status}`);
  }

  return response.json();
}

export interface RecalculatePricingResult {
  success: boolean;
  pricing_calculated: number;
  total_products: number;
  duration_ms: number;
  errors?: string[];
  analysis: EmailAnalysisResult;
}

/**
 * Recalcule les prix pour un email déjà analysé
 * Utile pour les emails analysés avant l'implémentation de la Phase 5
 */
export async function recalculatePricing(emailId: string): Promise<RecalculatePricingResult> {
  const response = await fetch(`${GRAPH_API_BASE}/emails/${emailId}/recalculate-pricing`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(error.detail || `Erreur HTTP ${response.status}`);
  }

  return response.json();
}

// ============================================================
// PIÈCES JOINTES STOCKÉES LOCALEMENT
// ============================================================

export interface StoredAttachment {
  id: number;
  email_id: string;
  attachment_id: string;
  filename: string;
  content_type: string;
  size: number;
  local_path: string;
  downloaded_at: string;
  is_previewable: boolean;
}

export interface StoredAttachmentsResponse {
  email_id: string;
  count: number;
  attachments: StoredAttachment[];
  already_stored?: boolean;
}

/** Liste les PJ stockées localement pour un email. */
export async function fetchStoredAttachments(
  emailId: string
): Promise<StoredAttachmentsResponse> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/stored-attachments?email_id=${encodeURIComponent(emailId)}`
  );
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

/** Déclenche le stockage des PJ si pas encore fait (idempotent). */
export async function triggerAttachmentStorage(
  emailId: string
): Promise<StoredAttachmentsResponse> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/store-attachments?email_id=${encodeURIComponent(emailId)}`,
    { method: 'POST' }
  );
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

/** URL pour servir une PJ depuis le stockage local (utilisable en href ou iframe src). */
export function getStoredAttachmentUrl(emailId: string, attachmentId: string, download = false): string {
  const base = `${GRAPH_API_BASE}/emails/stored-attachments/serve?email_id=${encodeURIComponent(emailId)}&attachment_id=${encodeURIComponent(attachmentId)}`;
  return download ? `${base}&download=true` : base;
}

// ============================================================
// CORRECTIONS MANUELLES
// ============================================================

export interface QuoteCorrection {
  id?: number;
  email_id: string;
  field_type: 'client' | 'product' | 'delivery' | 'general';
  field_index?: number | null;
  field_name: string;
  original_value?: string | null;
  corrected_value: string;
  corrected_at?: string;
  corrected_by?: string;
}

export interface CorrectionsResponse {
  email_id: string;
  count: number;
  corrections: QuoteCorrection[];
}

/** Récupère les corrections manuelles pour un email. */
export async function fetchCorrections(emailId: string): Promise<CorrectionsResponse> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/corrections?email_id=${encodeURIComponent(emailId)}`
  );
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

/** Sauvegarde des corrections (lot). */
export async function saveCorrections(
  emailId: string,
  corrections: Omit<QuoteCorrection, 'id' | 'email_id' | 'corrected_at'>[]
): Promise<CorrectionsResponse> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/corrections?email_id=${encodeURIComponent(emailId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corrections }),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(err.detail || `Erreur ${response.status}`);
  }
  return response.json();
}

// ============================================================
// ACTIONS PRODUITS (articles non trouvés SAP)
// ============================================================

export interface ExcludeProductResult {
  status: string;
  message: string;
  email_id: string;
  item_code: string;
  reason?: string;
  excluded_at: string;
}

export interface ManualCodeResult {
  status: string;
  message: string;
  email_id: string;
  original_code: string;
  item_code: string;
  item_name: string;
  not_found_in_sap: boolean;
}

export interface RetrySearchItem {
  item_code: string;
  item_name: string;
  quantity_on_hand?: number;
}

export interface RetrySearchResult {
  email_id: string;
  original_code: string;
  search_query: string;
  items: RetrySearchItem[];
  count: number;
}

/** Exclut un article du devis (Option C - Ignorer). */
export async function excludeProduct(
  emailId: string,
  itemCode: string,
  reason?: string
): Promise<ExcludeProductResult> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/${encodeURIComponent(emailId)}/products/${encodeURIComponent(itemCode)}/exclude`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(err.detail || `Erreur ${response.status}`);
  }
  return response.json();
}

/** Associe un code SAP saisi manuellement à un article non trouvé (Option A). */
export async function setManualCode(
  emailId: string,
  itemCode: string,
  rondotCode: string
): Promise<ManualCodeResult> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/${encodeURIComponent(emailId)}/products/${encodeURIComponent(itemCode)}/manual-code`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rondot_code: rondotCode }),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(err.detail || `Erreur ${response.status}`);
  }
  return response.json();
}

/** Relance la recherche SAP pour un article non trouvé (Option B). */
export async function retrySearchProduct(
  emailId: string,
  itemCode: string,
  searchQuery?: string
): Promise<RetrySearchResult> {
  const response = await fetch(
    `${GRAPH_API_BASE}/emails/${encodeURIComponent(emailId)}/products/${encodeURIComponent(itemCode)}/retry-search`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ search_query: searchQuery }),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(err.detail || `Erreur ${response.status}`);
  }
  return response.json();
}
