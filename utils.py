"""
utils.py
--------
PDF extraction and AI-powered field generation utilities.
Uses PyMuPDF for text extraction and the Google Gemini API for
intelligent structured data extraction from World Bank-style project documents.
"""

import os
import re
import json
import time
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
from typing import Optional
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemma-3-27b-it"
MAX_TOKENS = 2000
CHUNK_SIZE = 10_000          # characters — safe context window per API call
RATE_LIMIT_DELAY = 20.0       # seconds between API calls to avoid throttling

COLUMNS = [
    "PROJ_DEV_OBJECTIVE_DESC",
    "LEAD_GP_NAME",
    "CMT_AMT",
    "Climate Financing (%)",
    "Adaptation (%)",
    "Mitigation (%)",
    "PriorActions",
    "Indicators",
    "Components",
    "DLI_DLR",
]

SYSTEM_PROMPT = """You are an expert analyst specializing in World Bank and international development project documents.
Your task is to extract structured information from project documents accurately and concisely.
Always respond with valid JSON only — no markdown fences, no preamble, no explanation outside the JSON object."""

EXTRACTION_PROMPT_TEMPLATE = """Extract the following fields from the project document text below.
Return ONLY a valid JSON object with these exact keys. Do not add extra keys.

Fields to extract:
- PROJ_DEV_OBJECTIVE_DESC: The Project Development Objective (PDO) description. Write 4-5 sentences describing the project's development objective, beneficiaries, and expected outcomes. Draw from the PDO section or executive summary.
- LEAD_GP_NAME: The Lead Global Practice or Global Practice responsible for this project. Return 2-4 words only (e.g., "Urban, Resilience and Land", "Education", "Water Global Practice").
- CMT_AMT: The total commitment/financing amount for the project. Include the currency and numeric value (e.g., "USD 150 million", "EUR 80.5 million"). If not found, return "Not Available".
- Climate Financing (%): The percentage of the total project cost attributed to climate financing. Return as a number with % sign (e.g., "35%"). If not explicitly stated, estimate from context or return "Not Available".
- Adaptation (%): The percentage of total project cost for adaptation financing. Return as a number with % sign. If not available, return "Not Available".
- Mitigation (%): The percentage of total project cost for mitigation financing. Return as a number with % sign. If not available, return "Not Available".
- PriorActions: Any prior actions mentioned (policy actions required before disbursement). Include dates and descriptions. If multiple, separate with " | ". If none, return "Not Available".
- Indicators: All project indicators, KPIs, PDO indicators, IRIs, or quantitative metrics. For each, include the indicator name and target/description. Separate multiple indicators with " | ". If none, return "Not Available".
- Components: All project components with their descriptions and allocated amounts if available. Separate multiple components with " | ". If none, return "Not Available".
- DLI_DLR: Disbursement Linked Indicators (DLI) and Disbursement Linked Results (DLR). Include the name/number and description of each. Separate with " | ". If none, return "Not Available".

Rules:
- Be accurate and extract only information present in the document.
- Do not invent or hallucinate figures.
- For numeric fields like CMT_AMT, look for terms like "total financing", "IDA credit", "IBRD loan", "grant amount", "total project cost".
- For percentages, look for climate co-benefits tables, climate finance tags, or explicit percentage statements.

Document text:
{text}

Return ONLY the JSON object:"""


# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------

class PDFExtractor:
    """Extracts full text from PDF files using PyMuPDF."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.filename = Path(pdf_path).name

    def extract_text(self) -> str:
        """Extract all text from the PDF, page by page."""
        doc = fitz.open(self.pdf_path)
        pages_text = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                pages_text.append(f"[Page {page_num}]\n{text}")
        doc.close()
        return "\n\n".join(pages_text)

    def extract_text_with_layout(self) -> str:
        """Extract text preserving layout (better for tables and forms)."""
        doc = fitz.open(self.pdf_path)
        pages_text = []
        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks")
            # Sort blocks top-to-bottom, left-to-right
            blocks_sorted = sorted(blocks, key=lambda b: (round(b[1] / 20), b[0]))
            page_content = "\n".join(b[4].strip() for b in blocks_sorted if b[4].strip())
            if page_content:
                pages_text.append(f"[Page {page_num}]\n{page_content}")
        doc.close()
        return "\n\n".join(pages_text)

    def get_metadata(self) -> dict:
        """Extract PDF metadata."""
        doc = fitz.open(self.pdf_path)
        meta = doc.metadata or {}
        meta["page_count"] = len(doc)
        doc.close()
        return meta

    def is_scanned(self) -> bool:
        """Heuristic: if text extraction yields very little text, likely scanned."""
        text = self.extract_text()
        words = len(text.split())
        pages = fitz.open(self.pdf_path)
        page_count = len(pages)
        pages.close()
        avg_words_per_page = words / max(page_count, 1)
        return avg_words_per_page < 30


# ---------------------------------------------------------------------------
# Smart text chunking
# ---------------------------------------------------------------------------

def smart_chunk(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """
    Split text into chunks of up to max_chars characters.
    Tries to split at paragraph boundaries to preserve context.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for \n\n
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def prioritize_text(full_text: str, max_chars: int = CHUNK_SIZE) -> str:
    """
    For very long documents, prioritize sections most likely to contain
    the target fields: early pages (executive summary, PDO) and
    sections with financial/component keywords.
    """
    if len(full_text) <= max_chars:
        return full_text

    lines = full_text.split("\n")
    priority_keywords = [
        "development objective", "PDO", "commitment", "financing amount",
        "climate", "adaptation", "mitigation", "component", "prior action",
        "indicator", "disbursement", "DLI", "DLR", "IRI", "global practice",
        "lead GP", "total project cost", "IBRD", "IDA", "grant",
    ]

    priority_lines = []
    normal_lines = []

    for line in lines:
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in priority_keywords):
            priority_lines.append(line)
        else:
            normal_lines.append(line)

    # Build text: first 40% priority content, then fill with normal
    priority_text = "\n".join(priority_lines)
    first_chunk = "\n".join(lines[:500])  # Always include document start

    combined = first_chunk + "\n\n--- KEY SECTIONS ---\n\n" + priority_text
    if len(combined) <= max_chars:
        return combined

    return combined[:max_chars]


# ---------------------------------------------------------------------------
# AI Field Extractor
# ---------------------------------------------------------------------------

class FieldExtractor:
    """
    Uses the Google Gemini API to extract structured fields from PDF text.
    Supports chunked processing for large documents.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "Google API key not found. Set the GOOGLE_API_KEY "
                "environment variable or pass api_key= to FieldExtractor."
            )
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def _call_api(self, text: str) -> dict:
        """Make a single API call to extract fields from text."""
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(text=text)
        full_prompt = SYSTEM_PROMPT + "\n\n" + prompt
        
        response = self.model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=MAX_TOKENS,
                temperature=0.2,  # Low temperature for consistency
            ),
        )
        raw = response.text.strip()

        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Attempt to extract JSON object substring
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse API response as JSON:\n{raw}")

    def _merge_results(self, results: list[dict]) -> dict:
        """
        Merge extraction results from multiple chunks.
        For each field, use the first non-"Not Available" value found.
        For list-like fields (Indicators, Components, etc.), concatenate unique entries.
        """
        list_fields = {"PriorActions", "Indicators", "Components", "DLI_DLR"}
        merged = {col: "Not Available" for col in COLUMNS}

        for result in results:
            for col in COLUMNS:
                val = result.get(col, "Not Available")
                if not val or val.strip().lower() in ("not available", "n/a", "none", ""):
                    continue

                if col in list_fields:
                    # Accumulate unique entries separated by |
                    existing = merged[col]
                    if existing == "Not Available":
                        merged[col] = val
                    else:
                        # Deduplicate pipe-separated entries
                        existing_parts = set(p.strip() for p in existing.split("|"))
                        new_parts = [p.strip() for p in val.split("|")
                                     if p.strip() not in existing_parts]
                        if new_parts:
                            merged[col] = existing + " | " + " | ".join(new_parts)
                else:
                    # Scalar field: keep first good value
                    if merged[col] == "Not Available":
                        merged[col] = val

        return merged

    def extract_fields(self, full_text: str, filename: str = "") -> dict:
        """
        Extract all target fields from a PDF's full text.
        Handles large documents by chunking or prioritizing content.
        """
        print(f"  Extracting fields from: {filename or 'document'} "
              f"({len(full_text):,} chars)")

        # For large docs: use priority text first, then chunk remainder
        text_to_use = prioritize_text(full_text, max_chars=CHUNK_SIZE)

        if len(full_text) > CHUNK_SIZE * 2:
            # Very large doc: also process raw chunks for completeness
            chunks = smart_chunk(full_text, max_chars=CHUNK_SIZE)
            print(f"    Document is large ({len(chunks)} chunks). "
                  f"Processing priority text + first 3 chunks.")
            texts_to_process = [text_to_use] + chunks[:3]
        else:
            texts_to_process = [text_to_use]

        all_results = []
        for i, chunk in enumerate(texts_to_process):
            print(f"    API call {i+1}/{len(texts_to_process)} ...")
            try:
                result = self._call_api(chunk)
                all_results.append(result)
                if i < len(texts_to_process) - 1:
                    time.sleep(RATE_LIMIT_DELAY)
            except Exception as e:
                print(f"    Warning: API call {i+1} failed: {e}")

        if not all_results:
            print(f"  ERROR: All API calls failed for {filename}")
            return {col: "Extraction Failed" for col in COLUMNS}

        merged = self._merge_results(all_results)
        return merged


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class PDFPipeline:
    """
    Main pipeline: scans a folder for PDFs, extracts text, runs AI extraction,
    and produces a pandas DataFrame saved as CSV.
    """

    def __init__(self, docs_folder: str, api_key: Optional[str] = None,
                 output_path: str = "data.csv"):
        self.docs_folder = Path(docs_folder)
        self.output_path = output_path
        self.extractor = FieldExtractor(api_key=api_key)

    def get_pdf_files(self) -> list[Path]:
        """Return sorted list of .pdf files in the docs folder."""
        if not self.docs_folder.exists():
            raise FileNotFoundError(
                f"Docs folder not found: {self.docs_folder.resolve()}"
            )
        pdfs = sorted(self.docs_folder.glob("*.pdf"))
        if not pdfs:
            raise FileNotFoundError(
                f"No PDF files found in: {self.docs_folder.resolve()}"
            )
        print(f"Found {len(pdfs)} PDF file(s) in '{self.docs_folder}':")
        for p in pdfs:
            print(f"  - {p.name}")
        return pdfs

    def process_pdf(self, pdf_path: Path) -> dict:
        """Full pipeline for a single PDF: extract text → extract fields."""
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_path.name}")
        print(f"{'='*60}")

        pdf_extractor = PDFExtractor(str(pdf_path))

        # Check for scanned PDFs
        if pdf_extractor.is_scanned():
            print(f"  WARNING: '{pdf_path.name}' appears to be scanned "
                  f"(low text density). Results may be limited.")

        # Use layout-aware extraction for better table/form parsing
        try:
            text = pdf_extractor.extract_text_with_layout()
            if len(text.strip()) < 200:
                # Fallback to simple text extraction
                text = pdf_extractor.extract_text()
        except Exception as e:
            print(f"  Layout extraction failed ({e}), using basic extraction.")
            text = pdf_extractor.extract_text()

        if not text.strip():
            print(f"  ERROR: Could not extract any text from {pdf_path.name}")
            row = {col: "Text Extraction Failed" for col in COLUMNS}
            row["source_file"] = pdf_path.name
            return row

        fields = self.extractor.extract_fields(text, filename=pdf_path.name)
        fields["source_file"] = pdf_path.name
        return fields

    def run(self) -> pd.DataFrame:
        """
        Run the full pipeline on all PDFs in the docs folder.
        Returns a DataFrame and saves it to output_path as CSV.
        """
        pdf_files = self.get_pdf_files()
        rows = []

        for pdf_path in pdf_files:
            try:
                row = self.process_pdf(pdf_path)
                rows.append(row)
                print(f"\n  ✓ Done: {pdf_path.name}")
            except Exception as e:
                print(f"\n  ✗ Failed: {pdf_path.name} — {e}")
                row = {col: f"Error: {e}" for col in COLUMNS}
                row["source_file"] = pdf_path.name
                rows.append(row)

            # Throttle between PDFs
            time.sleep(RATE_LIMIT_DELAY)

        # Build DataFrame with columns in defined order
        df = pd.DataFrame(rows, columns=["source_file"] + COLUMNS)
        df.to_csv(self.output_path, index=False, encoding="utf-8-sig")
        print(f"\n{'='*60}")
        print(f"Pipeline complete. {len(df)} record(s) written to: {self.output_path}")
        print(f"{'='*60}")
        return df