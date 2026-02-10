// Quote Detection Module
// Deterministic rules-based detection for quote requests

export interface DetectionResult {
  isQuote: boolean;
  confidence: 'high' | 'medium' | 'low';
  matchedRules: string[];
  sources: ('subject' | 'body' | 'attachment')[];
}

// Keywords for subject detection
const SUBJECT_KEYWORDS = [
  'demande de devis',
  'quotation',
  'quote',
  'price request',
  'request for quotation',
  'rfq',
  'prix',
  'offre de prix',
  'devis',
];

// Phrases for body detection
const BODY_PHRASES = [
  'merci de nous faire un devis',
  'please quote',
  'we would like a quotation',
  'demande de prix',
  'veuillez nous communiquer',
  'could you quote',
  'request for price',
  'nous souhaitons recevoir une offre',
  'please provide a quote',
  'pouvez-vous nous faire une offre',
];

// Keywords for PDF attachment detection
const PDF_KEYWORDS = [
  'offer request',
  'quotation',
  'qty',
  'quantity',
  'demande de prix',
  'unit price',
  'prix unitaire',
  'référence',
  'reference',
  'article',
];

// Quantity pattern detection
const QUANTITY_PATTERNS = [
  /\b\d+\s*(pcs|pieces|pièces|units?|unités?|ea|each)\b/gi,
  /\bqt[ey]?\.?\s*:?\s*\d+/gi,
  /\b\d+\s*x\s*\w+/gi,
  /\bquantité\s*:?\s*\d+/gi,
];

function normalizeText(text: string): string {
  return text.toLowerCase().trim();
}

function detectInSubject(subject: string): boolean {
  const normalized = normalizeText(subject);
  return SUBJECT_KEYWORDS.some(keyword => normalized.includes(keyword));
}

function detectInBody(body: string): { detected: boolean; hasQuantities: boolean } {
  const normalized = normalizeText(body);
  
  const hasPhrases = BODY_PHRASES.some(phrase => normalized.includes(phrase));
  const hasQuantities = QUANTITY_PATTERNS.some(pattern => pattern.test(body));
  
  return {
    detected: hasPhrases,
    hasQuantities,
  };
}

function detectInPdfContent(pdfText: string): { detected: boolean; hasQuantities: boolean } {
  const normalized = normalizeText(pdfText);
  
  const hasKeywords = PDF_KEYWORDS.some(keyword => normalized.includes(keyword));
  const hasQuantities = QUANTITY_PATTERNS.some(pattern => pattern.test(pdfText));
  
  return {
    detected: hasKeywords,
    hasQuantities,
  };
}

export function detectQuoteRequest(
  subject: string,
  body: string,
  pdfContents: string[] = []
): DetectionResult {
  const matchedRules: string[] = [];
  const sources: ('subject' | 'body' | 'attachment')[] = [];
  
  // Check subject
  if (detectInSubject(subject)) {
    matchedRules.push('Subject contains quote-related keywords');
    sources.push('subject');
  }
  
  // Check body
  const bodyResult = detectInBody(body);
  if (bodyResult.detected) {
    matchedRules.push('Body contains quote request phrases');
    sources.push('body');
  }
  if (bodyResult.hasQuantities) {
    matchedRules.push('Body contains explicit quantities');
    if (!sources.includes('body')) sources.push('body');
  }
  
  // Check PDF contents
  for (const pdfText of pdfContents) {
    const pdfResult = detectInPdfContent(pdfText);
    if (pdfResult.detected || pdfResult.hasQuantities) {
      if (!sources.includes('attachment')) {
        sources.push('attachment');
      }
      if (pdfResult.detected) {
        matchedRules.push('PDF contains quote-related keywords');
      }
      if (pdfResult.hasQuantities) {
        matchedRules.push('PDF contains explicit quantities');
      }
    }
  }
  
  const isQuote = matchedRules.length > 0;
  
  // Determine confidence
  let confidence: 'high' | 'medium' | 'low' = 'low';
  if (matchedRules.length >= 3 || sources.includes('attachment')) {
    confidence = 'high';
  } else if (matchedRules.length >= 2) {
    confidence = 'medium';
  } else if (matchedRules.length === 1) {
    confidence = 'low';
  }
  
  return {
    isQuote,
    confidence,
    matchedRules,
    sources,
  };
}
