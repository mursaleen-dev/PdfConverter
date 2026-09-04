export interface ToolSeo {
  id: string;
  path: string;
  title: string;
  metaTitle: string;
  metaDescription: string;
  lead: string;
  steps: string[];
  faqs: { question: string; answer: string }[];
  related: string[];
}

export const HOME_SEO = {
  metaTitle: "Online PDF Editor, Converter, and Merger",
  metaDescription:
    "Free online PDF tools to edit text in place, convert PDF to Word or images, merge files, and export PDF/A. Works in the browser with no desktop install.",
  intro:
    "PDF Tools is a browser workspace for everyday PDF jobs: edit existing text without flattening the page, convert to Word, Excel, PowerPoint, or images, merge files, and archive to PDF/A. Each tool keeps the original page size and, when the file allows it, the original fonts.",
};

export const TOOL_SEO: Record<string, ToolSeo> = {
  "edit-pdf": {
    id: "edit-pdf",
    path: "/edit-pdf",
    title: "Edit PDF",
    metaTitle: "Edit PDF Online — Replace Text, Keep Fonts",
    metaDescription:
      "Edit PDF text in the browser while keeping the original font, size, and background. Add signatures, images, and shapes, then download a new PDF.",
    lead:
      "Use Edit PDF when you need to change wording on a form, ticket, or letter without rebuilding the file. Click a line, type the new text, and the editor reuses the source font and weight when the glyphs are available. Colored heading bars and table cells stay in place instead of being painted white. You can also add overlays (text boxes, signatures, images) and reorder pages before you save.",
    steps: [
      "Upload a PDF from your computer.",
      "Choose Edit text, then click the line you want to change.",
      "Type the new wording and click outside the box or the check mark to save it.",
      "Add signatures or shapes if you need overlays, then download the edited PDF.",
    ],
    faqs: [
      {
        question: "Will editing text change the original font?",
        answer:
          "The editor keeps the source family, weight, and size when the PDF embeds that face or a matching system font is installed. Type3 subsets (common in HTML-to-PDF tickets) are reused glyph-by-glyph so bold headings do not fall back to Arial.",
      },
      {
        question: "Can I edit a scanned PDF?",
        answer:
          "Pages that are only a photo of text cannot be clicked as selectable lines. Add a new text overlay instead, or OCR the file first and upload a searchable PDF.",
      },
      {
        question: "Does a second edit show my latest wording?",
        answer:
          "Yes. After you confirm a change, opening the same line again loads the updated text, not the original PDF string.",
      },
    ],
    related: ["merge-pdf", "pdf-to-word", "pdf-to-pdfa"],
  },
  "merge-pdf": {
    id: "merge-pdf",
    path: "/merge-pdf",
    title: "Merge PDF",
    metaTitle: "Merge PDF Files Online",
    metaDescription:
      "Combine two or more PDFs into one file. Reorder pages before you merge and download a single document.",
    lead:
      "Merge PDF joins separate documents—contracts, scans, annexes—into one file you can share. Add the PDFs, drag the list into the order you want, and download a single document. Page sizes and rotations from each source file are preserved.",
    steps: [
      "Add at least two PDF files.",
      "Use the arrows to set the order.",
      "Click merge and download the combined PDF.",
    ],
    faqs: [
      {
        question: "Is there a limit on how many PDFs I can merge?",
        answer:
          "You can add as many files as the upload size limit allows. Very large batches may take longer to process.",
      },
      {
        question: "Are bookmarks kept?",
        answer:
          "Page content is concatenated in order. Outline/bookmark trees from the source files are not rebuilt in the merged file.",
      },
    ],
    related: ["edit-pdf", "pdf-to-pdfa", "word-to-pdf"],
  },
  "pdf-to-word": {
    id: "pdf-to-word",
    path: "/pdf-to-word",
    title: "PDF to Word",
    metaTitle: "Convert PDF to Word (DOCX) Online",
    metaDescription:
      "Turn a PDF into an editable Word document. Keep a visual layout or extract real paragraphs and tables.",
    lead:
      "PDF to Word is for files you need to revise in Microsoft Word or Google Docs. Keep layout renders each page as it looks in the PDF (best for design-heavy pages). Editable text rebuilds paragraphs, tables, and images so you can change the copy. Complex multi-column layouts may still shift in editable mode.",
    steps: [
      "Upload a PDF.",
      "Pick Keep layout for a visual match, or Editable text to revise wording.",
      "Download the DOCX and open it in Word.",
    ],
    faqs: [
      {
        question: "Which mode should I use?",
        answer:
          "Use Keep layout when appearance matters more than editing (invoices, certificates). Use Editable text when you need to rewrite paragraphs or reuse tables.",
      },
      {
        question: "Can I convert a scanned PDF?",
        answer:
          "A scan has no real text layer. Keep layout will still produce a visual Word file. For editable copy, OCR the PDF first.",
      },
    ],
    related: ["word-to-pdf", "edit-pdf", "pdf-to-excel"],
  },
  "word-to-pdf": {
    id: "word-to-pdf",
    path: "/word-to-pdf",
    title: "Word to PDF",
    metaTitle: "Convert Word to PDF Online",
    metaDescription:
      "Convert DOC or DOCX files to PDF for sharing and printing. Keeps a readable, fixed layout.",
    lead:
      "Word to PDF locks a document into a layout that looks the same on every device. Upload a .doc or .docx file when you need to send a contract, resume, or report that should not reflow in someone else’s word processor.",
    steps: [
      "Upload a DOC or DOCX file.",
      "Wait for conversion to finish.",
      "Download the PDF.",
    ],
    faqs: [
      {
        question: "Are comments and tracked changes included?",
        answer:
          "The PDF reflects the document as rendered. Hidden markup is not exported as a separate review pane.",
      },
      {
        question: "What about fonts?",
        answer:
          "Common fonts are substituted if the original face is missing on the server. Embed unusual fonts in the Word file when you need an exact match.",
      },
    ],
    related: ["pdf-to-word", "edit-pdf", "merge-pdf"],
  },
  "pdf-to-excel": {
    id: "pdf-to-excel",
    path: "/pdf-to-excel",
    title: "PDF to Excel",
    metaTitle: "Convert PDF Tables to Excel (XLSX)",
    metaDescription:
      "Extract tables and rows from a PDF into an Excel spreadsheet you can filter and calculate.",
    lead:
      "PDF to Excel is built for statements, reports, and lists that already look like tables. It pulls rows into an .xlsx workbook so you can sort, chart, or re-total the numbers. Nested or borderless layouts may need a quick cleanup in Excel.",
    steps: [
      "Upload a PDF that contains tables.",
      "Download the XLSX file.",
      "Open it in Excel and check column headers.",
    ],
    faqs: [
      {
        question: "Will every table map 1:1?",
        answer:
          "Ruled tables convert most reliably. Text that only looks tabular (spaces instead of cells) may land in fewer columns.",
      },
      {
        question: "Are formulas preserved?",
        answer:
          "PDFs store values, not Excel formulas. You get numbers and text; you add formulas after export.",
      },
    ],
    related: ["excel-to-pdf", "pdf-to-word", "pdf-to-text"],
  },
  "excel-to-pdf": {
    id: "excel-to-pdf",
    path: "/excel-to-pdf",
    title: "Excel to PDF",
    metaTitle: "Convert Excel to PDF Online",
    metaDescription:
      "Turn XLS or XLSX spreadsheets into a PDF that prints and shares with a fixed layout.",
    lead:
      "Excel to PDF is for sending a sheet that should not be edited—budgets, invoices, or printed reports. The converter renders the workbook into pages so recipients see the same columns you see, without opening Excel.",
    steps: [
      "Upload an XLS or XLSX file.",
      "Download the PDF.",
      "Print or share the file as a fixed snapshot.",
    ],
    faqs: [
      {
        question: "Are all sheets included?",
        answer:
          "Visible worksheets are converted. Very wide sheets may paginate across more than one PDF page.",
      },
      {
        question: "Do charts export?",
        answer:
          "Charts that render with the sheet are included in the page image. Interactive slicers are not.",
      },
    ],
    related: ["pdf-to-excel", "word-to-pdf", "merge-pdf"],
  },
  "pdf-to-powerpoint": {
    id: "pdf-to-powerpoint",
    path: "/pdf-to-powerpoint",
    title: "PDF to PowerPoint",
    metaTitle: "Convert PDF to PowerPoint (PPTX)",
    metaDescription:
      "Turn each PDF page into a PowerPoint slide while keeping the visual layout.",
    lead:
      "PDF to PowerPoint is useful when a one-pager or report needs to become a deck. Each page becomes a slide so you can present without redesigning. Keep layout mode favors visual fidelity over fully editable shapes.",
    steps: [
      "Upload a PDF.",
      "Download the PPTX file.",
      "Open it in PowerPoint and add speaker notes if needed.",
    ],
    faqs: [
      {
        question: "Can I edit every object on the slide?",
        answer:
          "Slides match the PDF visually. Text and graphics may be grouped or rasterized depending on how the PDF was built.",
      },
      {
        question: "What about animations?",
        answer:
          "PDFs have no slide animations. Those are not created during conversion.",
      },
    ],
    related: ["powerpoint-to-pdf", "pdf-to-jpg", "edit-pdf"],
  },
  "powerpoint-to-pdf": {
    id: "powerpoint-to-pdf",
    path: "/powerpoint-to-pdf",
    title: "PowerPoint to PDF",
    metaTitle: "Convert PowerPoint to PDF Online",
    metaDescription:
      "Export PPT or PPTX slideshows to PDF for sharing, printing, and archiving.",
    lead:
      "PowerPoint to PDF freezes a deck into a file anyone can open. Use it for handouts, RFPs, and email attachments when you do not want recipients to edit the slides.",
    steps: [
      "Upload a PPT or PPTX file.",
      "Download the PDF.",
      "Share or print the slides as pages.",
    ],
    faqs: [
      {
        question: "Are speaker notes included?",
        answer:
          "The PDF contains the slide canvas. Speaker notes are not added as extra pages.",
      },
      {
        question: "Do videos play in the PDF?",
        answer:
          "Embedded video does not play in the exported PDF. Export a still of the slide instead.",
      },
    ],
    related: ["pdf-to-powerpoint", "merge-pdf", "pdf-to-jpg"],
  },
  "pdf-to-jpg": {
    id: "pdf-to-jpg",
    path: "/pdf-to-jpg",
    title: "PDF to JPG",
    metaTitle: "Convert PDF Pages to JPG Images",
    metaDescription:
      "Render each PDF page as a JPG. Multi-page files download as a zip of images.",
    lead:
      "PDF to JPG is for thumbnails, social posts, or embedding a page in a CMS that only accepts photos. Every page is rasterized to JPEG. A multi-page PDF comes back as a zip so you can pick the pages you need.",
    steps: [
      "Upload a PDF.",
      "Download the JPG, or a zip if there are several pages.",
      "Use the images in slides, web pages, or print workflows.",
    ],
    faqs: [
      {
        question: "Is text still selectable?",
        answer:
          "No. JPG is a picture of the page. Use Edit PDF or PDF to Word if you need selectable text.",
      },
      {
        question: "What resolution do I get?",
        answer:
          "Pages are rendered at a high enough resolution for screen and typical print. Extreme large-format print may need a dedicated RIP.",
      },
    ],
    related: ["pdf-to-png", "jpg-to-pdf", "edit-pdf"],
  },
  "jpg-to-pdf": {
    id: "jpg-to-pdf",
    path: "/jpg-to-pdf",
    title: "JPG to PDF",
    metaTitle: "Convert JPG Images to PDF",
    metaDescription:
      "Turn a JPEG photo or scan into a PDF page you can print or combine with other files.",
    lead:
      "JPG to PDF wraps a photo or phone scan into a standard PDF page. Use it when an office portal only accepts PDF, or when you want to merge photos with other documents later.",
    steps: [
      "Upload a JPG or JPEG image.",
      "Download the PDF.",
      "Merge it with other PDFs if you need a packet.",
    ],
    faqs: [
      {
        question: "Will the image be compressed again?",
        answer:
          "The JPEG is placed on a PDF page. Quality stays close to the original unless the source file is already tiny.",
      },
      {
        question: "Can I convert several photos at once?",
        answer:
          "This tool converts one image per run. Convert each photo, then use Merge PDF to stack them.",
      },
    ],
    related: ["png-to-pdf", "merge-pdf", "pdf-to-jpg"],
  },
  "png-to-pdf": {
    id: "png-to-pdf",
    path: "/png-to-pdf",
    title: "PNG to PDF",
    metaTitle: "Convert PNG Images to PDF",
    metaDescription:
      "Place a PNG—including transparency—onto a PDF page for sharing and printing.",
    lead:
      "PNG to PDF is the right path for screenshots, UI captures, and graphics with a transparent background. The image becomes a PDF page you can email or merge with reports.",
    steps: [
      "Upload a PNG file.",
      "Download the PDF.",
      "Print or merge it with other documents.",
    ],
    faqs: [
      {
        question: "Is transparency kept?",
        answer:
          "PNG transparency is preserved in the PDF where the viewer supports it. Some printers flatten it to white.",
      },
      {
        question: "Why not use JPG to PDF?",
        answer:
          "JPEG has no alpha channel. Use PNG to PDF for logos and screenshots that need sharp edges.",
      },
    ],
    related: ["jpg-to-pdf", "pdf-to-png", "merge-pdf"],
  },
  "pdf-to-png": {
    id: "pdf-to-png",
    path: "/pdf-to-png",
    title: "PDF to PNG",
    metaTitle: "Convert PDF Pages to PNG Images",
    metaDescription:
      "Export each PDF page as a lossless PNG. Multi-page files download as a zip.",
    lead:
      "PDF to PNG is for crisp screenshots of vector pages—diagrams, UI specs, or slides—when JPEG artifacts would show. Each page becomes a PNG; several pages download as a zip.",
    steps: [
      "Upload a PDF.",
      "Download the PNG or zip.",
      "Drop the images into design tools or documentation.",
    ],
    faqs: [
      {
        question: "PNG or JPG?",
        answer:
          "Choose PNG for sharp lines and text. Choose JPG for photos and smaller files.",
      },
      {
        question: "Can I pick one page only?",
        answer:
          "The tool exports every page. Unzip and keep the page you need, or split the PDF first.",
      },
    ],
    related: ["pdf-to-jpg", "png-to-pdf", "edit-pdf"],
  },
  "html-to-pdf": {
    id: "html-to-pdf",
    path: "/html-to-pdf",
    title: "HTML to PDF",
    metaTitle: "Convert a Webpage URL to PDF",
    metaDescription:
      "Paste a URL and save that webpage as a PDF, including the live layout Chrome would print.",
    lead:
      "HTML to PDF captures a public URL the way a browser would print it. Use it for receipts, documentation, or articles you want to archive. The page must be reachable from the converter (no login wall).",
    steps: [
      "Paste a full URL starting with https://.",
      "Convert and wait for the page to render.",
      "Download the PDF.",
    ],
    faqs: [
      {
        question: "Can I convert a page behind a login?",
        answer:
          "No. Only publicly reachable URLs work. Print from your browser for authenticated pages.",
      },
      {
        question: "Why do some fonts look different after I edit the PDF?",
        answer:
          "Chrome often embeds Type3 font subsets. Edit PDF is built to reuse those faces so headings stay bold instead of switching to a generic sans font.",
      },
    ],
    related: ["edit-pdf", "pdf-to-word", "text-to-pdf"],
  },
  "pdf-to-text": {
    id: "pdf-to-text",
    path: "/pdf-to-text",
    title: "PDF to Text",
    metaTitle: "Extract Text from a PDF",
    metaDescription:
      "Pull the plain text layer out of a PDF for search, notes, or another editor.",
    lead:
      "PDF to Text copies the real text stream from a searchable PDF—no formatting, just the words. Use it for quotes, indexing, or feeding content into another tool. Image-only scans have nothing to extract.",
    steps: [
      "Upload a searchable PDF.",
      "Download the text file.",
      "Open it in any editor.",
    ],
    faqs: [
      {
        question: "Why is the file empty?",
        answer:
          "The PDF is probably a scan. There is no text layer. OCR it first, or type over it in Edit PDF.",
      },
      {
        question: "Is reading order perfect?",
        answer:
          "Text follows the PDF’s content stream. Multi-column pages may interleave in unexpected order.",
      },
    ],
    related: ["text-to-pdf", "pdf-to-word", "edit-pdf"],
  },
  "text-to-pdf": {
    id: "text-to-pdf",
    path: "/text-to-pdf",
    title: "Text to PDF",
    metaTitle: "Convert a TXT File to PDF",
    metaDescription:
      "Turn a plain text file into a simple, readable PDF for sharing and printing.",
    lead:
      "Text to PDF wraps a .txt file in a clean PDF so notes, logs, or license text can be attached to email and print jobs. It is not a word processor—expect a straightforward paginated layout.",
    steps: [
      "Upload a .txt file.",
      "Download the PDF.",
      "Print or merge it with other PDFs.",
    ],
    faqs: [
      {
        question: "Can I set fonts and margins?",
        answer:
          "The converter uses a readable default layout. For designed pages, paste the text into Word and use Word to PDF.",
      },
      {
        question: "What encoding is supported?",
        answer:
          "UTF-8 text works for most languages. Legacy encodings may show replacement characters.",
      },
    ],
    related: ["pdf-to-text", "word-to-pdf", "html-to-pdf"],
  },
  "pdf-to-pdfa": {
    id: "pdf-to-pdfa",
    path: "/pdf-to-pdfa",
    title: "PDF to PDF/A",
    metaTitle: "Convert PDF to PDF/A for Archiving",
    metaDescription:
      "Convert a PDF to PDF/A-2b, the ISO format used for long-term records and compliance.",
    lead:
      "PDF to PDF/A produces an archival file (PDF/A-2b) that embeds the fonts it needs so the document still opens years later. Use it for records retention, tenders, and court filings that ask for PDF/A.",
    steps: [
      "Upload a PDF.",
      "Download the PDF/A file.",
      "Store it in your archive or upload it to the portal that required PDF/A.",
    ],
    faqs: [
      {
        question: "Which PDF/A level is this?",
        answer:
          "The converter targets PDF/A-2b, a widely accepted archival profile for visual preservation.",
      },
      {
        question: "Will every PDF pass a validator?",
        answer:
          "Most office PDFs convert cleanly. Files with forbidden features (some attachments or encryption) may need to be flattened first.",
      },
    ],
    related: ["edit-pdf", "merge-pdf", "word-to-pdf"],
  },
};

export function getToolSeo(id: string): ToolSeo {
  const tool = TOOL_SEO[id];
  if (!tool) {
    throw new Error(`Missing SEO copy for tool ${id}`);
  }
  return tool;
}
