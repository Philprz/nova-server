// API Service pour mail-to-biz
// Appels vers le backend NOVA-SERVER

const API_BASE = '/api/sap-rondot';

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface SAPClient {
  CardCode: string;
  CardName: string;
  CardType?: string;
  Phone1?: string;
  EmailAddress?: string;
  City?: string;
  Country?: string;
}

export interface SAPProduct {
  ItemCode: string;
  ItemName: string;
  ItemType?: string;
  QuantityOnStock?: number;
  Price?: number;
}

export interface SAPQuotation {
  DocEntry: number;
  DocNum: string;
  CardCode: string;
  CardName: string;
  DocDate: string;
  DocTotal: number;
  DocStatus: string;
}

export interface CreateQuoteLine {
  ItemCode?: string;
  ItemDescription: string;
  Quantity: number;
  UnitPrice?: number;
  DiscountPercent?: number;
}

export interface CreateQuoteRequest {
  CardCode: string;
  DocDate?: string;
  DocDueDate?: string;
  Comments?: string;
  NumAtCard?: string;
  email_id?: string;
  email_subject?: string;
  DocumentLines: CreateQuoteLine[];
}

export interface PreviewResponse {
  validation_status: string;
  client: { CardCode: string };
  lines: CreateQuoteLine[];
  totals: { subtotal: number; lines_count: number };
  currency: string;
  sap_payload: Record<string, unknown>;
}

// Test de connexion SAP
export async function testSAPConnection(): Promise<{ success: boolean; message: string }> {
  try {
    const response = await fetch(`${API_BASE}/test-connection`);
    return await response.json();
  } catch (error) {
    return { success: false, message: `Erreur: ${error}` };
  }
}

// Récupérer les clients SAP
export async function getSAPClients(search?: string, limit = 50): Promise<ApiResponse<SAPClient[]>> {
  try {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    params.append('limit', limit.toString());

    const response = await fetch(`${API_BASE}/clients?${params}`);
    const data = await response.json();

    return {
      success: data.success,
      data: data.clients,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Récupérer un client par code
export async function getSAPClient(cardCode: string): Promise<ApiResponse<SAPClient>> {
  try {
    const response = await fetch(`${API_BASE}/clients/${encodeURIComponent(cardCode)}`);
    const data = await response.json();

    return {
      success: data.success,
      data: data.client,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Récupérer les produits SAP
export async function getSAPProducts(search?: string, limit = 50): Promise<ApiResponse<SAPProduct[]>> {
  try {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    params.append('limit', limit.toString());

    const response = await fetch(`${API_BASE}/products?${params}`);
    const data = await response.json();

    return {
      success: data.success,
      data: data.products,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Récupérer un produit par code
export async function getSAPProduct(itemCode: string): Promise<ApiResponse<SAPProduct>> {
  try {
    const response = await fetch(`${API_BASE}/products/${encodeURIComponent(itemCode)}`);
    const data = await response.json();

    return {
      success: data.success,
      data: data.product,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Récupérer le prix d'un produit
export async function getSAPProductPrice(itemCode: string, cardCode?: string): Promise<ApiResponse<{
  item_code: string;
  base_prices: any[];
  client_price?: number;
}>> {
  try {
    const params = new URLSearchParams();
    if (cardCode) params.append('card_code', cardCode);

    const response = await fetch(`${API_BASE}/products/${encodeURIComponent(itemCode)}/price?${params}`);
    const data = await response.json();

    return {
      success: data.success,
      data: {
        item_code: data.item_code,
        base_prices: data.base_prices,
        client_price: data.client_price,
      },
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Récupérer les devis SAP
export async function getSAPQuotations(cardCode?: string, limit = 50): Promise<ApiResponse<SAPQuotation[]>> {
  try {
    const params = new URLSearchParams();
    if (cardCode) params.append('card_code', cardCode);
    params.append('limit', limit.toString());

    const response = await fetch(`${API_BASE}/quotations?${params}`);
    const data = await response.json();

    return {
      success: data.success,
      data: data.quotations,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
  }
}

// Prévisualiser un devis SAP (sans envoi à SAP)
export async function previewSAPQuotation(
  request: CreateQuoteRequest
): Promise<ApiResponse<PreviewResponse>> {
  try {
    const response = await fetch('/api/sap/quotation/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    const data = await response.json();
    if (!response.ok) {
      return { success: false, error: data.detail?.message || data.detail || 'Erreur preview' };
    }
    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Créer un devis SAP (endpoint production avec session management complet)
export async function createSAPQuotation(request: CreateQuoteRequest): Promise<ApiResponse<{
  doc_entry: number;
  doc_num: number;
  card_code: string;
  doc_total: number;
  message: string;
  retried: boolean;
  retry_reason?: string;
}>> {
  try {
    const response = await fetch('/api/sap/quotation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.detail?.message || data.detail || 'Erreur création SAP' };
    }

    return { success: true, data };
  } catch (error) {
    return { success: false, error: `Erreur réseau: ${error}` };
  }
}

// Devis SAP déjà créé pour cet email
export interface ExistingQuoteInfo {
  found: boolean;
  id?: number;
  client_code?: string;
  total_ht?: number;
  sap_doc_entry?: number;
  sap_doc_num?: number;
  status?: string;
  created_at?: string;
}

export async function getExistingQuoteForEmail(emailId: string): Promise<ExistingQuoteInfo> {
  try {
    const response = await fetch(`/api/sap/quotation/by-email/${encodeURIComponent(emailId)}`);
    if (!response.ok) return { found: false };
    return response.json();
  } catch {
    return { found: false };
  }
}

// Statut de connexion SAP
export async function getSAPStatus(): Promise<{
  connected: boolean;
  company_db: string;
  user: string;
  session_expires?: string;
}> {
  try {
    const response = await fetch(`${API_BASE}/status`);
    return await response.json();
  } catch (error) {
    return { connected: false, company_db: '', user: '' };
  }
}
