// Email and Quote Processing Types

export interface EmailAttachment {
  id: string;
  name: string;
  contentType: string;
  size: number;
  contentBytes?: string;
}

export interface EmailMessage {
  id: string;
  subject: string;
  from: {
    emailAddress: {
      name: string;
      address: string;
    };
  };
  receivedDateTime: string;
  bodyPreview: string;
  body: {
    contentType: string;
    content: string;
  };
  hasAttachments: boolean;
  isRead: boolean;
  attachments: EmailAttachment[];
}

export interface ProcessedEmail {
  email: EmailMessage;
  isQuote: boolean;
  detection: {
    confidence: 'high' | 'medium' | 'low';
    matchedRules: string[];
    sources: ('subject' | 'body' | 'attachment')[];
  };
  preSapDocument?: import('@/lib/preSapNormalizer').PreSapDocument;
  pdfContents: string[];
}

export type ValidationStatus = 'pending' | 'validated' | 'rejected';

export interface QuoteListItem {
  id: string;
  emailId: string;
  subject: string;
  sender: string;
  senderEmail: string;
  receivedAt: string;
  confidence: 'high' | 'medium' | 'low';
  status: ValidationStatus;
  articleCount: number;
  clientName: string;
}
