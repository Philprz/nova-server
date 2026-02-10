// Supplier File Extractor Module
// Extracts product data from supplier files (PDF/Excel) attached to emails

import { getMockPdfContent } from './pdfParser';

export interface SupplierFileInfo {
  filename: string;
  type: 'excel' | 'pdf';
}

export interface ExtractedProductData {
  supplier_reference: string | null;
  designation: string | null;
  unit_price: number | null;
  currency: string | null;
  delivery_time: string | null;
  supplier_name: string | null;
}

export interface SupplierExtractionResult {
  product_found_in_sap: false;
  supplier_files_used: SupplierFileInfo[];
  extracted_product_data: ExtractedProductData | null;
  missing_fields: string[];
  extraction_notes?: string;
}

// Single file extraction result (user-selected file)
export interface SingleFileExtractionResult {
  product_found_in_sap: false;
  supplier_file: SupplierFileInfo;
  extracted_product_data: ExtractedProductData | null;
  missing_fields: string[];
  extraction_notes?: string;
}

// Patterns for extracting supplier data
const PATTERNS = {
  // Reference patterns: REF-XXX, REF:XXX, Référence: XXX, Code: XXX
  reference: [
    /(?:ref|référence|reference|code|art\.?|article)\s*[:\-]?\s*([A-Z0-9\-]+)/gi,
    /^([A-Z]{2,4}[\-][0-9]{2,4})/gm,
  ],
  // Price patterns: 12.50 €, €12.50, 12,50 EUR, USD 12.50
  price: [
    /(\d+[.,]\d{2})\s*(?:€|EUR|USD|\$)/gi,
    /(?:€|EUR|USD|\$)\s*(\d+[.,]\d{2})/gi,
    /(?:prix|price|p\.u\.?|unit price)\s*[:\-]?\s*(\d+[.,]\d{2})/gi,
  ],
  // Currency patterns
  currency: [
    /(EUR|USD|€|\$)/gi,
  ],
  // Delivery time patterns
  deliveryTime: [
    /(?:délai|delivery|lead\s*time|livraison)\s*[:\-]?\s*(\d+)\s*(jours?|semaines?|weeks?|days?)/gi,
    /(\d+)\s*(jours?|semaines?|weeks?|days?)\s*(?:délai|delivery|livraison)/gi,
  ],
  // Supplier name patterns
  supplier: [
    /(?:fournisseur|supplier|from|de)\s*[:\-]?\s*([A-Za-z0-9\s]+(?:Ltd|GmbH|SAS|SARL|Inc|Corp)?)/gi,
  ],
};

function extractReference(text: string): string | null {
  for (const pattern of PATTERNS.reference) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    if (match && match[1]) {
      return match[1].trim().toUpperCase();
    }
  }
  return null;
}

function extractPrice(text: string): number | null {
  for (const pattern of PATTERNS.price) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    if (match && match[1]) {
      const priceStr = match[1].replace(',', '.');
      const price = parseFloat(priceStr);
      if (!isNaN(price)) {
        return price;
      }
    }
  }
  return null;
}

function extractCurrency(text: string): string | null {
  for (const pattern of PATTERNS.currency) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    if (match && match[1]) {
      const curr = match[1].toUpperCase();
      if (curr === '€') return 'EUR';
      if (curr === '$') return 'USD';
      return curr;
    }
  }
  return null;
}

function extractDeliveryTime(text: string): string | null {
  for (const pattern of PATTERNS.deliveryTime) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    if (match) {
      const value = match[1];
      const unit = match[2].toLowerCase();
      
      // Normalize to French
      let normalizedUnit = unit;
      if (unit.includes('week') || unit.includes('semaine')) {
        normalizedUnit = 'semaines';
      } else if (unit.includes('day') || unit.includes('jour')) {
        normalizedUnit = 'jours';
      }
      
      return `${value} ${normalizedUnit}`;
    }
  }
  return null;
}

function extractSupplierName(text: string): string | null {
  for (const pattern of PATTERNS.supplier) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    if (match && match[1]) {
      return match[1].trim();
    }
  }
  return null;
}

function extractDesignation(text: string, reference: string | null): string | null {
  // Try to find product description near the reference
  const lines = text.split('\n');
  
  for (const line of lines) {
    const trimmed = line.trim();
    
    // Skip empty lines or very short lines
    if (trimmed.length < 5) continue;
    
    // If we have a reference, look for lines containing it
    if (reference && trimmed.toUpperCase().includes(reference)) {
      // Extract description part (usually after reference)
      const parts = trimmed.split(/[\|\t\-]/);
      if (parts.length > 1) {
        return parts[1].trim();
      }
    }
    
    // Look for description patterns
    if (/description|désignation|produit|article/i.test(trimmed)) {
      const match = trimmed.match(/(?:description|désignation|produit|article)\s*[:\-]?\s*(.+)/i);
      if (match && match[1]) {
        return match[1].trim();
      }
    }
  }
  
  return null;
}

function extractProductDataFromText(text: string): ExtractedProductData {
  const reference = extractReference(text);
  
  return {
    supplier_reference: reference,
    designation: extractDesignation(text, reference),
    unit_price: extractPrice(text),
    currency: extractCurrency(text),
    delivery_time: extractDeliveryTime(text),
    supplier_name: extractSupplierName(text),
  };
}

function getMissingFields(data: ExtractedProductData): string[] {
  const missing: string[] = [];
  
  if (!data.supplier_reference) missing.push('supplier_reference');
  if (!data.designation) missing.push('designation');
  if (!data.unit_price) missing.push('unit_price');
  if (!data.currency) missing.push('currency');
  if (!data.delivery_time) missing.push('delivery_time');
  if (!data.supplier_name) missing.push('supplier_name');
  
  return missing;
}

function mergeProductData(
  existing: ExtractedProductData | null,
  newData: ExtractedProductData
): ExtractedProductData {
  if (!existing) return newData;
  
  return {
    supplier_reference: existing.supplier_reference ?? newData.supplier_reference,
    designation: existing.designation ?? newData.designation,
    unit_price: existing.unit_price ?? newData.unit_price,
    currency: existing.currency ?? newData.currency,
    delivery_time: existing.delivery_time ?? newData.delivery_time,
    supplier_name: existing.supplier_name ?? newData.supplier_name,
  };
}

export interface EmailAttachment {
  id: string;
  name: string;
  contentType: string;
  size: number;
  contentBytes?: string;
}

export function extractFromSupplierFiles(
  attachments: EmailAttachment[]
): SupplierExtractionResult {
  const supplierFiles: SupplierFileInfo[] = [];
  let extractedData: ExtractedProductData | null = null;
  
  // Filter for PDF and Excel files
  const relevantFiles = attachments.filter(att => {
    const name = att.name.toLowerCase();
    const type = att.contentType.toLowerCase();
    
    return (
      type === 'application/pdf' ||
      name.endsWith('.pdf') ||
      type.includes('excel') ||
      type.includes('spreadsheet') ||
      name.endsWith('.xlsx') ||
      name.endsWith('.xls')
    );
  });
  
  if (relevantFiles.length === 0) {
    return {
      product_found_in_sap: false,
      supplier_files_used: [],
      extracted_product_data: null,
      missing_fields: [
        'supplier_reference',
        'designation',
        'unit_price',
        'currency',
        'delivery_time',
        'supplier_name',
      ],
      extraction_notes: 'Aucun fichier fournisseur exploitable trouvé (PDF ou Excel).',
    };
  }
  
  // Process each file
  for (const file of relevantFiles) {
    const isPdf = file.contentType === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    const isExcel = file.name.toLowerCase().endsWith('.xlsx') || 
                    file.name.toLowerCase().endsWith('.xls') ||
                    file.contentType.includes('excel') ||
                    file.contentType.includes('spreadsheet');
    
    supplierFiles.push({
      filename: file.name,
      type: isPdf ? 'pdf' : 'excel',
    });
    
    // Extract text content
    let textContent = '';
    
    if (isPdf) {
      // Use mock PDF content for demo
      const parsed = getMockPdfContent(file.name);
      if (parsed.parseSuccess) {
        textContent = parsed.textContent;
      }
    } else if (isExcel) {
      // Mock Excel extraction (in production, would use xlsx library)
      textContent = getMockExcelContent(file.name);
    }
    
    if (textContent) {
      const fileData = extractProductDataFromText(textContent);
      extractedData = mergeProductData(extractedData, fileData);
    }
  }
  
  const missingFields = extractedData ? getMissingFields(extractedData) : [
    'supplier_reference',
    'designation',
    'unit_price',
    'currency',
    'delivery_time',
    'supplier_name',
  ];
  
  return {
    product_found_in_sap: false,
    supplier_files_used: supplierFiles,
    extracted_product_data: extractedData,
    missing_fields: missingFields,
  };
}

// Extract from a single user-selected file
export function extractFromSingleFile(
  attachment: EmailAttachment
): SingleFileExtractionResult {
  const isPdf = attachment.contentType === 'application/pdf' || 
                attachment.name.toLowerCase().endsWith('.pdf');
  const isExcel = attachment.name.toLowerCase().endsWith('.xlsx') || 
                  attachment.name.toLowerCase().endsWith('.xls') ||
                  attachment.contentType.includes('excel') ||
                  attachment.contentType.includes('spreadsheet');
  
  if (!isPdf && !isExcel) {
    return {
      product_found_in_sap: false,
      supplier_file: {
        filename: attachment.name,
        type: isPdf ? 'pdf' : 'excel',
      },
      extracted_product_data: null,
      missing_fields: [
        'supplier_reference',
        'designation',
        'unit_price',
        'currency',
        'delivery_time',
        'supplier_name',
      ],
      extraction_notes: 'Format de fichier non supporté. Seuls les fichiers PDF et Excel sont acceptés.',
    };
  }
  
  const fileType: 'pdf' | 'excel' = isPdf ? 'pdf' : 'excel';
  let textContent = '';
  
  if (isPdf) {
    const parsed = getMockPdfContent(attachment.name);
    if (parsed.parseSuccess) {
      textContent = parsed.textContent;
    }
  } else if (isExcel) {
    textContent = getMockExcelContent(attachment.name);
  }
  
  if (!textContent) {
    return {
      product_found_in_sap: false,
      supplier_file: {
        filename: attachment.name,
        type: fileType,
      },
      extracted_product_data: null,
      missing_fields: [
        'supplier_reference',
        'designation',
        'unit_price',
        'currency',
        'delivery_time',
        'supplier_name',
      ],
      extraction_notes: 'Impossible de lire le contenu du fichier.',
    };
  }
  
  const extractedData = extractProductDataFromText(textContent);
  const missingFields = getMissingFields(extractedData);
  
  return {
    product_found_in_sap: false,
    supplier_file: {
      filename: attachment.name,
      type: fileType,
    },
    extracted_product_data: extractedData,
    missing_fields: missingFields,
  };
}

// Mock Excel content for demo purposes
function getMockExcelContent(filename: string): string {
  const mockContents: Record<string, string> = {
    'product_catalog.xlsx': `
Catalogue Fournisseur TechParts GmbH

REF | Description | Prix | Devise | Délai
TEC-001 | Moteur Servo 2kW | 450.00 | EUR | 3 semaines
TEC-002 | Capteur Pression | 125.50 | EUR | 2 semaines
TEC-003 | Module Controller | 890.00 | EUR | 4 semaines

Conditions: Franco usine
    `,
    'price_list.xlsx': `
Liste de Prix - Supplier ABC

Code Article: ABC-500
Désignation: Pompe Hydraulique HD
Prix Unitaire: 1250.00 EUR
Délai livraison: 6 semaines
Fournisseur: ABC Industrial Supply
    `,
    default: `
Référence: GEN-100
Produit: Article Standard
Prix: 100.00 EUR
Délai: 2 semaines
    `,
  };
  
  return mockContents[filename] || mockContents.default;
}
