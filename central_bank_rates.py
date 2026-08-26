"""Single source of truth for central bank policy rates.

Consolidates what used to be two duplicated hardcoded dicts
(central_bank_harvester.py and market_harvester.py). Every returned record is
tagged with explicit provenance so a static fallback number is never
presented with the same confidence as a live print.
"""

import logging
import datetime
import requests

logger = logging.getLogger(__name__)

REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# Last-known values, used only when no live source is available or reachable.
# 'date' is when this value was last verified by a human against an official source.
STATIC_FALLBACK_RATES = {
    'RBI_REPO':         {'rate': 6.50, 'country': 'IN', 'name': 'RBI Policy Repo Rate',         'date': '2026-06-06'},
    'RBI_SDF':          {'rate': 6.25, 'country': 'IN', 'name': 'RBI Standing Deposit Facility', 'date': '2026-06-06'},
    'RBI_MSF':          {'rate': 6.75, 'country': 'IN', 'name': 'RBI Marginal Standing Facility','date': '2026-06-06'},
    'BOJ_POLICY':       {'rate': 0.25, 'country': 'JP', 'name': 'BoJ Uncollateralized Call Rate','date': '2026-07-15'},
    'RBA_CASH':         {'rate': 4.35, 'country': 'AU', 'name': 'RBA Official Cash Rate',        'date': '2026-07-02'},
    'SNB_POLICY':       {'rate': 1.00, 'country': 'CH', 'name': 'SNB Policy Rate',               'date': '2026-06-20'},
    'PBOC_LPR_1Y':      {'rate': 3.10, 'country': 'CN', 'name': 'PBoC 1-Year LPR',               'date': '2026-07-20'},
    'PBOC_LPR_5Y':      {'rate': 3.60, 'country': 'CN', 'name': 'PBoC 5-Year LPR',               'date': '2026-07-20'},
    'RIKSBANK_POLICY':  {'rate': 2.00, 'country': 'SE', 'name': 'Riksbank Policy Rate',          'date': '2026-06-27'},
    'FED_TARGET_LOWER': {'rate': 5.25, 'country': 'US', 'name': 'Fed Target Rate Lower Bound',   'date': '2026-06-18'},
    'FED_TARGET_UPPER': {'rate': 5.50, 'country': 'US', 'name': 'Fed Target Rate Upper Bound',   'date': '2026-06-18'},
    'ECB_MRO':          {'rate': 4.25, 'country': 'EU', 'name': 'ECB Main Refinancing Rate',     'date': '2026-06-12'},
    'ECB_DFR':          {'rate': 3.75, 'country': 'EU', 'name': 'ECB Deposit Facility Rate',     'date': '2026-06-12'},
    'BOE_BANK_RATE':    {'rate': 5.25, 'country': 'UK', 'name': 'BoE Official Bank Rate',        'date': '2026-06-20'},
}

# How many days may pass since a symbol's static 'date' before we flag it STALE.
# Set roughly to each bank's decision cadence (~8 meetings/year => ~45-55 days)
# plus a grace buffer so a normal gap between meetings isn't falsely flagged.
STALENESS_THRESHOLD_DAYS = {
    'RBI_REPO': 75, 'RBI_SDF': 75, 'RBI_MSF': 75,
    'BOJ_POLICY': 55, 'RBA_CASH': 55, 'RIKSBANK_POLICY': 70,
    'SNB_POLICY': 100, 'PBOC_LPR_1Y': 40, 'PBOC_LPR_5Y': 40,
    'FED_TARGET_LOWER': 55, 'FED_TARGET_UPPER': 55,
    'ECB_MRO': 55, 'ECB_DFR': 55, 'BOE_BANK_RATE': 55,
}

# symbol -> (provider, provider-specific identifier). Only symbols with a
# verified free/live feed appear here; everything else uses the static table.
_FRED_SERIES = {
    'FED_TARGET_LOWER': 'DFEDTARL',
    'FED_TARGET_UPPER': 'DFEDTARU',
    'ECB_DFR': 'ECBDFR',
    'BOE_BANK_RATE': 'BOERATENUM',
}


def _fred_latest(series_id, fred_key):
    """Returns (value, date) from FRED's latest observation, or None."""
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {"series_id": series_id, "api_key": fred_key, "file_type": "json",
                  "sort_order": "desc", "limit": 1}
        resp = requests.get(url, params=params, headers=REQ_HEADERS, timeout=5)
        if resp.status_code == 200:
            obs = resp.json().get('observations', [])
            if obs and obs[0].get('value') not in ['.', None]:
                return float(obs[0]['value']), obs[0].get('date')
    except Exception as e:
        logger.debug(f"FRED fetch failed for {series_id}: {e}")
    return None


def _staleness(symbol, as_of_date_str):
    threshold = STALENESS_THRESHOLD_DAYS.get(symbol, 60)
    try:
        as_of = datetime.datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        days = (datetime.date.today() - as_of).days
        return days, days > threshold
    except (ValueError, TypeError):
        return None, False


def get_policy_rate(symbol, fred_key="", eodhd_key=""):
    """Returns a fully-annotated policy-rate record for `symbol`, or None if unknown.

    Record shape (all keys always present):
      symbol, name, country, rate, value, close, date,
      provenance ('LIVE:FRED' | 'STATIC_FALLBACK'),
      is_stale (bool), staleness_days (int | None), source_note (str)
    """
    symbol = symbol.upper()
    if symbol not in STATIC_FALLBACK_RATES:
        return None

    fallback = STATIC_FALLBACK_RATES[symbol]

    if symbol in _FRED_SERIES and fred_key:
        live = _fred_latest(_FRED_SERIES[symbol], fred_key)
        if live is not None:
            value, date = live
            return {
                'symbol': symbol, 'name': fallback['name'], 'country': fallback['country'],
                'rate': value, 'value': value, 'close': value, 'date': date,
                'provenance': 'LIVE:FRED', 'is_stale': False, 'staleness_days': 0,
                'source_note': f"Live FRED series {_FRED_SERIES[symbol]}, as of {date}.",
            }

    days, is_stale = _staleness(symbol, fallback['date'])
    return {
        'symbol': symbol, 'name': fallback['name'], 'country': fallback['country'],
        'rate': fallback['rate'], 'value': fallback['rate'], 'close': fallback['rate'],
        'date': fallback['date'],
        'provenance': 'STATIC_FALLBACK', 'is_stale': is_stale, 'staleness_days': days,
        'source_note': (
            f"Static fallback value as of last confirmed decision on {fallback['date']}; "
            f"not independently re-verified today."
            + (f" STALE: {days} days since last verification." if is_stale else "")
        ),
    }


def get_all_policy_rates(fred_key="", eodhd_key=""):
    """Returns {symbol: record} for every symbol this module knows about."""
    return {
        sym: get_policy_rate(sym, fred_key=fred_key, eodhd_key=eodhd_key)
        for sym in STATIC_FALLBACK_RATES
    }
