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

export interface EmailAnalysisResult {
  classification: 'QUOTE_REQUEST' | 'INFORMATION' | 'OTHER';
  confidence: 'high' | 'medium' | 'low';
  is_quote_request: boolean;
  reasoning: string;
  extracted_data?: ExtractedQuoteData;
  quick_filter_passed: boolean;
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
