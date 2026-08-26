"""Unified multi-source research harvester.

Aggregates academic paper search across several free HTTP APIs behind a single
interface, returning results in a normalized schema so the front-end and the
harvest pipeline don't need to care which source a paper came from.

Sources:
  - arXiv              (via ArxivHarvester)
  - Semantic Scholar   (graph API, no key)
  - OpenAlex           (open API, polite pool via mailto)
  - CrossRef           (metadata API, polite pool via mailto)

Every result carries a source-prefixed ``id`` (e.g. ``arxiv:2401.01234``,
``openalex:W123``, ``doi:10.1234/xyz``) so ``get_pdf`` / harvest can dispatch
back to the right backend.
"""

import os
import re
import json
import time
import logging
import datetime

import requests

from arxiv_harvester import ArxivHarvester

logger = logging.getLogger(__name__)

# Default contact for the OpenAlex / CrossRef "polite pool" (faster, more
# reliable responses). Overridable via config["research_contact_email"].
DEFAULT_CONTACT_EMAIL = "civam.caushik@gmail.com"

USER_AGENT = "SamvitResearchHarvester/1.0 (mailto:{email})"

# Canonical source keys used across the module and API.
SOURCE_ARXIV = "arxiv"
SOURCE_S2 = "semantic_scholar"
SOURCE_OPENALEX = "openalex"
SOURCE_CROSSREF = "crossref"
ALL_SOURCES = [SOURCE_ARXIV, SOURCE_S2, SOURCE_OPENALEX, SOURCE_CROSSREF]


def _norm_title(title):
    """Normalize a title for dedup: lowercase alphanumerics only."""
    return re.sub(r'[^a-z0-9]+', '', (title or '').lower())


def _clean_doi(doi):
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    return doi.lower() or None


def _strip_tags(text):
    """Strip HTML/JATS tags (CrossRef abstracts are JATS XML)."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _reconstruct_inverted_abstract(inverted):
    """OpenAlex returns abstracts as an inverted index {word: [positions]}."""
    if not inverted:
        return ""
    positions = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions))


class ResearchHarvester:
    def __init__(self, config_path="config.json", download_dir=None, arxiv=None):
        self.config = {}
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read config {config_path}: {e}")

        self.download_dir = download_dir or self.config.get("raw_material_path", "RawMaterials")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        self.contact_email = self.config.get("research_contact_email", DEFAULT_CONTACT_EMAIL)
        # Optional Semantic Scholar key lifts the shared keyless rate limit
        # (which frequently returns 429). Looked up in api_keys or top level.
        self.s2_api_key = (self.config.get("api_keys", {}).get("semantic_scholar")
                           or self.config.get("semantic_scholar_api_key", ""))
        self.arxiv = arxiv or ArxivHarvester(download_dir=self.download_dir)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT.format(email=self.contact_email)})

    # ── ID helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def parse_id(result_id):
        """Split a source-prefixed id into (source, native_id)."""
        if not result_id:
            return None, None
        if ':' in result_id:
            prefix, native = result_id.split(':', 1)
            mapping = {
                'arxiv': SOURCE_ARXIV,
                's2': SOURCE_S2,
                'openalex': SOURCE_OPENALEX,
                'doi': SOURCE_CROSSREF,
            }
            if prefix in mapping:
                return mapping[prefix], native
        # Bare id → assume arXiv (backwards compatible with old harvest calls).
        return SOURCE_ARXIV, result_id

    # ── Unified search ──────────────────────────────────────────────────────

    def search(self, query, sources=None, max_results=25, sort_by='relevance',
               year_from=None, year_to=None):
        """Search selected sources and return merged, de-duplicated results.

        Returns {"results": [...], "errors": [{"source", "message"}]}.
        """
        sources = sources or [SOURCE_ARXIV]
        sources = [s for s in sources if s in ALL_SOURCES]
        errors = []
        per_source = {}

        dispatch = {
            SOURCE_ARXIV: self._search_arxiv,
            SOURCE_S2: self._search_semantic_scholar,
            SOURCE_OPENALEX: self._search_openalex,
            SOURCE_CROSSREF: self._search_crossref,
        }

        for source in sources:
            try:
                per_source[source] = dispatch[source](
                    query, max_results=max_results, sort_by=sort_by,
                    year_from=year_from, year_to=year_to)
            except Exception as e:
                logger.warning(f"{source} search failed: {e}")
                errors.append({"source": source, "message": str(e)})
                per_source[source] = []

        merged = self._merge(per_source, sources, sort_by)
        merged = self._filter_years(merged, year_from, year_to)
        return {"results": merged, "errors": errors}

    def _filter_years(self, results, year_from, year_to):
        """Enforce the year range uniformly and drop implausible dates.

        Some sources (notably CrossRef) carry bogus far-future ``issued``
        dates that would otherwise dominate date-sorted results, so cap the
        upper bound at next year regardless of what a source returns.
        """
        plausible_upper = datetime.date.today().year + 1
        upper = min(int(year_to), plausible_upper) if year_to else plausible_upper
        lower = int(year_from) if year_from else None
        out = []
        for r in results:
            year = r.get('year')
            if year is None:
                out.append(r)
                continue
            if year > upper:
                continue
            if lower and year < lower:
                continue
            out.append(r)
        return out

    def _merge(self, per_source, sources, sort_by):
        """De-dup by DOI/title, then order. Prefer results that carry a PDF."""
        seen = {}
        order = []
        # Iterate round-robin so top hits from every source surface early
        # when sort_by == relevance.
        idx = 0
        remaining = True
        while remaining:
            remaining = False
            for source in sources:
                lst = per_source.get(source, [])
                if idx < len(lst):
                    remaining = True
                    r = lst[idx]
                    key = r.get('doi') or _norm_title(r.get('title'))
                    if not key:
                        order.append(r)
                        continue
                    if key in seen:
                        # Merge: keep a pdf_url / abstract if the winner lacks one.
                        kept = seen[key]
                        if not kept.get('pdf_url') and r.get('pdf_url'):
                            kept['pdf_url'] = r['pdf_url']
                        if not kept.get('summary') and r.get('summary'):
                            kept['summary'] = r['summary']
                        kept.setdefault('also_in', []).append(r['source'])
                    else:
                        seen[key] = r
                        order.append(r)
            idx += 1

        if sort_by in ('lastUpdatedDate', 'submittedDate', 'date'):
            order.sort(key=lambda r: r.get('published') or '', reverse=True)
        elif sort_by == 'citations':
            order.sort(key=lambda r: r.get('citation_count') or 0, reverse=True)
        return order

    # ── Per-source search implementations ───────────────────────────────────

    def _search_arxiv(self, query, max_results, sort_by, year_from, year_to):
        arxiv_sort = sort_by if sort_by in ('lastUpdatedDate', 'submittedDate') else 'relevance'
        raw = self.arxiv.search(query, max_results=max_results, sort_by=arxiv_sort) or []
        out = []
        for r in raw:
            year = None
            if r.get('published'):
                try:
                    year = int(r['published'][:4])
                except ValueError:
                    pass
            if not self._year_ok(year, year_from, year_to):
                continue
            out.append({
                "id": f"arxiv:{r['id']}",
                "source": SOURCE_ARXIV,
                "title": r.get('title', '').strip(),
                "authors": r.get('authors', []),
                "summary": (r.get('summary') or '').strip(),
                "published": r.get('published'),
                "year": year,
                "pdf_url": r.get('pdf_url'),
                "url": r.get('entry_id'),
                "doi": None,
                "venue": "arXiv",
                "categories": r.get('categories', []),
                "citation_count": None,
            })
        return out

    def _search_semantic_scholar(self, query, max_results, sort_by, year_from, year_to):
        fields = ("title,abstract,authors,year,publicationDate,externalIds,"
                  "openAccessPdf,url,venue,citationCount,fieldsOfStudy")
        params = {"query": query, "limit": min(max_results, 100), "fields": fields}
        if year_from or year_to:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        headers = {"x-api-key": self.s2_api_key} if self.s2_api_key else None
        data = self._get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search", params,
            headers=headers)
        out = []
        for p in (data.get("data") or []):
            ext = p.get("externalIds") or {}
            oa = p.get("openAccessPdf") or {}
            out.append({
                "id": f"s2:{p.get('paperId')}",
                "source": SOURCE_S2,
                "title": (p.get("title") or "").strip(),
                "authors": [a.get("name", "") for a in (p.get("authors") or [])],
                "summary": (p.get("abstract") or "").strip(),
                "published": p.get("publicationDate"),
                "year": p.get("year"),
                "pdf_url": oa.get("url"),
                "url": p.get("url"),
                "doi": _clean_doi(ext.get("DOI")),
                "venue": p.get("venue"),
                "categories": p.get("fieldsOfStudy") or [],
                "citation_count": p.get("citationCount"),
            })
        return out

    def _search_openalex(self, query, max_results, sort_by, year_from, year_to):
        params = {
            "search": query,
            "per_page": min(max_results, 200),
            "mailto": self.contact_email,
        }
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if sort_by in ('lastUpdatedDate', 'submittedDate', 'date'):
            params["sort"] = "publication_date:desc"
        elif sort_by == 'citations':
            params["sort"] = "cited_by_count:desc"

        data = self._get_json("https://api.openalex.org/works", params)
        out = []
        for w in (data.get("results") or []):
            best = w.get("best_oa_location") or {}
            oa = w.get("open_access") or {}
            prim = w.get("primary_location") or {}
            pdf = best.get("pdf_url") or oa.get("oa_url") or prim.get("pdf_url")
            out.append({
                "id": f"openalex:{(w.get('id') or '').split('/')[-1]}",
                "source": SOURCE_OPENALEX,
                "title": (w.get("title") or w.get("display_name") or "").strip(),
                "authors": [a.get("author", {}).get("display_name", "")
                            for a in (w.get("authorships") or [])],
                "summary": _reconstruct_inverted_abstract(
                    w.get("abstract_inverted_index")),
                "published": w.get("publication_date"),
                "year": w.get("publication_year"),
                "pdf_url": pdf,
                "url": (prim.get("landing_page_url")
                        or (f"https://doi.org/{_clean_doi(w.get('doi'))}"
                            if w.get("doi") else w.get("id"))),
                "doi": _clean_doi(w.get("doi")),
                "venue": (prim.get("source") or {}).get("display_name"),
                "categories": [c.get("display_name", "")
                               for c in (w.get("concepts") or [])[:5]],
                "citation_count": w.get("cited_by_count"),
            })
        return out

    def _search_crossref(self, query, max_results, sort_by, year_from, year_to):
        params = {
            "query": query,
            "rows": min(max_results, 100),
            "mailto": self.contact_email,
            "select": ("DOI,title,author,issued,container-title,URL,"
                       "is-referenced-by-count,abstract,link"),
        }
        filters = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}-01-01")
        if year_to:
            filters.append(f"until-pub-date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if sort_by in ('lastUpdatedDate', 'submittedDate', 'date'):
            params["sort"] = "published"
            params["order"] = "desc"
        elif sort_by == 'citations':
            params["sort"] = "is-referenced-by-count"
            params["order"] = "desc"

        data = self._get_json("https://api.crossref.org/works", params)
        out = []
        for it in ((data.get("message") or {}).get("items") or []):
            title_list = it.get("title") or []
            title = title_list[0] if title_list else ""
            authors = []
            for a in (it.get("author") or []):
                name = " ".join(x for x in [a.get("given"), a.get("family")] if x)
                if name:
                    authors.append(name)
            published, year = self._crossref_date(it)
            pdf = None
            for link in (it.get("link") or []):
                if link.get("content-type") == "application/pdf":
                    pdf = link.get("URL")
                    break
            container = it.get("container-title") or []
            out.append({
                "id": f"doi:{it.get('DOI')}",
                "source": SOURCE_CROSSREF,
                "title": title.strip(),
                "authors": authors,
                "summary": _strip_tags(it.get("abstract")),
                "published": published,
                "year": year,
                "pdf_url": pdf,
                "url": it.get("URL"),
                "doi": _clean_doi(it.get("DOI")),
                "venue": container[0] if container else None,
                "categories": [],
                "citation_count": it.get("is-referenced-by-count"),
            })
        return out

    # ── Harvest / PDF acquisition ───────────────────────────────────────────

    def download_pdf(self, result_id, pdf_url=None, doi=None, title=None):
        """Download a paper's PDF to the raw-material dir; return local path.

        For arXiv, delegates to ArxivHarvester. For other sources, needs an
        open-access ``pdf_url`` (falls back to resolving one from the DOI via
        OpenAlex). Raises ValueError if no open-access PDF can be found.
        """
        source, native = self.parse_id(result_id)
        if source == SOURCE_ARXIV:
            return self.arxiv.download_pdf(native)

        url = pdf_url
        if not url and doi:
            url = self.resolve_oa_pdf(doi)
        if not url:
            raise ValueError("No open-access PDF available for this paper.")

        filename = self._pdf_filename(title, native)
        return self._download_pdf_url(url, filename)

    def resolve_oa_pdf(self, doi):
        """Find an open-access PDF for a DOI via OpenAlex (best_oa_location)."""
        doi = _clean_doi(doi)
        if not doi:
            return None
        try:
            data = self._get_json(
                f"https://api.openalex.org/works/doi:{doi}",
                {"mailto": self.contact_email})
        except Exception as e:
            logger.warning(f"OA resolution failed for {doi}: {e}")
            return None
        best = data.get("best_oa_location") or {}
        oa = data.get("open_access") or {}
        return best.get("pdf_url") or oa.get("oa_url")

    def convert_latex_to_md(self, tar_path):
        """Delegate to ArxivHarvester's LaTeX->Markdown conversion."""
        return self.arxiv.convert_latex_to_md(tar_path)

    def download_source(self, arxiv_id):
        return self.arxiv.download_source(arxiv_id)

    # ── HTTP + misc helpers ─────────────────────────────────────────────────

    def _get_json(self, url, params, max_retries=3, headers=None):
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30, headers=headers)
                if resp.status_code == 429:
                    time.sleep((attempt + 1) * 3)
                    last_err = Exception("Rate limited (429)")
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                time.sleep(attempt + 1)
        raise last_err or Exception("Request failed")

    def _download_pdf_url(self, url, filename):
        filepath = os.path.join(self.download_dir, filename)
        resp = self.session.get(url, timeout=60, stream=True, allow_redirects=True)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        with open(filepath, 'wb') as f:
            first = True
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                if first:
                    if not chunk.lstrip().startswith(b'%PDF') and 'pdf' not in ctype.lower():
                        f.close()
                        os.remove(filepath)
                        raise ValueError(
                            f"URL did not return a PDF (Content-Type: {ctype or 'unknown'}).")
                    first = False
                f.write(chunk)
        return filepath

    def _pdf_filename(self, title, native):
        base = re.sub(r'[^\w\s-]', '', (title or native or 'paper')).strip()
        base = re.sub(r'\s+', '_', base)[:80] or "paper"
        return f"{base}.pdf"

    @staticmethod
    def _year_ok(year, year_from, year_to):
        if year is None:
            return True
        if year_from and year < int(year_from):
            return False
        if year_to and year > int(year_to):
            return False
        return True

    @staticmethod
    def _crossref_date(item):
        parts = ((item.get("issued") or {}).get("date-parts")
                 or (item.get("published") or {}).get("date-parts") or [[]])
        dp = parts[0] if parts else []
        if not dp:
            return None, None
        year = dp[0]
        month = dp[1] if len(dp) > 1 else 1
        day = dp[2] if len(dp) > 2 else 1
        return f"{year:04d}-{month:02d}-{day:02d}", year


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rh = ResearchHarvester()
    print("Searching all sources for 'central bank digital currency'...\n")
    res = rh.search("central bank digital currency",
                    sources=ALL_SOURCES, max_results=5, sort_by='relevance')
    for r in res["results"][:15]:
        pdf = "PDF" if r["pdf_url"] else "no-pdf"
        print(f"[{r['source']:16}] ({pdf}) {r.get('year')} - {r['title'][:70]}")
    if res["errors"]:
        print("\nErrors:", res["errors"])
