// Mock data for demonstration mode
import { EmailMessage, ProcessedEmail } from '@/types/email';
import { detectQuoteRequest } from '@/lib/quoteDetector';
import { extractData } from '@/lib/dataExtractor';
import { normalizeToPreSap } from '@/lib/preSapNormalizer';
import { getMockPdfContent } from '@/lib/pdfParser';

export function getMockEmails(): EmailMessage[] {
  return [
    {
      id: 'email-001',
      subject: 'Demande de devis - Pièces mécaniques',
      from: {
        emailAddress: {
          name: 'Jean Dupont',
          address: 'j.dupont@acme-industries.com',
        },
      },
      receivedDateTime: '2026-01-21T09:30:00Z',
      bodyPreview: 'Bonjour, merci de nous faire un devis pour les articles suivants...',
      body: {
        contentType: 'text',
        content: `Bonjour,

Merci de nous faire un devis pour les articles suivants :

- Moteur industriel 5kW : 10 pcs
- Pompe hydraulique Type A : 5 pcs
- Panneau de contrôle : 3 pcs

Délai souhaité : 4 semaines

Cordialement,
Jean Dupont
Responsable Achats
ACME Industries`,
      },
      hasAttachments: true,
      isRead: false,
      attachments: [
        {
          id: 'att-001',
          name: 'quotation_request.pdf',
          contentType: 'application/pdf',
          size: 125000,
        },
      ],
    },
    {
      id: 'email-002',
      subject: 'Request for Quotation - Urgent',
      from: {
        emailAddress: {
          name: 'Marie Martin',
          address: 'm.martin@globalmfg.com',
        },
      },
      receivedDateTime: '2026-01-21T08:15:00Z',
      bodyPreview: 'Dear Sir/Madam, we would like a quotation for the following items...',
      body: {
        contentType: 'text',
        content: `Dear Sir/Madam,

We would like a quotation for the following items:

1. Stainless Steel Plates (2mm) - Quantity: 100 pcs
2. Aluminum Profiles (Type B) - Quantity: 200 units
3. Rubber Gaskets Kit - Quantity: 25 kits

Please provide lead time and best prices.
Delivery time required: within 2 weeks.

Best regards,
Marie Martin
Procurement Manager
Global Manufacturing Corp.`,
      },
      hasAttachments: true,
      isRead: false,
      attachments: [
        {
          id: 'att-002',
          name: 'rfq_urgent.pdf',
          contentType: 'application/pdf',
          size: 98000,
        },
      ],
    },
    {
      id: 'email-003',
      subject: 'Meeting confirmation for next week',
      from: {
        emailAddress: {
          name: 'Sophie Bernard',
          address: 's.bernard@partner.com',
        },
      },
      receivedDateTime: '2026-01-20T16:45:00Z',
      bodyPreview: 'Dear team, I confirm our meeting scheduled for next Tuesday...',
      body: {
        contentType: 'text',
        content: `Dear team,

I confirm our meeting scheduled for next Tuesday at 10:00 AM.

Please let me know if you need to reschedule.

Best regards,
Sophie Bernard`,
      },
      hasAttachments: false,
      isRead: true,
      attachments: [],
    },
    {
      id: 'email-004',
      subject: 'Price request - Electronic components',
      from: {
        emailAddress: {
          name: 'Thomas Weber',
          address: 't.weber@techsupply.de',
        },
      },
      receivedDateTime: '2026-01-20T14:20:00Z',
      bodyPreview: 'Hello, please quote for the following electronic components...',
      body: {
        contentType: 'text',
        content: `Hello,

Please quote for the following electronic components:

- Microcontroller STM32F4: 50 units
- Power Supply 24V/5A: 20 pcs
- Connector Kit Type-C: 100 sets

Lead time: 3 weeks preferred.

Thank you,
Thomas Weber
TechSupply GmbH`,
      },
      hasAttachments: false,
      isRead: false,
      attachments: [],
    },
    {
      id: 'email-005',
      subject: 'Invoice #2024-1234',
      from: {
        emailAddress: {
          name: 'Accounting',
          address: 'accounting@vendor.com',
        },
      },
      receivedDateTime: '2026-01-20T11:00:00Z',
      bodyPreview: 'Please find attached invoice for your recent order...',
      body: {
        contentType: 'text',
        content: `Dear Customer,

Please find attached invoice #2024-1234 for your recent order.

Payment terms: Net 30 days.

Regards,
Accounting Department`,
      },
      hasAttachments: true,
      isRead: true,
      attachments: [
        {
          id: 'att-003',
          name: 'invoice_2024-1234.pdf',
          contentType: 'application/pdf',
          size: 45000,
        },
      ],
    },
  ];
}

export function processEmails(emails: EmailMessage[]): ProcessedEmail[] {
  return emails.map((email) => {
    // Get PDF contents for quote detection
    const pdfContents: string[] = [];
    for (const attachment of email.attachments) {
      if (attachment.contentType === 'application/pdf') {
        const parsed = getMockPdfContent(attachment.name);
        if (parsed.parseSuccess) {
          pdfContents.push(parsed.textContent);
        }
      }
    }

    // Detect if this is a quote request
    const detection = detectQuoteRequest(
      email.subject,
      email.body.content,
      pdfContents
    );

    // If it's a quote, extract data and normalize
    let preSapDocument;
    if (detection.isQuote) {
      const extraction = extractData(
        email.body.content,
        email.from.emailAddress.address,
        email.from.emailAddress.name,
        pdfContents
      );

      preSapDocument = normalizeToPreSap(
        email.id,
        email.receivedDateTime,
        extraction,
        detection
      );
    }

    return {
      email,
      isQuote: detection.isQuote,
      detection: {
        confidence: detection.confidence,
        matchedRules: detection.matchedRules,
        sources: detection.sources,
      },
      preSapDocument,
      pdfContents,
    };
  });
}
