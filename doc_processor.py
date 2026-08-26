import os
import datetime
import json
import re
import threading
import fitz  # PyMuPDF
from docx import Document
import tempfile
import time
import pypandoc

def _format_log_message(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    return f"[{ts}] {msg}"

_gemini_quota_exhausted = False
_gemini_requests_this_minute = []
_gemini_total_requests_today = 0
_gemini_last_reset_time = None
_last_gemini_request_time = 0

def _check_and_reset_daily_quota():
    global _gemini_total_requests_today, _gemini_last_reset_time
    now = datetime.datetime.now()
    # Reset at 1:30 PM (13:30)
    reset_time_today = now.replace(hour=13, minute=30, second=0, microsecond=0)
    
    if _gemini_last_reset_time is None:
        if now >= reset_time_today:
            _gemini_last_reset_time = reset_time_today
        else:
            _gemini_last_reset_time = reset_time_today - datetime.timedelta(days=1)
        return

    if now >= reset_time_today and _gemini_last_reset_time < reset_time_today:
        _gemini_total_requests_today = 0
        _gemini_last_reset_time = reset_time_today

def _track_gemini_request():
    global _gemini_requests_this_minute, _gemini_total_requests_today
    _check_and_reset_daily_quota()
    now_ts = time.time()
    _gemini_requests_this_minute.append(now_ts)
    _gemini_total_requests_today += 1
    # Clean up old timestamps (older than 60s)
    _gemini_requests_this_minute = [ts for ts in _gemini_requests_this_minute if now_ts - ts < 60]

def _wait_for_gemini_rate_limit():
    global _last_gemini_request_time
    now = time.time()
    elapsed = now - _last_gemini_request_time
    # 15 RPM = 1 request every 4 seconds. 5 seconds is safer.
    if elapsed < 5:
        time.sleep(5 - elapsed)
    _last_gemini_request_time = time.time()
    _track_gemini_request()

def get_gemini_stats():
    now_ts = time.time()
    current_minute_requests = [ts for ts in _gemini_requests_this_minute if now_ts - ts < 60]
    return {
        "rpm": len(current_minute_requests),
        "total_today": _gemini_total_requests_today
    }

def call_gemini_text(prompt, api_key, model_id, temperature=0.4, system_instruction=None):
    """Generic single-shot Gemini text call shared across callers (e.g. the market
    digest engine) so they don't each duplicate SDK setup and quota handling.
    Shares this module's rate-limiter/quota globals with structure_text_with_gemini
    and generate_document_title. Never raises — returns None on any failure so
    callers can fall back cleanly."""
    global _gemini_quota_exhausted
    if _gemini_quota_exhausted:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        _wait_for_gemini_rate_limit()
        cfg_kwargs = {"temperature": temperature}
        if system_instruction:
            cfg_kwargs["system_instruction"] = system_instruction
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs)
        )
        if response and response.text:
            return response.text.strip()
        return None
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
            _gemini_quota_exhausted = True
        return None

def sanitize_filename(name):
    """Remove special characters and replace spaces with underscores to create a safe file name."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "_")
    return name

def extract_text_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        pages_text = []
        for i, page in enumerate(doc):
            pages_text.append(f"## Page {i+1}\n\n{page.get_text()}")
        return pages_text
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def extract_text_with_docling(pdf_path):
    """Uses Docling to convert PDF to Markdown and extract metadata."""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        import platform

        pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=False)
        # Increase resolution scale to 2.0 (144 DPI) to improve OCR recognition of small newspaper print
        pipeline_options.images_scale = 2.0
        
        # On macOS, use native Vision framework OCR (no model download required, hardware-accelerated)
        if platform.system() == "Darwin":
            from docling.datamodel.pipeline_options import OcrMacOptions
            # Limit language preference strictly to English to eliminate multi-language hallucinations
            pipeline_options.ocr_options = OcrMacOptions(lang=["en-US"])

        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(pdf_path)
        
        metadata = {}
        try:
            doc = result.document
            if hasattr(doc, 'origin') and doc.origin:
                origin = doc.origin
                if hasattr(origin, 'metadata') and origin.metadata:
                    m = origin.metadata
                    if hasattr(m, 'title') and m.title:
                        metadata['title'] = m.title
                    if hasattr(m, 'authors') and m.authors:
                        metadata['authors'] = m.authors
                    if hasattr(m, 'publication_date') and m.publication_date:
                        metadata['date'] = m.publication_date
                    if hasattr(m, 'abstract') and m.abstract:
                        metadata['abstract'] = m.abstract
                    if hasattr(m, 'keywords') and m.keywords:
                        metadata['keywords'] = m.keywords
        except Exception as e:
            print(f"Error harvesting Docling metadata: {e}")
            
        return result.document.export_to_markdown(), metadata
    except Exception as e:
        return f"Docling Extraction Failed: {str(e)}", {}

def extract_text_with_pypandoc(file_path, format='latex'):
    """Uses Pandoc to convert LaTeX or other formats to Markdown."""
    try:
        # Check for pandoc
        pypandoc.get_pandoc_version()
        output = pypandoc.convert_file(file_path, 'markdown', format=format, extra_args=['--wrap=none'])
        return output
    except Exception as e:
        return f"Pandoc Conversion Failed: {str(e)}"

_ocrmac_lock = threading.Lock()

def extract_text_from_pdf_with_ocrmac(pdf_path):
    """Uses native macOS Vision framework via ocrmac for on-device OCR."""
    try:
        from ocrmac import ocrmac
        doc = fitz.open(pdf_path)
        pages_text = []

        # Serialize Vision-framework OCR calls across documents. When multiple PDFs
        # are processed concurrently (ThreadPoolExecutor with max_workers>1), calling
        # ocrmac.OCR from several threads at once has been observed to silently return
        # zero annotations for some pages (no exception raised) rather than erroring or
        # queueing — producing blank "extracted" text that looks like a successful run.
        with _ocrmac_lock:
            for i, page in enumerate(doc):
                # Increase resolution (2x scale) to improve OCR for small newspaper text
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                    pix.save(tmp.name)
                    annotations = ocrmac.OCR(tmp.name, language_preference=['en-US']).recognize()
                    page_text = "\n".join([a[0] for a in annotations])
                    pages_text.append(f"## Page {i+1}\n\n{page_text}")

        return pages_text
    except Exception as e:
        return f"On-Device OCR Failed: {str(e)}"

# ===========================================================================
# AUTO-ROUTER — one entry point that classifies each PDF page and picks the
# right extraction engine itself, so you never switch engines per document.
#
#   TEXT page  (rich text layer)         -> faithful text-layer extraction
#   IMAGE page (no text, big image)      -> scanned page (OCR) OR an ad (drop)
#   SPARSE page (little text, no image)  -> title/divider (keep if short)
#
# Document mode disambiguates IMAGE pages:
#   SCANNED      (>=50% pages are IMAGE)  -> e.g. image-format FT  -> VLM-OCR
#   BORN_DIGITAL (<50% IMAGE)             -> e.g. WSJ/BS/RBI/HBR    -> text layer,
#                                            and IMAGE pages = ads  -> dropped
# Tunable thresholds default well for newspapers; verify with --classify.
# ===========================================================================

ROUTER_TEXT_CHARS = 300     # >= this many chars on a page => born-digital TEXT page
ROUTER_IMG_RATIO = 0.5      # image area / page area >= this => IMAGE page
ROUTER_DOC_IMAGE_SHARE = 0.5  # >= this share of IMAGE pages => whole doc is SCANNED
ROUTER_SPARSE_KEEP_CHARS = 40  # keep SPARSE pages with at least this much text
ROUTER_PRINTABLE_MIN = 0.6  # text layer must be >= this fraction printable to be "real"

def classify_page(page):
    """Classify a single fitz page. Returns (kind, chars, img_ratio, text)."""
    text = (page.get_text("text") or "").strip()
    # Count only *usable* characters. Some publishers (e.g. Indian Express) embed
    # non-Unicode subset fonts with no ToUnicode CMap, so get_text() returns raw glyph
    # codes (control chars \x01\x02…) instead of letters. Such a page has a large raw
    # length but is unreadable gibberish; counting raw length would misroute it to the
    # text-layer engine and emit garbage. If the layer is mostly non-printable, we treat
    # the page as having NO usable text layer (chars=0) so it routes to OCR instead.
    raw_len = len(text)
    if raw_len:
        bad = sum(1 for c in text if (not c.isprintable()) and c not in "\n\r\t")
        printable_ratio = 1.0 - (bad / raw_len)
    else:
        printable_ratio = 0.0
    chars = raw_len if printable_ratio >= ROUTER_PRINTABLE_MIN else 0
    img_area = 0.0
    try:
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") == 1:  # image block
                x0, y0, x1, y1 = b.get("bbox", (0, 0, 0, 0))
                img_area += abs((x1 - x0) * (y1 - y0))
    except Exception:
        pass
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    img_ratio = img_area / page_area
    if chars >= ROUTER_TEXT_CHARS:
        kind = "TEXT"
    elif img_ratio >= ROUTER_IMG_RATIO:
        kind = "IMAGE"
    else:
        kind = "SPARSE"
    return kind, chars, round(img_ratio, 2), text

def classify_pdf(pdf_path):
    """Per-page classification + document mode, with no extraction. Cheap & safe."""
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        kind, chars, img_ratio, _ = classify_page(page)
        pages.append({"page": i + 1, "kind": kind, "chars": chars, "img_ratio": img_ratio})
    total = len(pages) or 1
    image_share = sum(1 for p in pages if p["kind"] == "IMAGE") / total
    mode = "SCANNED" if image_share >= ROUTER_DOC_IMAGE_SHARE else "BORN_DIGITAL"
    engine = "nuextract_vlm" if mode == "SCANNED" else "text_layer"
    return {"mode": mode, "engine": engine, "pages": total,
            "image_share": round(image_share, 2), "page_detail": pages}

def route_and_extract(pdf_path, nuextract_model="numind/NuExtract3-mlx-4bits", progress_callback=None,
                      restructure_with_ollama=False, ollama_model=None, ollama_host="http://localhost:11434",
                      prompt_template=None, chunk_size=16000, overlap=1000):
    """Single auto-routing extraction entry point.

    Returns (markdown_text, report). `report` records mode/engine/pages so the
    caller can stamp provenance into frontmatter.

    If `restructure_with_ollama` is True and `ollama_model` is set, the faithfully
    extracted text (born-digital text layer OR scanned Apple-Vision OCR) is passed
    through a local Ollama LLM for clean-Markdown reformatting. The fidelity guard
    in structure_text_with_ollama falls back to the raw text if the model tries to
    summarize, so enabling this never silently loses content. No cloud/Gemini call.
    """
    doc = fitz.open(pdf_path)
    page_info = [classify_page(p) for p in doc]
    kinds = [pi[0] for pi in page_info]
    total = len(kinds) or 1
    image_share = sum(1 for k in kinds if k == "IMAGE") / total
    mode = "SCANNED" if image_share >= ROUTER_DOC_IMAGE_SHARE else "BORN_DIGITAL"

    report = {"mode": mode, "pages": total, "image_share": round(image_share, 2),
              "kept_pages": 0, "dropped_pages": 0, "page_kinds": kinds}

    if mode == "SCANNED":
        # Image-format publication (e.g. FT): on-device OCR (Apple Vision) over the whole doc.
        # Small vision-LLM OCR models (e.g. glm-ocr, NuExtract3) were tried here first but
        # both are unreliable for dense newsprint: glm-ocr (1.1B) hallucinates plausible-looking
        # wrong facts (wrong numbers, wrong names) rather than misreading characters, and
        # NuExtract3 via mlx-vlm is far too slow for a daily-paper page count. ocrmac makes
        # genuine character-level OCR slips (e.g. "rn"->"m") but never invents content, and is
        # ~8x faster and fully free/on-device. Faithfulness beats cleanliness for an archive.
        if progress_callback:
            progress_callback(f"Router: SCANNED ({image_share:.0%} image pages) -> on-device OCR (Apple Vision)")
        ocr = extract_text_from_pdf_with_ocrmac(pdf_path)
        text = "\n\n".join(ocr) if isinstance(ocr, list) else str(ocr)
        report["engine"] = "ocrmac"
        report["kept_pages"] = total
        if restructure_with_ollama and ollama_model and text.strip():
            if progress_callback:
                progress_callback(f"Router: restructuring OCR text locally via Ollama ({ollama_model})...")
            text = structure_text_with_ollama(text, ollama_model, host=ollama_host,
                                              prompt_template=prompt_template, chunk_size=chunk_size,
                                              overlap=overlap, progress_callback=progress_callback)
            report["engine"] = "ocrmac+ollama"
        return text, report

    # BORN_DIGITAL (WSJ / BS / RBI / HBR): faithful text layer, drop ad/image pages.
    # The text layer is already clean, real Unicode text, so it is preserved AS-IS and
    # never sent to an LLM — consistent with the docling/native paths. LLM restructuring
    # (the `restructure_with_ollama` flag) applies only to the SCANNED/OCR branch above,
    # where the raw OCR is genuinely messy and benefits from cleanup.
    if progress_callback:
        progress_callback(f"Router: BORN_DIGITAL ({image_share:.0%} image pages) -> text layer; dropping ad/image pages")
    report["engine"] = "text_layer"
    parts = []
    for i, (kind, chars, img_ratio, text) in enumerate(page_info):
        if kind == "TEXT":
            parts.append(f"## Page {i + 1}\n\n{text}")
            report["kept_pages"] += 1
        elif kind == "SPARSE" and chars >= ROUTER_SPARSE_KEEP_CHARS:
            parts.append(f"## Page {i + 1}\n\n{text}")
            report["kept_pages"] += 1
        else:
            # IMAGE page in a born-digital doc => advertisement / full-page figure => drop.
            report["dropped_pages"] += 1
    return "\n\n".join(parts), report

def chunk_text_by_chars(text, chunk_size=16000, overlap=1000):
    """Splits text into chunks of chunk_size characters with overlap."""
    if not text:
        return []
    if isinstance(text, list):
        text = "\n\n".join(text)
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if chunk_size <= overlap:
            overlap = int(chunk_size / 2)
        step = chunk_size - overlap
        if step <= 0:
            step = 1
        start += step
    return chunks

# --- Fidelity guard ---------------------------------------------------------
# The "structuring" step must only REFORMAT raw text, never summarize or chat.
# Small/instruct LLMs frequently ignore that and emit summaries or conversational
# filler ("Here's a summary...", "Let me know if..."). Accepting such output
# silently replaces the real article with a paraphrase. These markers + a
# length-ratio check catch that; on failure we fall back to the RAW extracted
# text (the faithful source of truth) tagged with #structuring_rejected.
_STRUCTURING_CHATTER_MARKERS = [
    "let me know", "here's a summary", "here is a summary", "i'll summarize",
    "i will summarize", "let me summarize", "as an ai", "i hope this helps",
    "feel free to ask", "in summary,", "to summarize", "let me break",
    "i've summarized", "if you'd like me to", "would you like me to",
    "i can summarize", "here's the summary", "here is the summary",
    "i'll provide a summary", "i'll break it down", "here's a breakdown",
    "this is a summary", "i have summarized", "let me clarify",
]

_FIDELITY_MIN_RATIO = 0.5  # content-length ratio below which a structured chunk is rejected

def set_fidelity_min_ratio(value):
    """Set the default fidelity threshold used by the structuring guard. Called once
    per run (from process_documents_generator) so a config value can tune rejection
    strictness without editing code. Ignores out-of-range/invalid input."""
    global _FIDELITY_MIN_RATIO
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if 0 < v <= 1:
        _FIDELITY_MIN_RATIO = v

def _content_len(s):
    """Length counting only alphanumeric characters — the actual content, ignoring
    whitespace, punctuation and Markdown syntax (#, *, |, -). Reformatting barely
    changes this; summarizing/omitting text reduces it sharply. Unicode-aware, so
    non-Latin scripts count as content too."""
    return sum(1 for c in (s or "") if c.isalnum())

def _validate_structured_chunk(structured, raw, min_ratio=None):
    """Return (ok: bool, reason: str). Rejects summarized/chatty LLM output so the
    pipeline can fall back to the faithful raw extraction. `min_ratio` defaults to the
    configurable module-level _FIDELITY_MIN_RATIO when not explicitly passed.

    The length check compares *content* (alphanumeric) characters, NOT raw length.
    Multi-column newspaper text layers are ~60% whitespace/punctuation for column
    positioning; collapsing that whitespace is exactly what restructuring should do,
    yet it nearly halves the raw character count with zero content loss. Measuring raw
    length there caused large numbers of faithful chunks to be falsely rejected. Content
    length is stable under reformatting and still drops sharply when text is summarized."""
    if min_ratio is None:
        min_ratio = _FIDELITY_MIN_RATIO
    if not structured or not structured.strip():
        return False, "empty output"
    low = structured.lower()
    for marker in _STRUCTURING_CHATTER_MARKERS:
        if marker in low:
            return False, f"chatter marker '{marker}'"
    raw_len = _content_len(raw)
    out_len = _content_len(structured)
    if raw_len > 0 and out_len < min_ratio * raw_len:
        return False, f"content too short ({out_len}/{raw_len} = {out_len/raw_len:.0%} < {min_ratio:.0%}) — likely summarized"
    return True, "ok"

def _accept_or_fallback(structured, raw, idx):
    """Validate a structured chunk; return either it (if faithful) or a raw-text
    fallback block tagged for later review."""
    ok, reason = _validate_structured_chunk(structured, raw)
    if ok:
        return structured
    return (f"> [!WARNING]\n> Structuring rejected for chunk {idx} ({reason}). "
            f"Preserving RAW extracted text below. #structuring_rejected\n\n{raw}")

def structure_text_with_gemini(raw_text, api_key, model_id, prompt_template=None, chunk_size=16000, overlap=1000, progress_callback=None):
    """Chunks raw OCR text by characters with overlap and uses Gemini to format it into structured Markdown."""
    global _gemini_quota_exhausted
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        chunks = chunk_text_by_chars(raw_text, chunk_size, overlap)
        if progress_callback:
            progress_callback(f"Splitting text into {len(chunks)} chunks for Gemini...")
        structured_chunks = []
        
        default_prompt = "You are an expert editor. Please format and restructure the following raw OCR text (from a newspaper/document) into clean, readable Markdown. Fix broken columns, merge broken sentences, add logical headings, and remove random page numbers or footer artifacts. Do not summarize or omit information; preserve the full article content. Output only the Markdown."
        system_prompt = prompt_template if prompt_template else default_prompt
        
        for i, chunk_text in enumerate(chunks):
            if _gemini_quota_exhausted:
                structured_chunks.append(f"> [!WARNING]\n> Gemini daily quota exhausted. Raw text below:\n\n{chunk_text}\n\n#gemini_exhausted")
                continue
            
            if progress_callback:
                progress_callback(f"Restructuring chunk {i+1} of {len(chunks)} via Gemini...")
            prompt = f"{system_prompt}\n\nRAW TEXT:\n{chunk_text}"
            
            try:
                _wait_for_gemini_rate_limit()
                from google.genai import types
                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,  # reformatting is deterministic — minimise drift/chatter
                        safety_settings=[
                            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        ]
                    )
                )
                if response and response.text:
                    structured_chunks.append(_accept_or_fallback(response.text, chunk_text, i+1))
                else:
                    structured_chunks.append(f"> [!WARNING]\n> Gemini returned empty text for chunk {i+1}. Raw text below:\n\n{chunk_text}")
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    _gemini_quota_exhausted = True
                    structured_chunks.append(f"> [!WARNING]\n> Gemini daily quota exhausted. Raw text below:\n\n{chunk_text}\n\n#gemini_exhausted")
                else:
                    structured_chunks.append(f"> [!ERROR]\n> Gemini text structuring failed for chunk {i+1}.\n> Error: {str(e)}\n\n{chunk_text}")
                
        return "\n\n---\n\n".join(structured_chunks)
    except Exception as e:
        return f"> [!ERROR]\n> Critical Gemini API Initialization Error: {str(e)}\n\n" + str(raw_text)

def structure_text_with_ollama(raw_text, model_id, host="http://localhost:11434", prompt_template=None, chunk_size=16000, overlap=1000, progress_callback=None):
    """Chunks raw OCR text by characters with overlap and uses a local Ollama model to format it into structured Markdown."""
    try:
        import requests
        
        chunks = chunk_text_by_chars(raw_text, chunk_size, overlap)
        if progress_callback:
            progress_callback(f"Splitting text into {len(chunks)} chunks for Ollama...")
        structured_chunks = []
        
        default_prompt = "You are an expert editor. Please format and restructure the following raw OCR text (from a newspaper/document) into clean, readable Markdown. Fix broken columns, merge broken sentences, add logical headings, and remove random page numbers or footer artifacts. Do not summarize or omit information; preserve the full article content. Output only the Markdown."
        system_prompt = prompt_template if prompt_template else default_prompt
        
        for i, chunk_text in enumerate(chunks):
            if progress_callback:
                progress_callback(f"Restructuring chunk {i+1} of {len(chunks)} via Ollama ({model_id})...")
            prompt = f"{system_prompt}\n\nRAW TEXT:\n{chunk_text}"
            
            url = f"{host}/api/generate"
            payload = {
                "model": model_id,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0
                }
            }

            try:
                response = requests.post(url, json=payload, timeout=300)
                response.raise_for_status()
                res_data = response.json()
                response_text = res_data.get("response", "").strip()
                if response_text:
                    structured_chunks.append(_accept_or_fallback(response_text, chunk_text, i+1))
                else:
                    structured_chunks.append(f"> [!WARNING]\n> Ollama returned empty text for chunk {i+1}. Raw text below:\n\n{chunk_text}")
            except Exception as e:
                structured_chunks.append(f"> [!ERROR]\n> Ollama text structuring failed for chunk {i+1}.\n> Error: {str(e)}\n\n{chunk_text}")
                
        return "\n\n---\n\n".join(structured_chunks)
    except Exception as e:
        return f"> [!ERROR]\n> Critical Ollama API Error: {str(e)}\n\n" + str(raw_text)

def structure_text_with_ollama_vision(pdf_path, model_id="glm-ocr:latest", host="http://localhost:11434",
                                       prompt_template=None, max_dim_px=1600, progress_callback=None):
    """
    Extracts text directly from PDF page images using a vision-capable Ollama OCR
    model (e.g. glm-ocr). Unlike structure_text_with_ollama, this sends the actual
    page image via /api/chat — OCR-specialist vision models produce garbled,
    hallucinated text if given only a text prompt with no image to read.

    glm-ocr specifically: it is not instruction-following — it only transcribes
    correctly when prompted with the literal trigger "OCR:" (a full English
    instruction makes it hallucinate a description instead of reading the page).
    It also crashes the Ollama runner on very large images (e.g. raw 150 DPI
    broadsheet scans, ~4500x7000px), so pages are downscaled to max_dim_px first.
    """
    import base64
    import requests

    doc = fitz.open(pdf_path)
    default_prompt = "OCR:"
    prompt = prompt_template if prompt_template else default_prompt

    extracted_pages = []
    total = len(doc)
    for i in range(total):
        page = doc[i]
        rect = page.rect
        long_side = max(rect.width, rect.height) or 1
        scale = max_dim_px / long_side
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")

        if progress_callback:
            progress_callback(f"OCR page {i+1} of {total} via {model_id} (Ollama vision)...")

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            response = requests.post(f"{host}/api/chat", json=payload, timeout=180)
            response.raise_for_status()
            text = response.json().get("message", {}).get("content", "").strip()
            extracted_pages.append(text if text else f"> [!WARNING]\n> Page {i+1} returned empty content.")
        except Exception as e:
            extracted_pages.append(f"> [!ERROR]\n> Page {i+1} OCR failed: {str(e)}")

    return "\n\n---\n\n".join(f"## Page {i+1}\n\n{t}" for i, t in enumerate(extracted_pages))

_nuextract_model = None
_nuextract_processor = None
_nuextract_model_id = None
_nuextract_lock = threading.RLock()

def structure_text_with_nuextract(pdf_path, model_id="numind/NuExtract3-mlx-4bits", prompt_template=None, progress_callback=None):
    """
    Extracts text and formats it directly from PDF page images using NuExtract 3 (Apple Silicon VLM via mlx-vlm).
    Bypasses traditional OCR and general LLMs.
    """
    global _nuextract_model, _nuextract_processor, _nuextract_model_id
    import tempfile
    import shutil
    
    # 1. Convert PDF pages to temporary images
    temp_dir = tempfile.mkdtemp()
    temp_image_paths = []
    
    try:
        doc = fitz.open(pdf_path)
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=150) # 150 DPI is standard and fast for VLMs
            img_path = os.path.join(temp_dir, f"page_{page_idx}.png")
            pix.save(img_path)
            temp_image_paths.append(img_path)
        
        if progress_callback:
            progress_callback(f"✓ PDF converted to {len(temp_image_paths)} page images. Preparing NuExtract 3...")
            
        # 2. Dynamic import and load of mlx-vlm
        with _nuextract_lock:
            if _nuextract_model is None or _nuextract_model_id != model_id:
                if progress_callback:
                    progress_callback(f"Loading {model_id} onto GPU (lazy-loading)...")
                from mlx_vlm import load as mlx_load
                _nuextract_model, _nuextract_processor = mlx_load(model_id)
                _nuextract_model_id = model_id
                if progress_callback:
                    progress_callback("✓ NuExtract 3 loaded successfully.")
                    
        # 3. Import vlm modules
        from mlx_vlm import generate as mlx_generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
        
        config = load_config(model_id)
        
        # Prepare system instructions / schema prompt
        default_prompt = (
            "You are an advanced, specialized Document Parsing Assistant. Your task is to convert the provided "
            "document page image into a high-fidelity, logically structured Markdown representation. Read the "
            "document as a human would (column-by-column for multi-column layouts). Do not summarize, rephrase, "
            "or correct grammar. Output only the Markdown."
        )
        system_prompt = prompt_template if prompt_template else default_prompt
        
        extracted_pages = []
        for i, img_path in enumerate(temp_image_paths):
            if progress_callback:
                progress_callback(f"Restructuring page {i+1} of {len(temp_image_paths)} via NuExtract 3 VLM...")
                
            formatted_prompt = apply_chat_template(
                _nuextract_processor,
                config,
                prompt=system_prompt,
                num_images=1
            )
            
            try:
                output = mlx_generate(
                    model=_nuextract_model,
                    processor=_nuextract_processor,
                    image=img_path,
                    prompt=formatted_prompt,
                    max_tokens=2000,
                    temp=0.1 # Low temperature for accurate factual parsing
                )
                generated_text = ""
                if output:
                    if hasattr(output, 'text') and output.text:
                        generated_text = output.text.strip()
                    elif isinstance(output, str):
                        generated_text = output.strip()
                
                if generated_text:
                    extracted_pages.append(generated_text)
                else:
                    extracted_pages.append(f"> [!WARNING]\n> Page {i+1} returned empty content.")
            except Exception as e:
                extracted_pages.append(f"> [!ERROR]\n> Page {i+1} extraction failed: {str(e)}")
                
        return "\n\n---\n\n".join(extracted_pages)
        
    except Exception as e:
        return f"> [!ERROR]\n> Critical NuExtract 3 VLM pipeline error: {str(e)}"
        
    finally:
        # Cleanup temporary files
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

def extract_text_from_pdf_with_gemini(pdf_path, api_key, model_id):
    global _gemini_quota_exhausted
    if _gemini_quota_exhausted:
        return "Gemini OCR Failed: Quota Exhausted\n\n#gemini_exhausted"
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # Copy to a temporary file with a safe ascii name to avoid httpx unicode encode errors
        fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="gemini_upload_")
        os.close(fd)
        shutil.copy2(pdf_path, temp_path)
        
        try:
            myfile = client.files.upload(file=temp_path)
            prompt = "Extract the complete text from this document. Maintain the structural layout, headings, and paragraphs. Do not add any summary or extra commentary."
            
            _wait_for_gemini_rate_limit()
            from google.genai import types
            response = client.models.generate_content(
                model=model_id,
                contents=[prompt, myfile]
            )
            
            try:
                client.files.delete(name=myfile.name)
            except:
                pass
                
            if response and response.text:
                return response.text
            return ""
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
            _gemini_quota_exhausted = True
            return "Gemini OCR Failed: Quota Exhausted\n\n#gemini_exhausted"
        return f"Gemini OCR Failed: {str(e)}"

def extract_text_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        return f"Error extracting DOCX: {str(e)}"

_mlx_model_cache = None

def generate_document_title(content, filename, engine="gemini", gemini_key=None, gemini_model="gemini-1.5-flash", ollama_model=None):
    """Generates a short, relevant title for the document using the configured active LLM engine, falling back to MLX or filename."""
    sample_text = content[:3000]
    prompt = f"""You are an expert librarian. I will provide you with the beginning of a document. 
Your task is to generate a short, highly relevant, and professional title for this document.
The title must be under 10 words. Do NOT include quotes, brackets, or any conversational text. Just output the title.

Document Content:
{sample_text}

Title:"""

    # If engine is NuExtract, choose Gemini or Ollama as the active generation engine if available
    effective_engine = engine
    if engine == "nuextract":
        if gemini_key:
            effective_engine = "gemini"
        elif ollama_model:
            effective_engine = "ollama"

    # 1. Try Ollama
    if effective_engine == "ollama" and ollama_model:
        try:
            import requests
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            }
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                title = res.json().get("response", "").strip()
                clean = title.strip().strip('"').strip("'").strip('*')
                if clean and len(clean) < 100:
                    return clean
        except Exception as e:
            print(f"Ollama title generation failed: {e}")

    # 2. Try Gemini
    elif engine == "gemini" and gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt
            )
            if response and response.text:
                clean = response.text.strip().strip('"').strip("'").strip('*')
                if clean and len(clean) < 100:
                    return clean
        except Exception as e:
            print(f"Gemini title generation failed: {e}")

    # 3. Fallback: MLX local model
    try:
        from mlx_lm import load, generate
        model_id = "mlx-community/Llama-3.2-1B-Instruct-4bit"
        global _mlx_model_cache
        if _mlx_model_cache is None:
            _mlx_model_cache = load(model_id)
        model, tokenizer = _mlx_model_cache
        
        messages = [
            {"role": "system", "content": "You are a precise assistant that outputs only document titles and nothing else. Do not use quotes or markdown."},
            {"role": "user", "content": prompt}
        ]
        try:
            text_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            text_prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\nYou are a precise assistant that outputs only document titles.<|eot_id|><|start_header_id|>user<|end_header_id|>\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
            
        response = generate(model, tokenizer, prompt=text_prompt, max_tokens=20, verbose=False)
        clean_title = response.strip().strip('"').strip("'").strip('*')
        if clean_title and len(clean_title) < 100:
            return clean_title
    except Exception as e:
        print(f"MLX Title Generation failed: {e}")
        
    return os.path.splitext(filename)[0]

def get_harvested_sources(output_dir):
    """Scans the vault to build a set of original filenames that have already been harvested."""
    harvested = set()
    if not os.path.exists(output_dir):
        return harvested
    for root, dirs, files in os.walk(output_dir):
        # Prune hidden directories like .obsidian and .git
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if '_Library_' in file and file.endswith('.md'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for _ in range(15):  # Check first 15 lines for frontmatter
                            line = f.readline()
                            if not line: break
                            if line.startswith('source: '):
                                source_val = line.replace('source: ', '').strip().strip('"').strip("'")
                                harvested.add(source_val)
                                break
                except Exception:
                    pass
    return harvested

def get_file_mtime_date(filepath):
    """Returns the modification date of a file in YYYYMMDD format."""
    mtime = os.path.getmtime(filepath)
    return datetime.datetime.fromtimestamp(mtime).strftime('%Y%m%d')

def generate_obsidian_markdown(content, title, source, date, metadata=None):
    """Generates structured Obsidian Markdown with frontmatter."""
    meta_lines = []
    if metadata:
        if metadata.get('authors'):
            authors_val = metadata['authors']
            if isinstance(authors_val, list):
                authors_val = ", ".join(authors_val)
            meta_lines.append(f'authors: "{authors_val}"')
        if metadata.get('abstract'):
            abstract_val = metadata['abstract'].replace('\n', ' ').replace('"', '\\"')
            meta_lines.append(f'abstract: "{abstract_val}"')
        if metadata.get('keywords'):
            kw_val = metadata['keywords']
            if isinstance(kw_val, list):
                meta_lines.append(f'keywords: {json.dumps(kw_val)}')
            else:
                meta_lines.append(f'keywords: "{kw_val}"')
                
    meta_str = "\n".join(meta_lines)
    if meta_str:
        meta_str = "\n" + meta_str
        
    return f"""---
title: "{title}"
source: "{source}"
date: {date}{meta_str}
tags: [document, library, samvit]
---

# {title}

**Original Source:** {source}
**Date:** {date}
**Imported On:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{content}
"""

import queue
from concurrent.futures import ThreadPoolExecutor

def process_file_worker(file_info, input_dir, output_dir, gemini_key, gemini_model, engine, ollama_model, prompt_template, chunk_size, overlap, harvested_sources, progress_queue, file_index, total_files, nuextract_model=None, archive_processed=False, auto_restructure_ollama=False):
    filename = file_info["name"]
    input_path = file_info["path"]
    
    if filename in harvested_sources:
        progress_queue.put(json.dumps({"message": _format_log_message(f"✓ {filename} found in vault. Skipping."), "type": "info", "progress": int((file_index+1)/total_files*100)}) + "\n")
        return
        
    progress_queue.put(json.dumps({"message": _format_log_message(f"Processing: {filename}..."), "current_file": filename, "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
    
    try:
        ext = os.path.splitext(filename)[1].lower()
        content = ""
        metadata = {}
        
        if ext == '.pdf':
            if engine == "auto":
                # AUTO-ROUTER: classify pages and pick the engine per document.
                # Born-digital (WSJ/BS/RBI/HBR) -> faithful text layer (ads dropped);
                # image-format (FT) -> NuExtract VLM-OCR. No manual engine switching.
                def local_callback(msg):
                    progress_queue.put(json.dumps({
                        "message": _format_log_message(msg),
                        "type": "info",
                        "progress": int((file_index)/total_files*100)
                    }) + "\n")
                content, _rr = route_and_extract(
                    input_path,
                    nuextract_model=(nuextract_model or "numind/NuExtract3-mlx-4bits"),
                    progress_callback=local_callback,
                    restructure_with_ollama=(auto_restructure_ollama and bool(ollama_model)),
                    ollama_model=ollama_model,
                    prompt_template=prompt_template,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                progress_queue.put(json.dumps({
                    "message": _format_log_message(
                        f"✓ Router: {_rr['mode']} → {_rr.get('engine','?')}; "
                        f"kept {_rr['kept_pages']}/{_rr['pages']} pages, "
                        f"dropped {_rr['dropped_pages']} ad/image pages"),
                    "type": "info",
                    "progress": int((file_index)/total_files*100)
                }) + "\n")
            elif engine == "nuextract":
                def local_callback(msg):
                    progress_queue.put(json.dumps({
                        "message": _format_log_message(msg),
                        "type": "info",
                        "progress": int((file_index)/total_files*100)
                    }) + "\n")
                content = structure_text_with_nuextract(
                    input_path, 
                    model_id=nuextract_model if nuextract_model else "numind/NuExtract3-mlx-4bits", 
                    prompt_template=prompt_template, 
                    progress_callback=local_callback
                )
            elif engine == "docling":
                progress_queue.put(json.dumps({"message": _format_log_message(f"Using Docling for {filename}..."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
                content, metadata = extract_text_with_docling(input_path)
                if content.startswith("Docling Extraction Failed"):
                    progress_queue.put(json.dumps({"message": _format_log_message(f"Docling failed. Falling back to native PDF extraction + LLM structuring for {filename}..."), "type": "warning"}) + "\n")
                    content = ""  # Force native/OCR flow below
                elif content:
                    # Classify the PDF to detect if it is scanned (image-based) or born-digital.
                    # Docling already OCR's scanned pages on-device via Apple Vision (OcrMacOptions,
                    # see extract_text_with_docling) — that text is already the faithful source, so
                    # for scanned docs we preserve it as-is instead of routing it through an LLM
                    # "structuring" pass (that step previously fed Vision-OCR'd text to glm-ocr, a
                    # vision-only OCR model with no text-editing ability, which hallucinated wrong
                    # facts). Gemini remains available as an explicit opt-in for readers who want
                    # cleaner formatting and are OK paying for it.
                    is_scanned = False
                    try:
                        pdf_info = classify_pdf(input_path)
                        if pdf_info["mode"] == "SCANNED":
                            is_scanned = True
                    except Exception as ce:
                        print(f"Error classifying PDF for docling post-processing: {ce}")

                    def local_callback(msg):
                        progress_queue.put(json.dumps({
                            "message": _format_log_message(msg),
                            "type": "info",
                            "progress": int((file_index)/total_files*100)
                        }) + "\n")

                    if is_scanned:
                        if engine == "gemini" and gemini_key and not _gemini_quota_exhausted:
                            progress_queue.put(json.dumps({"message": _format_log_message(f"✓ Docling extracted text (scanned PDF). Restructuring with Gemini..."), "type": "info", "progress": int((file_index)/total_files*100), "gemini_stats": get_gemini_stats()}) + "\n")
                            content = structure_text_with_gemini(content, gemini_key, gemini_model, prompt_template=prompt_template, chunk_size=chunk_size, overlap=overlap, progress_callback=local_callback)
                        else:
                            progress_queue.put(json.dumps({"message": _format_log_message(f"✓ Docling extracted text via on-device OCR (scanned PDF). Preserving as-is for fidelity."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
                    else:
                        progress_queue.put(json.dumps({"message": _format_log_message(f"✓ Docling extracted text (born-digital PDF). Preserving original extraction without LLM restructuring."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
            
            if not content: # If docling wasn't used or failed
                pages = extract_text_from_pdf(input_path)
                
                if isinstance(pages, list):
                    actual_text = "".join(p.split("\n\n", 1)[1] if "\n\n" in p else p for p in pages).strip()
                    # Detect scanned/unusable-text-layer PDFs via the router's printable-aware
                    # classifier, NOT raw length. Some publishers (e.g. Indian Express) embed
                    # non-Unicode fonts so the text layer is long but pure glyph-code gibberish;
                    # a naive length check would treat it as born-digital and feed junk to the
                    # LLM. classify_pdf() counts only printable chars, so such docs come back
                    # SCANNED and get routed to OCR. Fall back to the length check if it errors.
                    try:
                        is_scanned = classify_pdf(input_path)["mode"] == "SCANNED"
                    except Exception as ce:
                        print(f"Error classifying PDF in native fallback: {ce}")
                        is_scanned = len(actual_text) < 50
                    is_ollama_active = (engine == "ollama") or (engine != "gemini" and ollama_model)

                    def local_callback(msg):
                        progress_queue.put(json.dumps({
                            "message": _format_log_message(msg),
                            "type": "info",
                            "progress": int((file_index)/total_files*100)
                        }) + "\n")

                    if is_scanned:
                        # Native text layer is empty -> scanned/image-based PDF. Use on-device Apple
                        # Vision OCR (fast, free, faithful) rather than a vision-LLM OCR pass: small
                        # OCR-specialist models (e.g. glm-ocr) hallucinate wrong facts on dense
                        # newsprint instead of just misreading characters, which is worse for an archive.
                        progress_queue.put(json.dumps({"message": _format_log_message(f"Native extraction yielded no text (scanned PDF). Running on-device macOS OCR for {filename}..."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
                        pages = extract_text_from_pdf_with_ocrmac(input_path)

                    if isinstance(pages, list) and not content:
                        if is_scanned:
                            # Vision-OCR'd text is already the faithful source; only Gemini (a real
                            # general-purpose LLM) gets to reformat it, and only when explicitly chosen.
                            if engine == "gemini" and gemini_key and not _gemini_quota_exhausted:
                                progress_queue.put(json.dumps({"message": _format_log_message(f"✓ PDF extracted ({len(pages)} pages). Restructuring with Gemini..."), "type": "info", "progress": int((file_index)/total_files*100), "gemini_stats": get_gemini_stats()}) + "\n")
                                content = structure_text_with_gemini(pages, gemini_key, gemini_model, prompt_template=prompt_template, chunk_size=chunk_size, overlap=overlap, progress_callback=local_callback)
                            else:
                                content = "\n\n".join(pages)
                        elif is_ollama_active and ollama_model:
                            progress_queue.put(json.dumps({"message": _format_log_message(f"✓ PDF extracted ({len(pages)} pages). Structuring with Ollama ({ollama_model})..."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
                            content = structure_text_with_ollama(pages, ollama_model, prompt_template=prompt_template, chunk_size=chunk_size, overlap=overlap, progress_callback=local_callback)
                        elif gemini_key and not _gemini_quota_exhausted:
                            progress_queue.put(json.dumps({"message": _format_log_message(f"✓ PDF extracted ({len(pages)} pages). Structuring with Gemini..."), "type": "info", "progress": int((file_index)/total_files*100), "gemini_stats": get_gemini_stats()}) + "\n")
                            content = structure_text_with_gemini(pages, gemini_key, gemini_model, prompt_template=prompt_template, chunk_size=chunk_size, overlap=overlap, progress_callback=local_callback)
                        else:
                            content = "\n\n".join(pages)

            # Extraction-succeeded guard: every branch above (auto-router, docling,
            # nuextract, native+OCR fallback) is expected to yield substantial text for
            # a real PDF. If OCR/LLM structuring silently comes back empty or near-empty
            # (e.g. Apple Vision returning no annotations under thread contention when
            # several PDFs OCR concurrently — observed with Indian Express editions),
            # writing the note anyway is worse than doing nothing: the note's
            # `source:` frontmatter makes get_harvested_sources() treat the file as
            # permanently done, so a blank/garbled note can never be retried and the
            # failure repeats silently on every future run. Raising here instead keeps
            # the raw PDF in place so the next run retries it.
            page_count = len(fitz.open(input_path))
            usable_len = _content_len(re.sub(r'^## Page \d+$', '', content, flags=re.MULTILINE))
            min_expected = max(200, 30 * page_count)
            if usable_len < min_expected:
                raise ValueError(
                    f"Extraction produced insufficient content ({usable_len} usable chars "
                    f"across {page_count} pages, expected >= {min_expected}) — likely a "
                    f"silent OCR/extraction failure. Leaving raw file for retry."
                )

        elif ext == '.docx':
            content = extract_text_from_docx(input_path)
        elif ext == '.tex' or (filename.endswith('_source.tar.gz') and engine == 'latex'):
            if filename.endswith('.tar.gz'):
                pass
            else:
                content = extract_text_with_pypandoc(input_path, format='latex')
        elif ext in ('.txt', '.md'):
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

        # Generate dynamic title
        progress_queue.put(json.dumps({"message": _format_log_message(f"Generating smart title for {filename} via active LLM..."), "type": "info", "progress": int((file_index)/total_files*100)}) + "\n")
        generated_title = generate_document_title(content, filename, engine=engine, gemini_key=gemini_key, gemini_model=gemini_model, ollama_model=ollama_model)
        safe_title = sanitize_filename(generated_title)
        
        doc_date = get_file_mtime_date(input_path)
        md_filename = f"{doc_date}_Library_{safe_title}.md"
        output_path = os.path.join(output_dir, md_filename)
        
        markdown_content = generate_obsidian_markdown(content, generated_title, filename, doc_date, metadata=metadata)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Auto-archive if requested
        if archive_processed:
            try:
                import shutil
                processed_dir = os.path.join(input_dir, "Processed")
                os.makedirs(processed_dir, exist_ok=True)
                shutil.move(input_path, os.path.join(processed_dir, filename))
                progress_queue.put(json.dumps({"message": _format_log_message(f"Moved raw file to: {os.path.join(processed_dir, filename)}"), "type": "info", "progress": int((file_index+1)/total_files*100)}) + "\n")
            except Exception as move_err:
                progress_queue.put(json.dumps({"message": _format_log_message(f"Failed to archive raw file: {str(move_err)}"), "type": "warning", "progress": int((file_index+1)/total_files*100)}) + "\n")

        progress_queue.put(json.dumps({"message": _format_log_message(f"✓ Successfully converted {filename}"), "type": "success", "progress": int((file_index+1)/total_files*100)}) + "\n")
    except Exception as e:
        progress_queue.put(json.dumps({"message": _format_log_message(f"Failed to convert {filename}: {str(e)}"), "type": "error"}) + "\n")

def process_documents_generator(input_dir, output_dir, gemini_key=None, gemini_model="gemini-1.5-flash", target_files=None, engine="gemini", ollama_model=None, prompt_template=None, chunk_size=16000, overlap=1000, nuextract_model=None, archive_processed=False, auto_restructure_ollama=False, fidelity_min_ratio=0.5):
    """
    Generator that processes documents in parallel and yields status updates.
    Processes files in chronological order (Oldest -> Newest).
    If target_files is provided (list of filenames), only those files will be processed.
    """
    # Apply the configurable fidelity threshold for the whole run (read-only during
    # the threaded processing below, so it's safe to set once here).
    set_fidelity_min_ratio(fidelity_min_ratio)

    if not os.path.exists(input_dir):
        yield json.dumps({"message": _format_log_message(f"Raw material directory not found: {input_dir}"), "type": "error"}) + "\n"
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
 
    supported_extensions = ('.pdf', '.docx', '.txt', '.md')
    
    # Get all files and their modification times
    all_files = []
    for f in os.listdir(input_dir):
        if f.lower().endswith(supported_extensions):
            if target_files is not None and f not in target_files:
                continue
            full_path = os.path.join(input_dir, f)
            all_files.append({"name": f, "path": full_path, "mtime": os.path.getmtime(full_path)})
            
    # Sort files by modification time (Oldest -> Newest)
    all_files.sort(key=lambda x: x["mtime"])
    
    files_to_process = all_files
    
    if not files_to_process:
        yield json.dumps({"message": _format_log_message("No compatible documents found in raw folder."), "type": "info", "progress": 100}) + "\n"
        return
 
    yield json.dumps({"message": _format_log_message(f"Analyzing {len(files_to_process)} documents for parallel ingestion..."), "type": "info"}) + "\n"
    
    harvested_sources = get_harvested_sources(output_dir)
    progress_queue = queue.Queue()
    total_files = len(files_to_process)
    
    # For local engines (Ollama, Docling, and NuExtract), we serialize document processing (max_workers=1)
    # to avoid concurrent local model execution which causes high memory contention and timeouts.
    # Auto mode with local Ollama restructuring also runs a local model per doc, so serialize
    # it too to avoid concurrent Ollama execution (memory contention / timeouts).
    if engine in ("ollama", "docling", "nuextract") or (engine == "auto" and auto_restructure_ollama and ollama_model):
        max_workers = 1
    else:
        max_workers = min(3, total_files)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for idx, file_info in enumerate(files_to_process):
            futures.append(executor.submit(
                process_file_worker,
                file_info, input_dir, output_dir,
                gemini_key, gemini_model, engine, ollama_model,
                prompt_template, chunk_size, overlap,
                harvested_sources, progress_queue, idx, total_files,
                nuextract_model, archive_processed, auto_restructure_ollama
            ))
            
        import time
        # Poll the queue while threads are running or items are pending
        while any(f.running() for f in futures) or not progress_queue.empty():
            try:
                msg = progress_queue.get(timeout=0.1)
                yield msg
            except queue.Empty:
                time.sleep(0.05)
                
        # Drain any remaining logs
        while not progress_queue.empty():
            yield progress_queue.get()

def get_document_stats(input_dir, output_dir=None):
    """
    Returns number of pending documents and list of pending filenames in the input folder.
    Now performs an 'already synced' check using the frontmatter source.
    """
    if not os.path.exists(input_dir):
        return 0, []
        
    supported_extensions = ('.pdf', '.docx', '.txt', '.md')
    files = [f for f in os.listdir(input_dir) if f.lower().endswith(supported_extensions)]
    
    if not output_dir:
        return len(files), files
        
    harvested_sources = get_harvested_sources(output_dir)
        
    pending_files = []
    for f in files:
        if f not in harvested_sources:
            pending_files.append(f)

    return len(pending_files), pending_files


# ---------------------------------------------------------------------------
# CLI dry-run:  python doc_processor.py --classify FILE.pdf [FILE2.pdf ...]
# Prints the per-page verdict + chosen engine WITHOUT extracting or writing.
# Use it to sanity-check the router (and tune the thresholds) on a sample of
# each publisher before trusting it.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--classify":
        targets = args[1:]
        if not targets:
            print("usage: python doc_processor.py --classify FILE.pdf [...]")
            sys.exit(2)
        for path in targets:
            try:
                info = classify_pdf(path)
            except Exception as e:
                print(f"\n{os.path.basename(path)}\n  ERROR: {e}")
                continue
            print(f"\n{os.path.basename(path)}")
            print(f"  MODE={info['mode']}  ENGINE={info['engine']}  "
                  f"pages={info['pages']}  image_share={info['image_share']:.0%}")
            counts = {}
            for p in info["page_detail"]:
                counts[p["kind"]] = counts.get(p["kind"], 0) + 1
            print(f"  page kinds: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            # show first few pages' detail
            for p in info["page_detail"][:6]:
                print(f"    p{p['page']:>3}: {p['kind']:<6} chars={p['chars']:<6} img_ratio={p['img_ratio']}")
            if info["pages"] > 6:
                print(f"    ... ({info['pages'] - 6} more pages)")
        sys.exit(0)
    print("doc_processor.py — library module. Use --classify FILE.pdf for the router dry-run.")
