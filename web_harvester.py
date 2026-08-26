import os
import re
import json
import html
import datetime
import asyncio
from html.parser import HTMLParser
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from doc_processor import generate_obsidian_markdown, sanitize_filename

# The Hindu ePaper is served by a CCI "replica-reader". The visible reader is a
# page-bitmap viewer with clickable article hotspots — there is NO article text
# in the reader DOM (that is why the old CSS-selector scraper always found 0
# articles). The real content lives behind an authenticated JSON/HTML API:
#
#   {WS}/{product}/{publication}/issues/?epubName={publication}_web&fromDate=..&toDate=..
#       -> resolves the numeric issue id for a given edition + date
#   {WS}/{product}/{publication}/issues/{id}/OPS/cciobjects.json
#       -> manifest tree: Edition -> Page -> Article, with per-article HTML refs
#   {WS}/.../OPS/{article}.html
#       -> clean semantic HTML (h1.head, h2.head_deck, div.byline, div.body p)
#
# We harvest via that API using the cookies captured at login. No browser is
# launched for the harvest itself — a standalone Playwright request context
# replays the stored session cookies over plain HTTPS.

WS_BASE = "https://epaper.thehindu.com/ccidist-ws"
DEFAULT_PRODUCT = "th"
DEFAULT_PUBLICATION = "th_mumbai"


class _ArticleHTMLParser(HTMLParser):
    """Extracts headline / deck / byline / body paragraphs from a CCI article
    HTML document by tracking the semantic container classes."""

    def __init__(self):
        super().__init__()
        self.section = None          # 'head' | 'deck' | 'byline' | 'body' | None
        self._skip_depth = 0         # inside <script>/<style>
        self._buf = []
        self.headline = []
        self.deck = []
        self.byline = []
        self.body = []

    def _classify(self, attrs):
        cls = dict(attrs).get("class", "") or ""
        if "head_deck" in cls:
            return "deck"
        if "taggroup-head" in cls or re.search(r"\bhead\b", cls):
            return "head"
        if "byline" in cls:
            return "byline"
        if "taggroup-body" in cls or re.search(r"\bbody\b", cls):
            return "body"
        if "refer" in cls or "image-gallery" in cls:
            return "skip"  # jump refs & captions
        return None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if tag in ("h1", "h2", "div"):
            c = self._classify(attrs)
            if c is not None:
                self.section = None if c == "skip" else c
        if tag == "p":
            self._buf = []

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "p":
            text = html.unescape("".join(self._buf)).strip()
            text = re.sub(r"\s+", " ", text)
            if text and self.section == "head":
                self.headline.append(text)
            elif text and self.section == "deck":
                self.deck.append(text)
            elif text and self.section == "byline":
                self.byline.append(text)
            elif text and self.section == "body":
                self.body.append(text)
            self._buf = []

    def handle_data(self, data):
        if not self._skip_depth:
            self._buf.append(data)


def _parse_article_html(raw_html):
    p = _ArticleHTMLParser()
    p.feed(raw_html)
    return {
        "headline": " ".join(p.headline).strip(),
        "deck": " ".join(p.deck).strip(),
        "byline": " / ".join(p.byline).strip(),
        "body": p.body,
    }


class WebHarvester:
    def __init__(self, session_data_path=".data/web_session.json"):
        # Put session data in a subfolder to avoid Flask reloader triggers
        self.session_data_path = os.path.join(os.path.dirname(__file__), session_data_path)
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    # ------------------------------------------------------------------ login
    async def setup_session(self, url="https://epaper.thehindu.com/"):
        """Opens a browser for the user to log in and saves session data."""
        async with async_playwright() as p:
            # Use a dedicated profile directory to avoid conflicts with running Chrome
            user_data_dir = os.path.join(os.path.dirname(self.session_data_path), "chrome_profile")
            os.makedirs(user_data_dir, exist_ok=True)

            try:
                # Force the exact path to Google Chrome on macOS
                chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    executable_path=chrome_path if os.path.exists(chrome_path) else None,
                    channel="chrome" if not os.path.exists(chrome_path) else None,
                    headless=False,
                    no_viewport=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception as e:
                print(f"Failed to launch system Chrome: {e}. Falling back to default.")
                # Fallback to bundled chromium if system chrome fails
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    no_viewport=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )

            page = await context.new_page()
            # Apply stealth
            await Stealth().apply_stealth_async(page)

            await page.goto(url)

            # Wait for the user to log in.
            try:
                # We monitor if the context is still open
                while len(context.pages) > 0:
                    await asyncio.sleep(5)
                    # Periodically save the storage state to the JSON file too, for the headless harvester
                    storage = await context.storage_state()
                    with open(self.session_data_path, "w") as f:
                        json.dump(storage, f)
            except Exception as e:
                print(f"Session monitoring ended: {e}")
            finally:
                await context.close()
            return True

    def import_cookies(self, cookie_string, domain=".thehindu.com"):
        """Parses a raw Cookie header string and saves it as a Playwright session."""
        cookies = []
        # Basic parsing of 'name=value; name2=value2'
        parts = cookie_string.split(';')
        for part in parts:
            if '=' in part:
                name, value = part.strip().split('=', 1)
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "expires": int((datetime.datetime.now() + datetime.timedelta(days=30)).timestamp()),
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax"
                })

        storage = {
            "cookies": cookies,
            "origins": []
        }

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.session_data_path), exist_ok=True)

        with open(self.session_data_path, "w") as f:
            json.dump(storage, f)
        return True

    def is_session_active(self):
        return os.path.exists(self.session_data_path)

    def reset_session(self):
        """Clears the saved login: removes the cookie file and the persistent
        Chrome profile so the next 'Setup Login' starts fresh. Returns a list of
        the artifacts that were removed."""
        import shutil
        removed = []
        if os.path.exists(self.session_data_path):
            os.remove(self.session_data_path)
            removed.append(os.path.basename(self.session_data_path))
        profile_dir = os.path.join(os.path.dirname(self.session_data_path), "chrome_profile")
        if os.path.isdir(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)
            removed.append("chrome_profile")
        return removed

    # ---------------------------------------------------------------- helpers
    async def _new_request_context(self, p):
        """Standalone APIRequestContext that replays the stored session cookies.
        No browser is launched."""
        return await p.request.new_context(
            storage_state=self.session_data_path,
            extra_http_headers={"User-Agent": self.user_agent},
        )

    async def list_editions(self, date=None, product=DEFAULT_PRODUCT):
        """Returns [{'id': 'th_mumbai', 'title': 'EPaper-Mumbai'}, ...] for a date."""
        if not os.path.exists(self.session_data_path):
            return []
        date = date or datetime.date.today().isoformat()
        url = (f"{WS_BASE}/{product}/?json=true&fromDate={date}&toDate={date}"
               f"&skipSections=true&os=web&excludePublications=*-*")
        editions = []
        async with async_playwright() as p:
            rc = await self._new_request_context(p)
            try:
                resp = await rc.get(url)
                if resp.status != 200:
                    return []
                data = await resp.json()

                def walk(o):
                    if isinstance(o, dict):
                        if o.get("id") and o.get("title") and "issues" in o:
                            editions.append({"id": o["id"], "title": o["title"]})
                        for v in o.values():
                            walk(v)
                    elif isinstance(o, list):
                        for v in o:
                            walk(v)
                walk(data)
            finally:
                await rc.dispose()
        # de-dup preserving order
        seen, out = set(), []
        for e in editions:
            if e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)
        return out

    async def _resolve_issue(self, rc, product, publication, date):
        """Returns (issue_id, issue_meta) for a publication on a date, or (None, None)."""
        url = (f"{WS_BASE}/{product}/{publication}/issues/"
               f"?epubName={publication}_web&limit=1&skipSections=true"
               f"&fromDate={date}&toDate={date}")
        resp = await rc.get(url)
        if resp.status != 200:
            return None, None
        data = await resp.json()
        issues = (data.get("issues") or {}).get("web") or []
        if not issues:
            return None, None
        return issues[0].get("id"), issues[0]

    @staticmethod
    def _collect_articles(manifest):
        """Walks the manifest tree, returning article nodes tagged with their
        page context, in reading order."""
        articles = []

        def walk(node, page_ctx):
            if node.get("kind") == "Page":
                a = node.get("attributes", {})
                page_ctx = {
                    "group": a.get("PageGroup", ""),
                    "page": a.get("Page", ""),
                    "section": a.get("SectionName", ""),
                }
            if node.get("kind") == "Article":
                articles.append((node, page_ctx))
            for child in node.get("children", []) or []:
                walk(child, page_ctx)

        walk(manifest, {"group": "", "page": "", "section": ""})
        return articles

    # ---------------------------------------------------------------- harvest
    async def harvest_hindu(self, url=None, output_dir=".", publication=None,
                            date=None, product=DEFAULT_PRODUCT, min_body_chars=180):
        """Harvest a full The Hindu ePaper edition via the CCI JSON API.

        `url` is accepted for backward compatibility; if it names a specific
        publication (e.g. th_delhi) that is used, otherwise `publication`
        (default th_mumbai) and today's date are used.
        """
        def emit(message, type="info", progress=None):
            payload = {"message": message, "type": type}
            if progress is not None:
                payload["progress"] = progress
            return json.dumps(payload) + "\n"

        if not os.path.exists(self.session_data_path):
            yield emit("No session found. Please run 'Setup Login' first.", "error")
            return

        publication = publication or self._publication_from_url(url) or DEFAULT_PUBLICATION
        date = date or datetime.date.today().isoformat()

        async with async_playwright() as p:
            rc = await self._new_request_context(p)
            try:
                yield emit(f"Resolving {publication} edition for {date}...")
                issue_id, meta = await self._resolve_issue(rc, product, publication, date)
                if not issue_id:
                    yield emit(
                        f"No published edition found for {publication} on {date}. "
                        f"The edition may not be out yet, or the session expired — "
                        f"try 'Setup Login' again.", "error")
                    return

                page_count = (meta or {}).get("pageCount", "?")
                yield emit(f"Found issue #{issue_id} ({page_count} pages). Loading article index...")

                ops_base = f"{WS_BASE}/{product}/{publication}/issues/{issue_id}/OPS/"
                resp = await rc.get(ops_base + "cciobjects.json")
                if resp.status != 200:
                    yield emit(f"Failed to load article index (HTTP {resp.status}). "
                               f"Session may have expired.", "error")
                    return
                manifest = await resp.json()

                article_nodes = self._collect_articles(manifest)
                total = len(article_nodes)
                yield emit(f"Detected {total} objects. Extracting articles...", progress=0)

                collected = []          # (page_ctx, parsed)
                seen_headlines = {}      # normalized headline -> index in collected
                done = 0
                for node, page_ctx in article_nodes:
                    done += 1
                    attrs = node.get("attributes", {})
                    manifest_headline = (attrs.get("Headline") or "").strip()

                    # Find the article's HTML text resource
                    ref = None
                    for item in node.get("content", []) or []:
                        if item.get("kind") == "Text" and item.get("format") == "text/html":
                            ref = item.get("reference")
                            break
                    if not ref:
                        continue

                    try:
                        art_resp = await rc.get(ops_base + ref)
                        if art_resp.status != 200:
                            continue
                        parsed = _parse_article_html(await art_resp.text())
                    except Exception as e:
                        yield emit(f"⚠ Skipped an article ({e})", "warning")
                        continue

                    headline = parsed["headline"] or manifest_headline
                    body_text = " ".join(parsed["body"])

                    # Filter out ads, promos, QR boxes, standalone captions
                    if not headline:
                        continue
                    if len(body_text) < min_body_chars:
                        continue

                    # Fall back to manifest metadata where the HTML lacked it
                    if not parsed["byline"]:
                        parsed["byline"] = (attrs.get("Byline") or "").strip()
                    if not parsed["deck"]:
                        parsed["deck"] = (attrs.get("SubHead") or "").strip()
                    parsed["headline"] = headline

                    # De-duplicate jumps/continuations: keep the longest body
                    key = re.sub(r"\W+", "", headline.lower())[:60]
                    if key in seen_headlines:
                        idx = seen_headlines[key]
                        prev_ctx, prev = collected[idx]
                        if len(" ".join(parsed["body"])) > len(" ".join(prev["body"])):
                            collected[idx] = (prev_ctx, parsed)
                        continue
                    seen_headlines[key] = len(collected)
                    collected.append((page_ctx, parsed))

                    yield emit(f"✓ [{len(collected)}] {headline[:55]}",
                               progress=int((done / total) * 90))

                if not collected:
                    yield emit("No articles could be extracted. The session may have expired — "
                               "try 'Setup Login' again.", "error")
                    return

                yield emit(f"Assembling {len(collected)} articles into Markdown...", progress=95)
                combined = self._render_markdown_body(collected)

                pub_title = (meta or {}).get("title") or publication
                doc_title = f"The Hindu ePaper — {publication.replace('th_', '').title()} — {date}"
                safe_title = sanitize_filename(doc_title)
                date_compact = date.replace("-", "")
                md_filename = f"{date_compact}_WebHarvest_{safe_title}.md"
                output_path = os.path.join(output_dir, md_filename)

                source_url = (meta or {}).get("readerUrl") or "https://epaper.thehindu.com/reader"
                markdown = generate_obsidian_markdown(combined, doc_title, source_url, date)

                os.makedirs(output_dir, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(markdown)

                yield emit(f"🎊 Complete! {len(collected)} articles saved to {md_filename}",
                           "success", progress=100)
            finally:
                await rc.dispose()

    @staticmethod
    def _publication_from_url(url):
        if not url:
            return None
        m = re.search(r"(th_[a-z]+)", url)
        return m.group(1) if m else None

    @staticmethod
    def _render_markdown_body(collected):
        """Builds a section-grouped Markdown document from extracted articles."""
        lines = []
        # Table of contents
        lines.append("## Contents\n")
        for i, (_ctx, art) in enumerate(collected, 1):
            anchor = art["headline"]
            lines.append(f"{i}. {anchor}")
        lines.append("\n---\n")

        current_group = None
        for _ctx, art in collected:
            group = _ctx.get("group") or "General"
            if group != current_group:
                current_group = group
                lines.append(f"\n# {group}\n")

            lines.append(f"## {art['headline']}\n")
            if art["deck"]:
                lines.append(f"*{art['deck']}*\n")
            meta_bits = []
            if art["byline"]:
                meta_bits.append(f"**{art['byline']}**")
            page = _ctx.get("page")
            if page:
                meta_bits.append(f"_Page {page}_")
            if meta_bits:
                lines.append(" · ".join(meta_bits) + "\n")
            lines.append("\n".join(art["body"]))
            lines.append("\n---\n")

        return "\n".join(lines)
