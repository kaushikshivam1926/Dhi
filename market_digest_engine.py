"""Market Digest Drafting Engine.

Synthesizes market data points, central bank speeches, policy rates, money market
yields, India money-market data, recent market-news transcripts, and global economic
calendar releases into a structured Daily Market Digest report — with real historical
comparisons (via macro_history.py), explicit source provenance, and honest reporting
of any data that could not be retrieved.

Engine chain, in order of preference:
  1. "api_llm"   : Gemini (via doc_processor.call_gemini_text) -> Ollama -> deterministic
  2. "local_llm" : Ollama -> deterministic
  3. "raw_data"  : deterministic template only (no LLM)
The deterministic template is always the final safety net and never fails outright.
"""

import os
import re
import glob
import json
import logging
import requests
import datetime

import doc_processor
import macro_history

logger = logging.getLogger(__name__)

MARKET_DIGEST_SYSTEM_PROMPT = """You are a senior financial analyst and macro trader writing the Daily Market Digest for global market participants.

Given raw market data points, central bank communications, interest rate shifts, equity movements, recent market-news commentary, and economic calendar entries, write a comprehensive, professional Daily Market Digest.

## Non-Negotiable Rules
1. Never write "N/A", "N.A.", "--", or leave a blank where a number is expected. If a data point was not retrievable, OMIT it from the sentence entirely and instead rely on the closing "## Data Coverage Notes" section (already populated for you in the context — reproduce it, do not invent your own gaps).
2. Every numeric claim must be traceable to the CONTEXT DATA supplied in the user message — never invent, estimate, or "round to a plausible-sounding" number.
3. Wherever a historical delta (vs yesterday / vs 1 week / vs 1 month / 30-day range) is supplied for a data point, state it explicitly using the literal figures given — do not just repeat the raw level.
4. When a policy rate is tagged STATIC_FALLBACK or STALE in the context, say so plainly (e.g. "per the last confirmed RBI MPC decision on 6 June 2026, not independently re-verified today") — never present it with the same confidence as a live print. If tagged CHANGED_TODAY, lead with that as the day's headline for that section.
5. For every "why" and "outlook" clause, name a specific driver: a dated item from the CENTRAL BANK SPEECHES block, an excerpt from the RECENT MARKET COMMENTARY block, or a named framework from the list below. Generic filler ("market participants continue to monitor...") without a specific named driver is not acceptable and will be rejected.
6. Do not repeat boilerplate language across sections; each section's prose must reflect that day's actual numbers and drivers, not a template repeated verbatim from a prior day.

## Analytical Frameworks You Must Draw On (cite by name where relevant to a "why" or "outlook" clause)
- Taylor Rule — policy rate is judged against r* + inflation + 0.5x(inflation gap) + 0.5x(output gap); use to assess whether a central bank is behind or ahead of the curve.
- Uncovered/Covered Interest Rate Parity (UIP/CIP) — forward premium tracks the interest-rate differential; use to explain forward points and carry.
- Fisher Effect — nominal rate = real rate + expected inflation; use to decompose a yield move into real-rate vs. inflation-expectation components.
- Expectations Hypothesis + Term Premium — long yields track the average expected path of future short rates plus a term premium; use to explain curve steepening/flattening.
- Purchasing Power Parity (PPP) — a long-run FX fair-value anchor; use for multi-year framing, not to explain a single day's move.
- Mundell-Fleming / Impossible Trinity — a fixed exchange rate, free capital flow, and independent monetary policy cannot coexist; use when discussing EM central bank constraints (e.g. RBI managing INR while targeting inflation).
- Real Rates & r-star — the gap between the real policy rate and the neutral rate signals a restrictive or accommodative stance.
- Carry Trade Dynamics — the funding- vs. target-currency rate differential drives flows; volatility spikes tend to unwind carry trades (e.g. JPY funding carry).
- Forward Guidance Credibility — markets price in a central bank's communication track record; a surprise moves the curve disproportionately when credibility is in question.

The output MUST strictly follow this structured format:

# Morning Update
dt. [Current Date e.g. 18th June 2026]

## USDINR
[Detailed paragraph covering: yesterday's opening, intraday low, high, closing, and how that compares to the prior session/week; fundamental macro drivers including US Fed stance, DXY index, UST yields, Brent crude prices, geopolitical developments — each tied to a specific speech, news item, or framework; key economic data releases; expected USDINR opening and expected intraday trading range.]

## Forwards
[Detailed paragraph covering: monthly premium opening gap, intraday high/low, closing premium; FOMC stance impact on yields, UST 2Y and 10Y yields and their historical comparison; expected monthly premium opening level and trading range; 1-year annualised yield trading range, closing level, and expected range. If forward/premium data is not available this run, focus this section on the UST 2Y/10Y yield picture and its drivers instead of inventing forward levels.]

## Derivatives
[Detailed paragraph covering: central bank policy commentary & inflation forecasts (cite the specific speech); Treasury yield curve flattening/steepening explained via the Expectations Hypothesis/term premium; money market rates (SOFR/EFFR) and their historical comparison; if MIFOR/OIS/ATMF volatility data is unavailable this run (per Data Coverage Notes), do not describe it — instead focus on what SOFR/EFFR and the Treasury curve imply for the rates outlook.]

## Rates
[Detailed paragraph covering: US Treasury yields and Fed policy projections with historical comparison; system liquidity conditions inferred from SOFR/EFFR levels and any RBI VRR/VRRR operations reported in the context; any T-Bill auction items reported in the context (cite them by their actual RBI press-release title/date); central bank policy rates with explicit HELD/CHANGED_TODAY/STATIC_FALLBACK status for each.]

## Equity
[Detailed paragraph covering: Indian equity benchmark performance (Sensex, Nifty 50) with historical comparison; US equity benchmark performance (S&P 500, Nasdaq, Dow Jones) where available; Asian market trends (Nikkei, Hang Seng) where available; tie moves to specific drivers from the context (a speech, a data release, a news excerpt) rather than generic commentary.]

## Crosses
[Detailed paragraph covering: US Dollar Index (DXY) move & drivers where available; EUR/USD, GBP/USD, USD/JPY, AUD/USD levels and intraday shifts with historical comparison; Gold (XAU) price movement; upcoming economic calendar data releases and central bank policy decisions from the watchlist.]

## Data Coverage Notes
[Reproduce the "DATA COVERAGE / KNOWN GAPS" list from the context verbatim, one bullet per item, so the reader knows exactly what could not be retrieved and why. If the context states everything was retrieved, say so in one line.]
"""

# Symbols the "Morning Update" format expects to be able to cite. Diffed against
# what actually resolved this run to build the Data Coverage Notes honestly,
# instead of ever leaving an inline "N/A" in the prose.
EXPECTED_MARKET_SYMBOLS = [
    ("USDINR=X", "USD/INR spot"),
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
    ("JPY=X", "USD/JPY"),
    ("AUDUSD=X", "AUD/USD"),
    ("DX-Y.NYB", "US Dollar Index (DXY)"),
    ("BZ=F", "Brent Crude"),
    ("GC=F", "Gold"),
    ("^BSESN", "BSE Sensex"),
    ("^NSEI", "Nifty 50"),
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq Composite"),
    ("^DJI", "Dow Jones Industrial Average"),
    ("^N225", "Nikkei 225"),
    ("^HSI", "Hang Seng"),
    ("DGS2", "US 2Y Treasury Yield"),
    ("DGS10", "US 10Y Treasury Yield"),
]

INDIA_MONEY_MARKET_LABELS = {
    "tbill_auctions": "T-Bill auction cutoffs (91D/182D/364D)",
    "vrr_vrrr_ops": "RBI VRR/VRRR auction results",
    "fpi_flows": "FPI/FAR investment flows",
    "gift_nifty": "Gift Nifty",
    "india_ois_mifor": "India OIS / MIFOR fixings",
    "atmf_vols": "ATMF implied volatilities / Modified MIFOR curve",
}

DEFAULT_NEWS_CORRELATION_CHANNELS = [
    "Reuters", "Bloomberg", "Financial Times", "Standard Chartered",
    "Barron's", "Shadow Quant", "XM", "Indian Econ Podcasts", "S&P Global", "J P Morgan",
]


class MarketDigestEngine:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)

        self.download_dir = self.config.get("market_data_path", "RawMaterials")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        self.mode = self.config.get("digest_engine_mode", "local_llm")
        self.ollama_model = self.config.get("ollama_model", "gpt-oss:20b")
        self.ollama_url = self.config.get("ollama_url", "http://localhost:11434")
        self.cb_config = self.config.get("central_bank", {})

    # ── Main entry point ────────────────────────────────────────────────

    def generate_digest(self, market_results, cb_data):
        """Generates the Daily Market Digest based on configured mode."""
        today_str = datetime.datetime.now().strftime("%d %B %Y")
        obs_date = datetime.datetime.now().strftime("%Y-%m-%d")
        lookback_hours = self.cb_config.get("lookback_hours", 72)

        try:
            db_path = self.cb_config.get("macro_history_db_path", macro_history.DB_PATH_DEFAULT)
            macro_history.init_db(db_path)
            if macro_history.count_observations(db_path) == 0:
                logger.info("macro_history.db empty — running one-time backfill from vault digests.")
                macro_history.backfill_from_vault(self.download_dir, db_path)
            macro_history.ingest_market_results(market_results, obs_date, db_path)
            macro_history.ingest_policy_rates(cb_data.get("central_bank_rates", {}), obs_date, db_path)
        except Exception as e:
            logger.warning(f"macro_history ingest/backfill failed (continuing without full history): {e}")

        history_deltas = self._compute_history_deltas(market_results, cb_data, obs_date)
        news_items = self._gather_news_context(lookback_hours=lookback_hours)
        coverage_gaps = self._compute_coverage_gaps(market_results, cb_data)
        context = self._build_analysis_context(
            today_str, market_results, cb_data, history_deltas, news_items, coverage_gaps
        )

        content, engine_used = None, None
        if self.mode == "raw_data":
            logger.info("digest_engine_mode=raw_data: skipping LLM stages by configuration.")
        elif self.mode == "api_llm":
            content = self._generate_gemini_digest(context, today_str)
            engine_used = "gemini" if content else None
            if not content:
                content = self._generate_ollama_digest(context, today_str)
                engine_used = "ollama" if content else None
        elif self.mode == "local_llm":
            content = self._generate_ollama_digest(context, today_str)
            engine_used = "ollama" if content else None

        if not content:
            if self.mode != "raw_data":
                logger.warning(f"No LLM stage produced output (mode={self.mode}); using deterministic template.")
            content = self._generate_deterministic_report(today_str, market_results, cb_data, history_deltas, coverage_gaps)
            engine_used = engine_used or "deterministic"

        content = self._append_generation_footer(content, engine_used)

        filename = f"CentralBank_Macro_Digest_{obs_date}.md"
        filepath = os.path.join(self.download_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Market Digest saved to {filepath} (engine={engine_used})")
        return filepath, content

    # ── Historical comparison ───────────────────────────────────────────

    def _compute_history_deltas(self, market_results, cb_data, obs_date):
        db_path = self.cb_config.get("macro_history_db_path", macro_history.DB_PATH_DEFAULT)
        deltas = {}
        for point, data in market_results:
            sym = (point.get('symbol') or '').upper()
            if not sym:
                continue
            series_id = f"{sym}.value"
            deltas[series_id] = macro_history.compute_deltas(series_id, obs_date, db_path)
        for sym in cb_data.get("central_bank_rates", {}):
            series_id = f"{sym.upper()}.value"
            deltas[series_id] = macro_history.compute_deltas(series_id, obs_date, db_path)
        return deltas

    # ── Data coverage ───────────────────────────────────────────────────

    def _compute_coverage_gaps(self, market_results, cb_data):
        resolved = set()
        for point, data in market_results:
            if macro_history.primary_value(data) is not None:
                resolved.add((point.get('symbol') or '').upper())

        gaps = []
        for symbol, label in EXPECTED_MARKET_SYMBOLS:
            if symbol.upper() not in resolved:
                gaps.append({"label": label, "reason": "no live data point resolved this run (not configured, or the fetch failed)"})

        imm = cb_data.get("india_money_market") or {}
        for key, label in INDIA_MONEY_MARKET_LABELS.items():
            rec = imm.get(key) or {}
            if not rec.get("available"):
                gaps.append({"label": label, "reason": rec.get("unavailable_reason", "not available this run")})

        return gaps

    # ── News / live-event correlation ───────────────────────────────────

    def _gather_news_context(self, lookback_hours=72):
        """Scans the vault (market_data_path == obsidian_vault_path, flat layout)
        for recent transcripts from configured finance-news shows. Reconstructs
        the filename glob from sanitize_filename(channel)/sanitize_filename(show)
        rather than reverse-parsing the ambiguous underscore-joined filename."""
        channels = self.cb_config.get("news_correlation_channels", DEFAULT_NEWS_CORRELATION_CHANNELS)
        shows = self.config.get("shows", [])
        cutoff_date_str = (datetime.date.today() - datetime.timedelta(days=max(1, lookback_hours // 24))).strftime("%Y%m%d")

        candidates = []
        for show in shows:
            channel_name = show.get("channel_name", "")
            show_name = show.get("show_name", "")
            if not channel_name or not any(ch.lower() in channel_name.lower() for ch in channels):
                continue

            clean_channel = doc_processor.sanitize_filename(channel_name)
            clean_show = doc_processor.sanitize_filename(show_name)
            pattern = os.path.join(self.download_dir, f"*_{clean_channel}_{clean_show}_*.md")

            for path in glob.glob(pattern):
                basename = os.path.basename(path)
                date_match = re.match(r'(\d{8})_', basename)
                if not date_match or date_match.group(1) < cutoff_date_str:
                    continue
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        body = f.read()
                    if body.startswith('---'):
                        parts = body.split('---', 2)
                        if len(parts) >= 3:
                            body = parts[2]
                    candidates.append({
                        "channel": channel_name,
                        "show": show_name,
                        "date": date_match.group(1),
                        "excerpt": body.strip()[:600],
                    })
                except Exception as e:
                    logger.debug(f"Could not read news context file {path}: {e}")

        candidates.sort(key=lambda c: c["date"], reverse=True)
        return candidates[:15]

    # ── Context assembly ────────────────────────────────────────────────

    def _build_analysis_context(self, date_str, market_results, cb_data, history_deltas, news_items, coverage_gaps):
        lines = [f"Date: {date_str}", ""]

        lines.append("=== TODAY'S MARKET DATA (with provenance + historical deltas) ===")
        for point, data in market_results:
            sym = point.get('symbol', '')
            val = macro_history.primary_value(data)
            if val is None:
                continue
            provider = (point.get('provider') or 'unknown').upper()
            lines.append(f"{sym} ({point.get('type', '')}): {val} [LIVE:{provider}]")
            deltas = history_deltas.get(f"{sym.upper()}.value")
            delta_line = self._format_delta_line(deltas)
            if delta_line:
                lines.append(f"  {delta_line}")
        lines.append("")

        lines.append("=== CENTRAL BANK POLICY RATES (status-annotated) ===")
        for sym, rec in cb_data.get("central_bank_rates", {}).items():
            if not rec:
                continue
            status = macro_history.detect_policy_rate_status(
                f"{sym}.value", rec.get('value'), datetime.datetime.now().strftime("%Y-%m-%d"),
                self.cb_config.get("macro_history_db_path", macro_history.DB_PATH_DEFAULT),
            )
            flags = [status]
            if rec.get('provenance') == 'STATIC_FALLBACK':
                flags.append('STATIC_FALLBACK')
                if rec.get('is_stale'):
                    flags.append(f"STALE:{rec.get('staleness_days')}d")
            lines.append(f"{sym} ({rec.get('name')} - {rec.get('country')}): {rec.get('value')}% "
                         f"as of {rec.get('date')} [{', '.join(flags)}]")
        lines.append("")

        lines.append("=== INDIA MONEY-MARKET DATA (best-effort) ===")
        imm = cb_data.get("india_money_market") or {}
        any_available = False
        for key, label in INDIA_MONEY_MARKET_LABELS.items():
            rec = imm.get(key) or {}
            if rec.get("available"):
                any_available = True
                lines.append(f"{label}:")
                for it in rec.get("items", [])[:5]:
                    lines.append(f"  - [{it.get('pub_date')}] {it.get('title')}: {it.get('summary')}")
        if not any_available:
            lines.append("No India money-market items available this run (see Data Coverage below).")
        lines.append("")

        lines.append("=== CENTRAL BANK SPEECHES & OFFICIAL RELEASES (recent) ===")
        speeches = cb_data.get("speeches_and_releases", [])
        if speeches:
            for sp in speeches[:15]:
                lines.append(f"[{sp.get('institution')}] {sp.get('title')} ({sp.get('pub_date')})")
                if sp.get('summary'):
                    lines.append(f"  {sp.get('summary')[:300]}")
        else:
            lines.append("No central bank speeches/releases matched the recency window this run.")
        lines.append("")

        lines.append("=== RECENT MARKET COMMENTARY (podcasts/news, from vault) ===")
        if news_items:
            for it in news_items:
                lines.append(f"[{it['channel']} - {it['show']}] ({it['date']}): {it['excerpt'][:400]}")
        else:
            lines.append("No matching recent market-news transcripts found in the vault this run.")
        lines.append("")

        lines.append("=== ECONOMIC CALENDAR WATCHLIST ===")
        for ev in (cb_data.get("economic_calendar") or {}).get("watchlist", []):
            lines.append(f"- {ev.get('country')}: {ev.get('name')} ({ev.get('frequency')})")
        lines.append("")

        lines.append("=== DATA COVERAGE / KNOWN GAPS ===")
        if coverage_gaps:
            for gap in coverage_gaps:
                lines.append(f"- {gap['label']}: {gap['reason']}")
        else:
            lines.append("All configured data points were retrieved for this edition.")

        return "\n".join(lines)

    def _format_delta_line(self, deltas):
        if not deltas:
            return ""
        parts = []
        for label, key in (("vs yesterday", "prev_day"), ("vs 1wk", "prev_week"), ("vs 1mo", "prev_month")):
            block = deltas.get(key)
            if not block:
                continue
            if block.get('pct_change') is not None:
                parts.append(f"{label}: {block['change']:+.4f} ({block['pct_change']:+.2f}%)")
            else:
                parts.append(f"{label}: {block['change']:+.4f}")
        range_30d = deltas.get('range_30d')
        if range_30d and range_30d.get('min') is not None:
            parts.append(f"30d range: {range_30d['min']}-{range_30d['max']}")
        return " | ".join(parts)

    # ── LLM generation stages ────────────────────────────────────────────

    def _generate_gemini_digest(self, context, date_str):
        gemini_key = self.config.get("api_keys", {}).get("gemini", "")
        if not gemini_key:
            logger.info("No Gemini API key configured; skipping Gemini stage.")
            return None
        if doc_processor._gemini_quota_exhausted:
            logger.warning("Gemini daily quota already exhausted (shared state); skipping Gemini stage.")
            return None

        model_id = self.config.get("gemini_model", "gemini-1.5-flash")
        result = doc_processor.call_gemini_text(
            prompt=f"Generate the Daily Market Digest for {date_str} based on this context:\n\n{context}",
            api_key=gemini_key,
            model_id=model_id,
            temperature=0.4,
            system_instruction=MARKET_DIGEST_SYSTEM_PROMPT,
        )
        if not result:
            logger.warning("Gemini digest generation failed or returned empty; falling back to Ollama.")
        return result

    def _generate_ollama_digest(self, context, date_str):
        """Invokes local Ollama LLM endpoint."""
        endpoint = f"{self.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": MARKET_DIGEST_SYSTEM_PROMPT},
                {"role": "user", "content": f"Generate the Daily Market Digest for {date_str} based on this context:\n\n{context}"}
            ],
            "stream": False
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=90)
            if resp.status_code == 200:
                res_json = resp.json()
                msg = (res_json.get("message") or {}).get("content", "")
                if msg:
                    return msg.strip()
                logger.warning("Ollama returned an empty message; falling back to deterministic template.")
                return None
            logger.warning(f"Ollama request failed: {resp.status_code} - {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Ollama unreachable at {self.ollama_url} — is it running? Falling back to deterministic template.")
        except Exception as e:
            logger.warning(f"Exception calling Ollama: {e}")

        return None

    # ── Deterministic fallback (always succeeds) ────────────────────────

    def _fmt_val(self, val, decimals=4):
        if val is None or val == 'N/A' or val == '':
            return None
        try:
            fval = float(val)
            res = f"{fval:.{decimals}f}".rstrip('0').rstrip('.')
            return res
        except (ValueError, TypeError):
            return str(val)

    def _delta_phrase(self, deltas):
        """Renders a short 'up/down vs yesterday' clause from a compute_deltas()
        block, or '' if there's no prior observation yet (first run)."""
        if not deltas:
            return ""
        block = deltas.get('prev_day')
        if not block:
            return ""
        change = block['change']
        direction = "up" if change > 0 else ("down" if change < 0 else "flat vs")
        prior = self._fmt_val(block['value'])
        if block.get('pct_change') is not None:
            return f", {direction} {abs(block['pct_change']):.2f}% from {prior} the prior session"
        return f", {direction} {abs(change):.4f} from {prior} the prior session"

    def _generate_deterministic_report(self, date_str, market_results, cb_data, history_deltas, coverage_gaps):
        """Final safety net — always succeeds. Uses real computed deltas and
        policy-rate status instead of static filler; never prints N/A inline —
        gaps are listed once under Data Coverage Notes, matching the LLM path's
        contract so both look consistent to the reader."""
        try:
            return self._render_deterministic_report(date_str, market_results, cb_data, history_deltas, coverage_gaps)
        except Exception as e:
            logger.error(f"Deterministic report generation hit an unexpected error: {e}")
            return (
                f"# Morning Update\ndt. {date_str}\n\n"
                f"> [!WARNING] Digest generation encountered an error: {e}\n"
            )

    def _render_deterministic_report(self, date_str, market_results, cb_data, history_deltas, coverage_gaps):
        lookup = {}
        for point, data in market_results:
            lookup[(point.get('symbol') or '').upper()] = data

        def dv(sym):
            return history_deltas.get(f"{sym.upper()}.value")

        md = f"# Morning Update\ndt. {date_str}\n\n"

        # USDINR
        usdinr = lookup.get("USDINR=X") or {}
        md += "## USDINR\n"
        if usdinr.get('close') is not None:
            md += (f"USD/INR settled at {self._fmt_val(usdinr.get('close'))}"
                   f"{self._delta_phrase(dv('USDINR=X'))}, with an intraday range of "
                   f"{self._fmt_val(usdinr.get('low'))}-{self._fmt_val(usdinr.get('high'))}.\n")
        else:
            md += "USD/INR spot data was not retrieved this run (see Data Coverage Notes).\n"

        nyfed = cb_data.get("nyfed_rates") or {}
        sofr = (nyfed.get("SOFR") or {}).get("rate")
        effr = (nyfed.get("EFFR") or {}).get("rate")
        rate_bits = []
        if effr is not None:
            rate_bits.append(f"EFFR at {self._fmt_val(effr, 2)}%")
        if sofr is not None:
            rate_bits.append(f"SOFR fixing at {self._fmt_val(sofr, 2)}%")
        if rate_bits:
            md += f"US money-market reference: {', '.join(rate_bits)}.\n"

        dxy_data = lookup.get("DX-Y.NYB") or lookup.get("DXY") or lookup.get("DX=F") or {}
        brent_data = lookup.get("BZ=F") or {}
        cross_bits = []
        if dxy_data.get('close') is not None:
            cross_bits.append(f"DXY at {self._fmt_val(dxy_data.get('close'), 2)}{self._delta_phrase(dv('DX-Y.NYB'))}")
        if brent_data.get('close') is not None:
            cross_bits.append(f"Brent crude near ${self._fmt_val(brent_data.get('close'), 2)}{self._delta_phrase(dv('BZ=F'))}")
        if cross_bits:
            md += f"{'; '.join(cross_bits)}.\n"
        md += "\n"

        # Forwards / Rates backdrop
        ust10 = (lookup.get("DGS10") or {}).get('value')
        ust2 = (lookup.get("DGS2") or {}).get('value')
        md += "## Forwards\n"
        if ust2 is not None or ust10 is not None:
            bits = []
            if ust2 is not None:
                bits.append(f"2Y at {self._fmt_val(ust2, 2)}%{self._delta_phrase(dv('DGS2'))}")
            if ust10 is not None:
                bits.append(f"10Y at {self._fmt_val(ust10, 2)}%{self._delta_phrase(dv('DGS10'))}")
            md += f"US Treasury yields: {', '.join(bits)}, shaping forward premium expectations.\n\n"
        else:
            md += "US Treasury yield data was not retrieved this run (see Data Coverage Notes).\n\n"

        # Derivatives
        md += "## Derivatives\n"
        if rate_bits:
            md += f"Money-market fixings: {', '.join(rate_bits)}.\n\n"
        else:
            md += "SOFR/EFFR fixings were not retrieved this run (see Data Coverage Notes).\n\n"

        # Rates (policy rates + India money-market best-effort)
        md += "## Rates\n"
        cbrates = cb_data.get("central_bank_rates", {})
        if cbrates:
            md += "Central Bank Policy Rates:\n"
            for sym, rec in cbrates.items():
                if not rec:
                    continue
                status = macro_history.detect_policy_rate_status(
                    f"{sym}.value", rec.get('value'), datetime.datetime.now().strftime("%Y-%m-%d"),
                    self.cb_config.get("macro_history_db_path", macro_history.DB_PATH_DEFAULT),
                )
                tag = ""
                if rec.get('provenance') == 'STATIC_FALLBACK':
                    tag = f" (static fallback as of last confirmed decision {rec.get('date')}"
                    tag += ", STALE" if rec.get('is_stale') else ""
                    tag += ")"
                elif status == 'CHANGED_TODAY':
                    tag = " (changed today)"
                md += f"- {rec.get('name')} ({rec.get('country')}): {self._fmt_val(rec.get('value'), 2)}%{tag}\n"
            md += "\n"

        imm = cb_data.get("india_money_market") or {}
        imm_lines = []
        for key, label in INDIA_MONEY_MARKET_LABELS.items():
            rec = imm.get(key) or {}
            if rec.get("available"):
                for it in rec.get("items", [])[:2]:
                    imm_lines.append(f"- **{label}**: {it.get('title')} ({it.get('pub_date')})")
        if imm_lines:
            md += "India Money-Market Updates:\n" + "\n".join(imm_lines) + "\n\n"

        # Equity
        sensex = (lookup.get("^BSESN") or {}).get('close')
        nifty = (lookup.get("^NSEI") or {}).get('close')
        sp500 = (lookup.get("^GSPC") or {}).get('close')
        nasdaq = (lookup.get("^IXIC") or {}).get('close')
        dow = (lookup.get("^DJI") or {}).get('close')
        nikkei = (lookup.get("^N225") or {}).get('close')
        hangseng = (lookup.get("^HSI") or {}).get('close')

        md += "## Equity\n"
        equity_bits = []
        if sensex is not None:
            equity_bits.append(f"Sensex at {self._fmt_val(sensex, 2)}{self._delta_phrase(dv('^BSESN'))}")
        if nifty is not None:
            equity_bits.append(f"Nifty 50 at {self._fmt_val(nifty, 2)}{self._delta_phrase(dv('^NSEI'))}")
        if equity_bits:
            md += f"Indian benchmarks: {', '.join(equity_bits)}.\n"
        us_bits = []
        if sp500 is not None:
            us_bits.append(f"S&P 500 at {self._fmt_val(sp500, 2)}{self._delta_phrase(dv('^GSPC'))}")
        if nasdaq is not None:
            us_bits.append(f"Nasdaq at {self._fmt_val(nasdaq, 2)}{self._delta_phrase(dv('^IXIC'))}")
        if dow is not None:
            us_bits.append(f"Dow Jones at {self._fmt_val(dow, 2)}{self._delta_phrase(dv('^DJI'))}")
        if us_bits:
            md += f"US benchmarks: {', '.join(us_bits)}.\n"
        asia_bits = []
        if nikkei is not None:
            asia_bits.append(f"Nikkei 225 at {self._fmt_val(nikkei, 2)}{self._delta_phrase(dv('^N225'))}")
        if hangseng is not None:
            asia_bits.append(f"Hang Seng at {self._fmt_val(hangseng, 2)}{self._delta_phrase(dv('^HSI'))}")
        if asia_bits:
            md += f"Asian benchmarks: {', '.join(asia_bits)}.\n"
        if not (equity_bits or us_bits or asia_bits):
            md += "Equity index data was not retrieved this run (see Data Coverage Notes).\n"
        md += "\n"

        # Crosses
        eurusd = (lookup.get("EURUSD=X") or {}).get('close')
        gbpusd = (lookup.get("GBPUSD=X") or {}).get('close')
        usdjpy = (lookup.get("JPY=X") or {}).get('close')
        audusd = (lookup.get("AUDUSD=X") or {}).get('close')
        gold = (lookup.get("GC=F") or {}).get('close')

        md += "## Crosses\n"
        cross_line_bits = []
        if dxy_data.get('close') is not None:
            cross_line_bits.append(f"DXY: {self._fmt_val(dxy_data.get('close'), 2)}")
        if eurusd is not None:
            cross_line_bits.append(f"EUR/USD: {self._fmt_val(eurusd)}")
        if gbpusd is not None:
            cross_line_bits.append(f"GBP/USD: {self._fmt_val(gbpusd)}")
        if usdjpy is not None:
            cross_line_bits.append(f"USD/JPY: {self._fmt_val(usdjpy)}")
        if audusd is not None:
            cross_line_bits.append(f"AUD/USD: {self._fmt_val(audusd)}")
        if gold is not None:
            cross_line_bits.append(f"Gold: ${self._fmt_val(gold, 2)}")
        if cross_line_bits:
            md += " | ".join(cross_line_bits) + ".\n\n"
        else:
            md += "FX cross and gold data was not retrieved this run (see Data Coverage Notes).\n\n"

        # Speeches
        md += "### Central Bank Speeches & Official Releases\n"
        speeches = [sp for sp in cb_data.get("speeches_and_releases", []) if (sp.get('title') or '').strip()]
        if speeches:
            for sp in speeches:
                pub_date = f" ({sp.get('pub_date')})" if sp.get('pub_date') else ""
                md += f"- **[{sp.get('institution')}]** {sp.get('title')}{pub_date}\n"
                if sp.get('summary'):
                    md += f"  *{sp.get('summary')[:200]}*\n"
        else:
            md += "No central bank speeches matched the recency window this run.\n"

        # Calendar
        md += "\n### Global Economic Calendar Watchlist\n"
        for ev in (cb_data.get("economic_calendar") or {}).get("watchlist", []):
            md += f"- **{ev.get('country')}**: {ev.get('name')} ({ev.get('frequency')})\n"

        # Data Coverage Notes — always present, never an inline N/A anywhere above
        md += "\n## Data Coverage Notes\n"
        if coverage_gaps:
            for gap in coverage_gaps:
                md += f"- **{gap['label']}**: {gap['reason']}\n"
        else:
            md += "All configured data points were retrieved for this edition.\n"

        return md

    def _append_generation_footer(self, content, engine_used):
        engine_labels = {
            "gemini": f"Gemini ({self.config.get('gemini_model', 'gemini-1.5-flash')})",
            "ollama": f"Local Ollama ({self.ollama_model})",
            "deterministic": "Deterministic template (no LLM available this run)",
        }
        label = engine_labels.get(engine_used, engine_used or "unknown")
        stats = doc_processor.get_gemini_stats()
        footer = f"\n\n---\n*Generated via: {label} | Gemini requests today: {stats.get('total_today', 0)}*\n"
        return content.rstrip() + footer
