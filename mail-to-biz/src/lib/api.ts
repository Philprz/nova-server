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
  ItemCode: string;
  Quantity: number;
  UnitPrice?: number;
}

export interface CreateQuoteRequest {
  CardCode: string;
  DocDate?: string;
  DocDueDate?: string;
  Comments?: string;
  DocumentLines: CreateQuoteLine[];
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

// Créer un devis SAP
export async function createSAPQuotation(request: CreateQuoteRequest): Promise<ApiResponse<{
  DocEntry: number;
  DocNum: string;
  CardCode: string;
  DocTotal: number;
}>> {
  try {
    const response = await fetch(`${API_BASE}/quotations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    const data = await response.json();

    return {
      success: data.success,
      data: data.quotation,
      error: data.error,
    };
  } catch (error) {
    return { success: false, error: `Erreur: ${error}` };
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
