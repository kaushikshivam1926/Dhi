"""Central Bank Speeches, Official Communications, Macro Data & Economic Calendar Harvester.

Fetches central bank speeches and official releases from BIS (Bank for International
Settlements) and direct central bank feeds (Fed, RBI, ECB, BoE, BoJ, RBA, Riksbank, SNB),
fetches free official macro data (FRED, NYFed, EODHD, YFinance), and aggregates upcoming
economic calendar releases for global markets.
"""

import os
import re
import json
import logging
import requests
import datetime
import email.utils
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

import central_bank_rates

logger = logging.getLogger(__name__)

# RSS Feeds for Central Bank Speeches & Releases
CB_FEEDS = {
    "BIS_Global": {
        "url": "https://www.bis.org/doclist/cbspeeches.rss",
        "institution": "BIS / Global Central Banks"
    },
    "FED_Speeches": {
        "url": "https://www.federalreserve.gov/feeds/speeches.xml",
        "institution": "Federal Reserve"
    },
    "FED_Press": {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "institution": "Federal Reserve"
    },
    "ECB_Press": {
        "url": "https://www.ecb.europa.eu/rss/press.xml",
        "institution": "European Central Bank"
    },
    "BoE_News": {
        "url": "https://www.bankofengland.co.uk/rss/news",
        "institution": "Bank of England"
    },
    "RBI_Speeches": {
        "url": "https://rbi.org.in/rssfeed/speeches.xml",
        "institution": "Reserve Bank of India"
    },
    "RBA_Media": {
        "url": "https://www.rba.gov.au/rss/rss-media-releases.xml",
        "institution": "Reserve Bank of Australia"
    },
    "BoJ_News": {
        "url": "https://www.boj.or.jp/en/rss/press.xml",
        "institution": "Bank of Japan"
    },
    "Riksbank_News": {
        "url": "https://www.riksbank.se/en-gb/rss/press-releases/",
        "institution": "Sveriges Riksbank"
    }
}

REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

# RBI's general press-release feed (distinct from CB_FEEDS['RBI_Speeches'], which
# only carries speeches). Confirmed reachable and to genuinely carry Treasury Bill
# auction notices/results and VRR/VRRR operation announcements.
RBI_PRESS_RELEASES_URL = "https://rbi.org.in/pressreleases_rss.xml"
TBILL_KEYWORDS = re.compile(r'treasury bill|t-bill|91[- ]day|182[- ]day|364[- ]day', re.I)
VRR_KEYWORDS = re.compile(r'variable rate repo|variable rate reverse repo|\bVRR\b|\bVRRR\b', re.I)


def _parse_pub_date(pub_date_str):
    """Parses RFC822 (RSS) or ISO8601 (Atom) publication dates. Returns a
    tz-aware datetime, or None if unparseable — callers must fail OPEN on
    None (keep the item) rather than silently dropping it."""
    if not pub_date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except ValueError:
        return None


def _filter_and_sort_speeches(items, max_items, lookback_hours):
    """Keeps items published within the lookback window; items with an
    unparseable date are kept (fail open) rather than dropped. Sorted
    newest-first, truncated to max_items."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=lookback_hours)

    def in_window(it):
        pd = it.get("pub_date_parsed")
        return pd is None or pd >= cutoff

    kept = [it for it in items if in_window(it)]

    def sort_key(it):
        return it.get("pub_date_parsed") or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

    kept.sort(key=sort_key, reverse=True)
    for it in kept:
        it.pop("pub_date_parsed", None)
    return kept[:max_items]


class CentralBankHarvester:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)
                
        self.download_dir = self.config.get("market_data_path", "RawMaterials")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
            
        self.fred_key = self.config.get("api_keys", {}).get("fred", "")
        
    def fetch_speeches_and_releases(self, max_items_per_feed=5, lookback_hours=72):
        """Harvests recent central bank speeches and official press releases,
        filtered to the last `lookback_hours` and sorted newest-first."""
        speeches = []

        for key, feed_info in CB_FEEDS.items():
            url = feed_info["url"]
            inst = feed_info["institution"]
            feed_items = []
            try:
                resp = requests.get(url, headers=REQ_HEADERS, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch feed {key} ({url}): status {resp.status_code}")
                    continue

                # Parse RSS / XML content
                root = None
                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError:
                    # Fallback to BeautifulSoup parser for imperfect RSS feeds
                    soup = BeautifulSoup(resp.content, "xml")
                    for item in soup.find_all("item"):
                        title = item.title.text.strip() if item.title else "Untitled"
                        link = item.link.text.strip() if item.link else ""
                        pub_date = item.pubDate.text.strip() if item.pubDate else ""
                        desc = item.description.text.strip() if item.description else ""
                        # Clean HTML tags in description
                        clean_desc = BeautifulSoup(desc, "html.parser").get_text().strip()

                        feed_items.append({
                            "source": key,
                            "institution": inst,
                            "title": title,
                            "link": link,
                            "pub_date": pub_date,
                            "summary": clean_desc[:400],
                            "pub_date_parsed": _parse_pub_date(pub_date),
                        })
                    speeches.extend(_filter_and_sort_speeches(feed_items, max_items_per_feed, lookback_hours))
                    continue

                # Standard ElementTree parsing
                # Handles RSS <channel><item> and Atom <entry>
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
                for item in items:
                    def get_text(elem_name):
                        # NOTE: do not use `x or y` here — an ElementTree Element
                        # with no child elements (e.g. a normal <title>Foo</title>
                        # leaf) evaluates as falsy via __len__, which would wrongly
                        # discard perfectly valid text and fall through every time.
                        el = item.find(elem_name)
                        if el is None:
                            el = item.find(f".//{{http://www.w3.org/2005/Atom}}{elem_name}")
                        if el is None:
                            return ""
                        if el.text:
                            return el.text.strip()
                        return el.get('href', '')  # Atom <link href="..."/> has no text

                    title = get_text("title")
                    link = get_text("link")
                    pub_date = get_text("pubDate") or get_text("published") or get_text("updated")
                    desc = get_text("description") or get_text("summary")

                    # Clean HTML tags
                    clean_desc = BeautifulSoup(desc, "html.parser").get_text().strip() if desc else ""

                    feed_items.append({
                        "source": key,
                        "institution": inst,
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "summary": clean_desc[:400],
                        "pub_date_parsed": _parse_pub_date(pub_date),
                    })

                speeches.extend(_filter_and_sort_speeches(feed_items, max_items_per_feed, lookback_hours))

            except Exception as e:
                logger.error(f"Error fetching central bank feed {key}: {e}")

        return speeches

    def fetch_nyfed_rates(self):
        """Fetches reference rates directly from official public NYFed API."""
        url = "https://markets.newyorkfed.org/api/rates/all/latest.json"
        rates = {}
        try:
            resp = requests.get(url, headers=REQ_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                ref_rates = data.get('refRates', [])
                for item in ref_rates:
                    rate_type = item.get('type')
                    effective_date = item.get('effectiveDate')
                    rate_val = item.get('percentRate')
                    if rate_val is None and 'average30day' in item:
                        rate_val = item.get('average30day')
                    if rate_type:
                        rates[rate_type] = {
                            "date": effective_date,
                            "rate": rate_val,
                            "volume_billions": item.get('volumeInBillions')
                        }
        except Exception as e:
            logger.error(f"Error fetching NYFed rates: {e}")
        return rates

    def fetch_economic_calendar(self):
        """Aggregates upcoming major economic releases for key economies (US, EU, UK, JP, IN, CN, AU)."""
        calendar_events = []
        
        # 1. Try fetching calendar events via free API / Quantgist / FRED release calendar
        try:
            if self.fred_key:
                # Fetch FRED upcoming releases for today & next 7 days
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                future = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
                url = "https://api.stlouisfed.org/fred/release/dates"
                params = {
                    "api_key": self.fred_key,
                    "file_type": "json",
                    "realtime_start": today,
                    "realtime_end": future,
                    "limit": 20
                }
                resp = requests.get(url, params=params, headers=REQ_HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    release_dates = data.get("release_dates", [])
                    for rd in release_dates:
                        calendar_events.append({
                            "date": rd.get("date"),
                            "release_id": rd.get("release_id"),
                            "name": rd.get("release_name", f"Release {rd.get('release_id')}"),
                            "country": "US"
                        })
        except Exception as e:
            logger.error(f"Error fetching FRED calendar: {e}")
            
        # Standard recurring key global calendar data points tracked by traders
        static_calendar_watchlist = [
            {"name": "US Initial Jobless Claims", "country": "US", "frequency": "Weekly (Thursdays)"},
            {"name": "US Non-Farm Payrolls & Unemployment Rate", "country": "US", "frequency": "Monthly (First Friday)"},
            {"name": "US CPI & Core Inflation", "country": "US", "frequency": "Monthly"},
            {"name": "US Core PCE Price Index", "country": "US", "frequency": "Monthly"},
            {"name": "FOMC Interest Rate Decision & Press Conference", "country": "US", "frequency": "8 times/year"},
            {"name": "RBI MPC Policy Rate Decision", "country": "India", "frequency": "Bi-monthly"},
            {"name": "India CPI Inflation & IIP Data", "country": "India", "frequency": "Monthly (12th)"},
            {"name": "ECB Monetary Policy Decision", "country": "Eurozone", "frequency": "8 times/year"},
            {"name": "BoE Bank Rate Decision", "country": "UK", "frequency": "8 times/year"},
            {"name": "BoJ Rate Decision & Monetary Policy Statement", "country": "Japan", "frequency": "8 times/year"},
            {"name": "RBA Cash Rate Decision", "country": "Australia", "frequency": "8 times/year"}
        ]

        return {"watchlist": calendar_events + static_calendar_watchlist}

    def fetch_central_bank_policy_rates(self):
        """Fetches key Central Bank Policy Rates (RBI, BoJ, RBA, SNB, PBoC, Riksbank, ECB, Fed, BoE).
        Delegates to central_bank_rates.py, the single source of truth for these
        values, which tags every record with provenance (live vs. static fallback)
        and staleness rather than presenting a stale number as if freshly fetched."""
        return central_bank_rates.get_all_policy_rates(fred_key=self.fred_key)

    def _fetch_eodhd(self, point):
        eodhd_key = self.config.get("api_keys", {}).get("eodhd", "")
        if not eodhd_key:
            return None
        symbol = point.get('symbol', '').upper()
        dtype = point.get('type', 'stock')
        try:
            if dtype == 'macro':
                country = point.get('country', 'USA')
                url = f"https://eodhd.com/api/macro-indicator/{country}"
                params = {'api_token': eodhd_key, 'indicator': symbol, 'fmt': 'json'}
                resp = requests.get(url, params=params, headers=REQ_HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        last_row = max(data, key=lambda x: x.get('date', ''))
                        rate_val = float(last_row.get('rate')) if 'rate' in last_row and last_row.get('rate') is not None else None
                        date_val = last_row.get('date')
                        return {
                            'date': date_val,
                            'value': rate_val,
                            'rate': rate_val,
                            'close': rate_val
                        }
            else:
                url = f"https://eodhd.com/api/eod/{symbol}"
                params = {'api_token': eodhd_key, 'fmt': 'json', 'limit': 5}
                resp = requests.get(url, params=params, headers=REQ_HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        row = data[-1]
                        return {
                            'open': float(row['open']) if 'open' in row and row['open'] is not None else None,
                            'high': float(row['high']) if 'high' in row and row['high'] is not None else None,
                            'low': float(row['low']) if 'low' in row and row['low'] is not None else None,
                            'close': float(row['close']) if 'close' in row and row['close'] is not None else None,
                        }
        except Exception as e:
            logger.error(f"EODHD fetch error for {symbol}: {e}")
        return None

    def _fetch_central_bank(self, point):
        """Resolves a single 'central_bank' provider market point. EODHD/NYFed
        are tried first for the symbols where they carry a genuinely live
        print; everything else (including the EODHD/NYFed fallthrough case)
        is resolved via central_bank_rates.py, the single source of truth."""
        symbol = point.get('symbol', '').upper()

        if symbol in ['FED_TARGET_LOWER', 'FED_TARGET_UPPER', 'ECB_MRO', 'ECB_MLF', 'ECB_DFR', 'BOE_BANK_RATE']:
            eodhd_data = self._fetch_eodhd(point)
            if eodhd_data:
                return eodhd_data
        elif symbol in ['SOFR', 'EFFR', 'OBFR', 'TGCR', 'BGCR']:
            nyfed_data = self.fetch_nyfed_rates()
            if symbol in nyfed_data:
                return nyfed_data[symbol]

        return central_bank_rates.get_policy_rate(symbol, fred_key=self.fred_key)

    def fetch_macro_market_points(self):
        """Independently fetches key market data points for the Central Bank & Macro Digest."""
        results = []
        market_points = self.config.get("market_data_points", [])
        
        for point in market_points:
            provider = point.get('provider')
            symbol = point.get('symbol', '')
            try:
                if provider == 'central_bank':
                    data = self._fetch_central_bank(point)
                    if data:
                        results.append((point, data))
                elif provider == 'eodhd':
                    data = self._fetch_eodhd(point)
                    if data:
                        results.append((point, data))
                elif provider == 'nyfed':
                    nyfed_rates = self.fetch_nyfed_rates()
                    if symbol in nyfed_rates:
                        results.append((point, nyfed_rates[symbol]))
                elif provider == 'yfinance':
                    import yfinance as yf
                    t = yf.Ticker(symbol)
                    hist = t.history(period="5d")
                    if hist is not None and not hist.empty:
                        row = hist.iloc[-1]
                        results.append((point, {
                            'open': float(row['Open']) if 'Open' in row and row['Open'] is not None else None,
                            'high': float(row['High']) if 'High' in row and row['High'] is not None else None,
                            'low': float(row['Low']) if 'Low' in row and row['Low'] is not None else None,
                            'close': float(row['Close']) if 'Close' in row and row['Close'] is not None else None,
                        }))
                elif provider == 'fred' and self.fred_key:
                    url = "https://api.stlouisfed.org/fred/series/observations"
                    params = {"series_id": symbol, "api_key": self.fred_key, "file_type": "json", "sort_order": "desc", "limit": 1}
                    resp = requests.get(url, params=params, timeout=5)
                    if resp.status_code == 200:
                        obs = resp.json().get('observations', [])
                        if obs:
                            results.append((point, {'date': obs[0].get('date'), 'value': obs[0].get('value')}))
            except Exception as e:
                logger.warning(f"Error fetching point {symbol} in CentralBankHarvester: {e}")
                
        return results

    def _fetch_rbi_press_releases(self, lookback_hours=72):
        """Fetches RBI's general press-release feed. A real, verified-reachable
        source (unlike NSE/NSDL, which block unauthenticated scripted requests
        from this environment) that regularly carries Treasury Bill auction
        notices/results and VRR/VRRR operation announcements."""
        items = []
        try:
            resp = requests.get(RBI_PRESS_RELEASES_URL, headers=REQ_HEADERS, timeout=10)
            if resp.status_code != 200:
                logger.info(f"RBI press release feed returned status {resp.status_code}")
                return items
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                link_el = item.find("link")
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                pub_date_el = item.find("pubDate")
                pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ""
                desc_el = item.find("description")
                desc_raw = desc_el.text if desc_el is not None and desc_el.text else ""
                summary = BeautifulSoup(desc_raw, "html.parser").get_text(separator=" ").strip()
                summary = re.sub(r'\s+', ' ', summary)
                items.append({
                    "title": title, "link": link, "pub_date": pub_date,
                    "summary": summary[:500],
                    "pub_date_parsed": _parse_pub_date(pub_date),
                })
        except Exception as e:
            logger.info(f"RBI press release feed fetch failed: {e}")
        return _filter_and_sort_speeches(items, 25, lookback_hours)

    def fetch_india_money_market_data(self, lookback_hours=72):
        """Best-effort free/public India money-market data. Every field
        independently reports availability rather than ever being silently
        blank. Verified directly during implementation: NSE (Gift Nifty) and
        NSDL (FPI flows) block unauthenticated scripted requests from this
        environment (connection failures / HTTP 500); FBIL, the official
        OIS/MIFOR benchmark administrator, serves only a client-rendered SPA
        with no discoverable public data endpoint. RBI's own press-release
        feed was confirmed reachable and to genuinely carry this content."""
        press_items = self._fetch_rbi_press_releases(lookback_hours=lookback_hours)
        tbill_items = [it for it in press_items if TBILL_KEYWORDS.search(it["title"])]
        vrr_items = [it for it in press_items if VRR_KEYWORDS.search(it["title"])]

        def _bucket(items):
            if items:
                return {"available": True, "provenance": "LIVE:RBI",
                        "items": items, "source_url": RBI_PRESS_RELEASES_URL}
            return {"available": False, "provenance": "UNAVAILABLE", "items": [],
                    "source_url": RBI_PRESS_RELEASES_URL,
                    "unavailable_reason": f"No matching RBI press release in the last {lookback_hours}h."}

        return {
            "tbill_auctions": _bucket(tbill_items),
            "vrr_vrrr_ops": _bucket(vrr_items),
            "fpi_flows": {
                "available": False, "provenance": "UNAVAILABLE", "source_url": None,
                "unavailable_reason": "NSDL's public FPI reporting endpoint blocks unauthenticated "
                                       "scripted requests from this environment; no other free feed identified.",
            },
            "gift_nifty": {
                "available": False, "provenance": "UNAVAILABLE", "source_url": None,
                "unavailable_reason": "NSE blocks unauthenticated scripted requests (bot protection); "
                                       "no other free real-time feed identified.",
            },
            "india_ois_mifor": {
                "available": False, "provenance": "UNAVAILABLE", "source_url": None,
                "unavailable_reason": "FBIL (the official OIS/MIFOR benchmark administrator) publishes "
                                       "only via a client-rendered site with no discoverable public data "
                                       "API; these are otherwise dealer-quoted, Bloomberg/Refinitiv/CCIL-terminal data.",
            },
            "atmf_vols": {
                "available": False, "provenance": "UNAVAILABLE", "source_url": None,
                "unavailable_reason": "ATMF implied volatilities and the Modified MIFOR curve are "
                                       "dealer-quoted; no public free feed exists (Bloomberg/Refinitiv/CCIL terminal only).",
            },
        }

    def harvest_all_central_bank_data(self):
        """Full execution wrapper returning aggregated central bank context."""
        logger.info("Starting Central Bank & Macro harvesting...")
        lookback_hours = self.config.get("central_bank", {}).get("lookback_hours", 72)
        speeches = self.fetch_speeches_and_releases(lookback_hours=lookback_hours)
        nyfed_rates = self.fetch_nyfed_rates()
        cb_rates = self.fetch_central_bank_policy_rates()
        calendar = self.fetch_economic_calendar()
        india_money_market = self.fetch_india_money_market_data(lookback_hours=lookback_hours)

        return {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "speeches_and_releases": speeches,
            "nyfed_rates": nyfed_rates,
            "central_bank_rates": cb_rates,
            "economic_calendar": calendar,
            "india_money_market": india_money_market,
        }

def run_central_bank_harvest():
    """Standalone entry point for central bank & macro digest harvesting."""
    from market_digest_engine import MarketDigestEngine
    harvester = CentralBankHarvester()
    engine = MarketDigestEngine()
    
    cb_data = harvester.harvest_all_central_bank_data()
    market_results = harvester.fetch_macro_market_points()
    
    filepath, _ = engine.generate_digest(market_results, cb_data)
    return True, f"Successfully harvested Central Bank & Macro data. Digest saved to {os.path.basename(filepath)}."

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, msg = run_central_bank_harvest()
    print(f"Result: {success} - {msg}")
