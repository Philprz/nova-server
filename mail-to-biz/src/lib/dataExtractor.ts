// Data Extraction Module
// Extracts structured data from email body and PDF content

export interface ExtractedArticle {
  designation: string;
  quantity: number | null;
  unit: string | null;
  source: 'email' | 'pdf';
  lineNumber: number;
}

export interface ExtractedClient {
  name: string;
  email: string;
  source: 'explicit' | 'sender';
}

export interface ExtractedDelivery {
  rawText: string;
  estimatedDays: number | null;
  source: 'email' | 'pdf';
}

export interface ExtractionResult {
  client: ExtractedClient;
  articles: ExtractedArticle[];
  delivery: ExtractedDelivery | null;
  sourceConflicts: string[];
}

// Patterns for article line detection
const ARTICLE_PATTERNS = [
  // "10 pcs ProductName" or "10 x ProductName"
  /^[\s-]*(\d+)\s*(pcs?|pieces?|pièces?|units?|unités?|ea|x)\s+(.+)$/gmi,
  // "ProductName: 10" or "ProductName - qty 10"
  /^[\s-]*(.+?)\s*[-:]\s*(?:qt[ey]?\.?\s*)?(\d+)\s*(pcs?|pieces?|pièces?|units?|unités?)?$/gmi,
  // "ProductName (10 pcs)"
  /^[\s-]*(.+?)\s*\((\d+)\s*(pcs?|pieces?|pièces?|units?|unités?)?\)$/gmi,
  // Table-like: "REF001 | Product Name | 10 | pcs"
  /^[\s]*([A-Z0-9-]+)\s*[|,]\s*(.+?)\s*[|,]\s*(\d+)\s*[|,]?\s*(pcs?|pieces?|pièces?|units?|unités?)?$/gmi,
];

// Company name patterns
const COMPANY_PATTERNS = [
  /(?:company|société|entreprise|from|de la part de)\s*[:\s]+(.+)/i,
  /^(.+?)\s*(?:S\.?A\.?|SARL|SAS|EURL|GmbH|LLC|Inc\.?|Ltd\.?)$/mi,
];

// Delivery time patterns
const DELIVERY_PATTERNS = [
  /(?:delivery\s*(?:time)?|lead\s*time|délai(?:\s*de\s*livraison)?)\s*[:\s]*(\d+)\s*(weeks?|semaines?|days?|jours?)/gi,
  /(\d+)\s*(weeks?|semaines?|days?|jours?)\s*(?:delivery|délai)/gi,
  /dans\s*(\d+)\s*(semaines?|jours?)/gi,
  /within\s*(\d+)\s*(weeks?|days?)/gi,
];

function extractCompanyFromEmail(senderEmail: string): string {
  const domain = senderEmail.split('@')[1];
  if (!domain) return senderEmail;
  
  // Remove common email provider domains
  const commonProviders = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com'];
  if (commonProviders.includes(domain.toLowerCase())) {
    return senderEmail;
  }
  
  // Extract company name from domain
  const companyPart = domain.split('.')[0];
  return companyPart.charAt(0).toUpperCase() + companyPart.slice(1);
}

function extractArticlesFromText(text: string, source: 'email' | 'pdf'): ExtractedArticle[] {
  const articles: ExtractedArticle[] = [];
  const lines = text.split('\n');
  let lineNumber = 0;
  
  for (const line of lines) {
    lineNumber++;
    const trimmedLine = line.trim();
    if (!trimmedLine || trimmedLine.length < 3) continue;
    
    // Try each pattern
    for (const pattern of ARTICLE_PATTERNS) {
      pattern.lastIndex = 0;
      const match = pattern.exec(trimmedLine);
      
      if (match) {
        // Different patterns have different group orders
        let designation: string;
        let quantity: number | null = null;
        let unit: string | null = null;
        
        if (match[3] && !isNaN(Number(match[1]))) {
          // Pattern: "10 pcs ProductName"
          quantity = parseInt(match[1]);
          unit = match[2] || null;
          designation = match[3].trim();
        } else if (match[2] && !isNaN(Number(match[2]))) {
          // Pattern: "ProductName: 10" or "ProductName (10 pcs)"
          designation = match[1].trim();
          quantity = parseInt(match[2]);
          unit = match[3] || null;
        } else if (match[4]) {
          // Table pattern
          designation = `${match[1]} - ${match[2]}`.trim();
          quantity = parseInt(match[3]);
          unit = match[4] || null;
        } else {
          continue;
        }
        
        // Clean up designation
        designation = designation.replace(/^[-•*]\s*/, '').trim();
        
        if (designation.length >= 2) {
          articles.push({
            designation,
            quantity,
            unit: unit?.toLowerCase() || null,
            source,
            lineNumber,
          });
          break; // Found a match, move to next line
        }
      }
    }
  }
  
  return articles;
}

function extractDeliveryFromText(text: string, source: 'email' | 'pdf'): ExtractedDelivery | null {
  for (const pattern of DELIVERY_PATTERNS) {
    pattern.lastIndex = 0;
    const match = pattern.exec(text);
    
    if (match) {
      const value = parseInt(match[1]);
      const unit = match[2].toLowerCase();
      
      let estimatedDays = value;
      if (unit.includes('week') || unit.includes('semaine')) {
        estimatedDays = value * 7;
      }
      
      return {
        rawText: match[0],
        estimatedDays,
        source,
      };
    }
  }
  
  return null;
}

function extractClientFromText(body: string, senderEmail: string, senderName: string): ExtractedClient {
  // Try to find explicit company name in body
  for (const pattern of COMPANY_PATTERNS) {
    const match = pattern.exec(body);
    if (match && match[1]) {
      return {
        name: match[1].trim(),
        email: senderEmail,
        source: 'explicit',
      };
    }
  }
  
  // Fall back to sender info
  const name = senderName || extractCompanyFromEmail(senderEmail);
  return {
    name,
    email: senderEmail,
    source: 'sender',
  };
}

export function extractData(
  emailBody: string,
  senderEmail: string,
  senderName: string,
  pdfContents: string[] = []
): ExtractionResult {
  const sourceConflicts: string[] = [];
  
  // Extract client
  const allText = [emailBody, ...pdfContents].join('\n');
  const client = extractClientFromText(allText, senderEmail, senderName);
  
  // Extract articles from email
  const emailArticles = extractArticlesFromText(emailBody, 'email');
  
  // Extract articles from PDFs (priority)
  const pdfArticles: ExtractedArticle[] = [];
  for (const pdfContent of pdfContents) {
    pdfArticles.push(...extractArticlesFromText(pdfContent, 'pdf'));
  }
  
  // Merge articles - PDF takes priority
  let articles = pdfArticles.length > 0 ? pdfArticles : emailArticles;
  
  // Check for conflicts
  if (pdfArticles.length > 0 && emailArticles.length > 0) {
    sourceConflicts.push('Articles found in both email and PDF - using PDF data');
  }
  
  // Extract delivery
  let delivery = extractDeliveryFromText(emailBody, 'email');
  for (const pdfContent of pdfContents) {
    const pdfDelivery = extractDeliveryFromText(pdfContent, 'pdf');
    if (pdfDelivery) {
      if (delivery && delivery.source === 'email') {
        sourceConflicts.push('Delivery time found in both email and PDF - using PDF data');
      }
      delivery = pdfDelivery;
    }
  }
  
  return {
    client,
    articles,
    delivery,
    sourceConflicts,
  };
}
