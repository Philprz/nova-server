// PDF Parser Module
// Extracts text content from PDF attachments (base64 encoded)
// Note: This is a simplified text extraction for demo purposes
// Real implementation would use a proper PDF library

export interface ParsedPdf {
  filename: string;
  textContent: string;
  pageCount: number;
  parseSuccess: boolean;
  errorMessage?: string;
}

// Simplified PDF text extraction from base64
// In production, this would use pdf.js or a server-side PDF library
export function parsePdfBase64(base64Content: string, filename: string): ParsedPdf {
  try {
    // Decode base64 to binary
    const binaryString = atob(base64Content);
    
    // Simple text extraction - looks for readable text patterns
    // This is a simplified approach; real PDF parsing needs a proper library
    let textContent = '';
    const streamMatches = binaryString.match(/stream[\s\S]*?endstream/g);
    
    if (streamMatches) {
      for (const stream of streamMatches) {
        // Try to extract readable ASCII text
        const cleaned = stream
          .replace(/stream|endstream/g, '')
          .replace(/[^\x20-\x7E\n\r]/g, ' ')
          .replace(/\s+/g, ' ')
          .trim();
        
        if (cleaned.length > 10) {
          textContent += cleaned + '\n';
        }
      }
    }
    
    // Also try to find text directly in the PDF
    const textMatches = binaryString.match(/\(([^)]+)\)/g);
    if (textMatches) {
      for (const match of textMatches) {
        const text = match.slice(1, -1);
        if (text.length > 2 && /[a-zA-Z0-9]/.test(text)) {
          textContent += text + ' ';
        }
      }
    }
    
    // Clean up the extracted text
    textContent = textContent
      .replace(/\s+/g, ' ')
      .replace(/\n\s*\n/g, '\n')
      .trim();
    
    return {
      filename,
      textContent: textContent || 'Unable to extract text from PDF',
      pageCount: (binaryString.match(/\/Type\s*\/Page[^s]/g) || []).length || 1,
      parseSuccess: textContent.length > 0,
    };
  } catch (error) {
    console.error('PDF parsing error:', error);
    return {
      filename,
      textContent: '',
      pageCount: 0,
      parseSuccess: false,
      errorMessage: error instanceof Error ? error.message : 'Unknown parsing error',
    };
  }
}

// Mock PDF content for demo mode
export function getMockPdfContent(filename: string): ParsedPdf {
  const mockContents: Record<string, string> = {
    'quotation_request.pdf': `
QUOTATION REQUEST

From: Acme Industries Ltd.
Date: 2026-01-20

Dear Supplier,

Please provide a quotation for the following items:

REF     | Description              | Qty  | Unit
--------|--------------------------|------|------
MCH-001 | Industrial Motor 5kW     | 10   | pcs
MCH-002 | Hydraulic Pump Type A    | 5    | pcs  
ELC-015 | Control Panel Assembly   | 3    | pcs
FAS-100 | Mounting Brackets Set    | 50   | sets

Delivery time required: 4 weeks

Please confirm availability and lead time.

Best regards,
John Smith
Purchasing Manager
    `,
    'rfq_urgent.pdf': `
REQUEST FOR QUOTATION - URGENT

Company: Global Manufacturing Corp.
Contact: Marie Dupont
Email: m.dupont@globalmfg.com

We request your best offer for:

1. Stainless Steel Plates (2mm) - Quantity: 100 pcs
2. Aluminum Profiles (Type B) - Quantity: 200 units
3. Rubber Gaskets Kit - Quantity: 25 kits

Délai de livraison souhaité: 2 semaines

Merci de nous faire un devis urgent.
    `,
    default: `
OFFER REQUEST

Items requested:
- Component A: 20 pieces
- Component B: 15 units
- Assembly Kit: 5 sets

Lead time: 3 weeks
    `,
  };
  
  const content = mockContents[filename] || mockContents.default;
  
  return {
    filename,
    textContent: content.trim(),
    pageCount: 1,
    parseSuccess: true,
  };
}
