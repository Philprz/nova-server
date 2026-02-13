// Pre-SAP Business One Normalizer
// Transforms extracted data into SAP B1 compatible JSON format

import { ExtractionResult } from './dataExtractor';
import { DetectionResult } from './quoteDetector';
import { EmailAnalysisResult } from './graphApi';

export interface SapBusinessPartner {
  CardCode: string | null;
  CardName: string;
  ContactEmail: string;
  ToBeCreated: boolean;
}

export interface SapDocumentLine {
  LineNum: number;
  ItemCode: string | null;
  ItemDescription: string;
  Quantity: number;
  UnitOfMeasure: string | null;
  RequestedDeliveryDate: string | null;
  ToBeCreated: boolean;
  SourceType: 'email' | 'pdf';
}

export interface SapDocumentMeta {
  source: 'office365';
  emailId: string;
  receivedDate: string;
  confidenceLevel: 'high' | 'medium' | 'low';
  manualValidationRequired: boolean;
  detectionRules: string[];
  sourceConflicts: string[];
  validationStatus: 'pending' | 'validated' | 'rejected';
  validatedAt: string | null;
  validatedBy: string | null;
}

export interface PreSapDocument {
  sapDocumentType: 'SalesQuotation';
  businessPartner: SapBusinessPartner;
  documentLines: SapDocumentLine[];
  requestedDeliveryDate: string | null;
  deliveryLeadTimeDays: number | null;
  meta: SapDocumentMeta;
}

function calculateDeliveryDate(leadTimeDays: number | null): string | null {
  if (!leadTimeDays) return null;
  
  const date = new Date();
  date.setDate(date.getDate() + leadTimeDays);
  return date.toISOString().split('T')[0]; // YYYY-MM-DD format
}

export function normalizeToPreSap(
  emailId: string,
  receivedDate: string,
  extraction: ExtractionResult,
  detection: DetectionResult
): PreSapDocument {
  // Normalize business partner
  const businessPartner: SapBusinessPartner = {
    CardCode: null, // Unknown - to be matched in SAP
    CardName: extraction.client.name,
    ContactEmail: extraction.client.email,
    ToBeCreated: true, // Assume new until validated
  };
  
  // Calculate delivery date
  const deliveryDate = calculateDeliveryDate(extraction.delivery?.estimatedDays || null);
  
  // Normalize document lines
  const documentLines: SapDocumentLine[] = extraction.articles.map((article, index) => ({
    LineNum: index + 1,
    ItemCode: null, // Unknown - to be matched in SAP
    ItemDescription: article.designation,
    Quantity: article.quantity || 1,
    UnitOfMeasure: article.unit || 'pcs',
    RequestedDeliveryDate: deliveryDate,
    ToBeCreated: true, // Assume new until validated
    SourceType: article.source,
  }));
  
  // Build meta information
  const meta: SapDocumentMeta = {
    source: 'office365',
    emailId,
    receivedDate,
    confidenceLevel: detection.confidence,
    manualValidationRequired: true,
    detectionRules: detection.matchedRules,
    sourceConflicts: extraction.sourceConflicts,
    validationStatus: 'pending',
    validatedAt: null,
    validatedBy: null,
  };
  
  return {
    sapDocumentType: 'SalesQuotation',
    businessPartner,
    documentLines,
    requestedDeliveryDate: deliveryDate,
    deliveryLeadTimeDays: extraction.delivery?.estimatedDays || null,
    meta,
  };
}

export function validateDocument(
  document: PreSapDocument,
  validatedBy: string = 'user'
): PreSapDocument {
  return {
    ...document,
    meta: {
      ...document.meta,
      validationStatus: 'validated',
      validatedAt: new Date().toISOString(),
      validatedBy,
      manualValidationRequired: false,
    },
  };
}

export function rejectDocument(
  document: PreSapDocument,
  rejectedBy: string = 'user'
): PreSapDocument {
  return {
    ...document,
    meta: {
      ...document.meta,
      validationStatus: 'rejected',
      validatedAt: new Date().toISOString(),
      validatedBy: rejectedBy,
    },
  };
}

export function exportToJson(document: PreSapDocument): string {
  // Convert to SAP-friendly format for export
  const sapFormat = {
    sap_document_type: document.sapDocumentType,
    business_partner: {
      CardCode: document.businessPartner.CardCode,
      CardName: document.businessPartner.CardName,
      ToBeCreated: document.businessPartner.ToBeCreated,
    },
    document_lines: document.documentLines.map(line => ({
      ItemCode: line.ItemCode,
      ItemDescription: line.ItemDescription,
      Quantity: line.Quantity,
      RequestedDeliveryDate: line.RequestedDeliveryDate,
      ToBeCreated: line.ToBeCreated,
    })),
    meta: {
      source: document.meta.source,
      confidence_level: document.meta.confidenceLevel,
      manual_validation_required: document.meta.manualValidationRequired,
      validated: document.meta.validationStatus === 'validated',
    },
  };
  
  return JSON.stringify(sapFormat, null, 2);
}

/**
 * Nouvelle fonction utilisant les données du backend (avec matching SAP amélioré)
 * Utilise client_matches et product_matches au lieu de l'extraction locale
 */
export function normalizeFromBackendAnalysis(
  emailId: string,
  receivedDate: string,
  analysis: EmailAnalysisResult
): PreSapDocument {
  // Utiliser le meilleur client matché par le backend
  const bestClient = analysis.client_matches?.[0]; // Le premier est le meilleur (score le plus élevé)

  const businessPartner: SapBusinessPartner = {
    CardCode: bestClient?.card_code || analysis.extracted_data?.client_card_code || null,
    CardName: bestClient?.card_name || analysis.extracted_data?.client_name || 'Unknown',
    ContactEmail: bestClient?.email_address || analysis.extracted_data?.client_email || '',
    ToBeCreated: !bestClient?.card_code, // Créer seulement si pas de CardCode
  };

  // Utiliser les produits matchés par le backend (déjà filtrés, sans faux positifs)
  const documentLines: SapDocumentLine[] = (analysis.product_matches || []).map((product, index) => ({
    LineNum: index + 1,
    ItemCode: product.item_code,
    ItemDescription: product.item_name || product.item_code,
    Quantity: product.quantity || 1,
    UnitOfMeasure: 'pcs',
    RequestedDeliveryDate: null,
    ToBeCreated: product.score < 100, // Créer si pas de match exact
    SourceType: 'email',
  }));

  // Build meta information
  const meta: SapDocumentMeta = {
    source: 'office365',
    emailId,
    receivedDate,
    confidenceLevel: analysis.confidence,
    manualValidationRequired: analysis.requires_user_choice || !analysis.client_auto_validated || !analysis.products_auto_validated || false,
    detectionRules: [analysis.reasoning],
    sourceConflicts: analysis.user_choice_reason ? [analysis.user_choice_reason] : [],
    validationStatus: 'pending',
    validatedAt: null,
    validatedBy: null,
  };

  return {
    sapDocumentType: 'SalesQuotation',
    businessPartner,
    documentLines,
    requestedDeliveryDate: null,
    deliveryLeadTimeDays: null,
    meta,
  };
}
