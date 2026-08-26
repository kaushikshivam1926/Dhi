"""Lightweight historical ledger for macro/market data points.

Enables real day/week/month comparisons ("+X% from yesterday", "HELD since
<date>") instead of a digest with zero memory of its own past runs. Backed by
stdlib sqlite3, stored in the repo working directory (never inside the
iCloud-synced Obsidian vault, to avoid sync-driven corruption of a live DB
file) — same convention as sync_history.json / feed_cache.json.

Every function opens and closes its own short-lived connection rather than
holding a module-level connection open, since this runs inside APScheduler's
background-thread execution model.
"""

import os
import re
import glob
import logging
import sqlite3
import datetime

logger = logging.getLogger(__name__)

DB_PATH_DEFAULT = "macro_history.db"


def _connect(db_path):
    return sqlite3.connect(db_path)


def init_db(db_path=DB_PATH_DEFAULT):
    """Idempotent: creates the observations table if it doesn't exist."""
    conn = _connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                series_id   TEXT NOT NULL,
                obs_date    TEXT NOT NULL,
                value       REAL,
                provenance  TEXT,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (series_id, obs_date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_date ON observations(series_id, obs_date)")
        conn.commit()
    finally:
        conn.close()


def count_observations(db_path=DB_PATH_DEFAULT):
    conn = _connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    finally:
        conn.close()


def record_observations_bulk(rows, db_path=DB_PATH_DEFAULT):
    """rows: list of (series_id, obs_date, value, provenance). Idempotent
    (INSERT OR REPLACE keyed on series_id+obs_date) — safe to re-run same-day."""
    if not rows:
        return 0
    now_iso = datetime.datetime.now().isoformat()
    conn = _connect(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO observations (series_id, obs_date, value, provenance, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(sid, od, val, prov, now_iso) for (sid, od, val, prov) in rows],
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def primary_value(data):
    """Picks the representative numeric field from a fetch result dict,
    trying close, then value, then rate; skips None/''/'.' (FRED's no-data sentinel)."""
    if not isinstance(data, dict):
        return None
    for key in ('close', 'value', 'rate'):
        v = data.get(key)
        if v is None or v == '' or v == '.':
            continue
        try:
            return float(v)
        except (ValueError, TypeError):
            continue
    return None


def ingest_market_results(market_results, obs_date, db_path=DB_PATH_DEFAULT):
    """Adapter for CentralBankHarvester.fetch_macro_market_points() output:
    list of (point_dict, data_dict) tuples."""
    rows = []
    for point, data in market_results:
        sym = (point.get('symbol') or '').upper()
        if not sym:
            continue
        val = primary_value(data)
        if val is None:
            continue
        provenance = f"LIVE:{(point.get('provider') or 'unknown').upper()}"
        rows.append((f"{sym}.value", obs_date, val, provenance))
    return record_observations_bulk(rows, db_path)


def ingest_policy_rates(cb_rates, obs_date, db_path=DB_PATH_DEFAULT):
    """Adapter for central_bank_rates.get_all_policy_rates() output."""
    rows = []
    for sym, rec in (cb_rates or {}).items():
        if not rec:
            continue
        val = primary_value(rec)
        if val is None:
            continue
        provenance = rec.get('provenance', 'UNKNOWN') if isinstance(rec, dict) else 'UNKNOWN'
        rows.append((f"{sym.upper()}.value", obs_date, val, provenance))
    return record_observations_bulk(rows, db_path)


def _row_leq(conn, series_id, date_str):
    return conn.execute(
        "SELECT obs_date, value FROM observations WHERE series_id=? AND obs_date<=? "
        "ORDER BY obs_date DESC LIMIT 1",
        (series_id, date_str),
    ).fetchone()


def _row_lt(conn, series_id, date_str):
    return conn.execute(
        "SELECT obs_date, value FROM observations WHERE series_id=? AND obs_date<? "
        "ORDER BY obs_date DESC LIMIT 1",
        (series_id, date_str),
    ).fetchone()


def _change_block(latest_value, row):
    if row is None:
        return None
    date, value = row
    if value is None or latest_value is None:
        return None
    change = latest_value - value
    pct = (change / value * 100) if value else None
    return {'date': date, 'value': value, 'change': change, 'pct_change': pct}


def compute_deltas(series_id, as_of_date, db_path=DB_PATH_DEFAULT):
    """Real historical comparison for one series, each lookup resolving to
    'most recent obs_date <= target date' so weekends/gaps resolve naturally.

    Returns {latest, prev_day, prev_week, prev_month, range_30d, n_obs}.
    """
    conn = _connect(db_path)
    try:
        latest_row = _row_leq(conn, series_id, as_of_date)
        if latest_row is None:
            return {'latest': None, 'prev_day': None, 'prev_week': None,
                    'prev_month': None, 'range_30d': None, 'n_obs': 0}

        latest_date, latest_value = latest_row
        prev_day_row = _row_lt(conn, series_id, latest_date)

        as_of_dt = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
        week_target = (as_of_dt - datetime.timedelta(days=7)).isoformat()
        month_target = (as_of_dt - datetime.timedelta(days=30)).isoformat()
        prev_week_row = _row_leq(conn, series_id, week_target)
        prev_month_row = _row_leq(conn, series_id, month_target)

        range_start = (as_of_dt - datetime.timedelta(days=30)).isoformat()
        range_row = conn.execute(
            "SELECT MIN(value), MAX(value) FROM observations "
            "WHERE series_id=? AND obs_date>=? AND obs_date<=? AND value IS NOT NULL",
            (series_id, range_start, as_of_date),
        ).fetchone()
        range_30d = {'min': range_row[0], 'max': range_row[1]} if range_row and range_row[0] is not None else None

        n_obs = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id=?", (series_id,)
        ).fetchone()[0]

        return {
            'latest': {'date': latest_date, 'value': latest_value},
            'prev_day': _change_block(latest_value, prev_day_row),
            'prev_week': _change_block(latest_value, prev_week_row),
            'prev_month': _change_block(latest_value, prev_month_row),
            'range_30d': range_30d,
            'n_obs': n_obs,
        }
    finally:
        conn.close()


def detect_policy_rate_status(series_id, latest_value, latest_date, db_path=DB_PATH_DEFAULT):
    """'FIRST_OBSERVATION' | 'CHANGED_TODAY' | 'HELD', comparing against the
    most recent PRIOR stored observation (obs_date < latest_date)."""
    conn = _connect(db_path)
    try:
        prior = _row_lt(conn, series_id, latest_date)
        if prior is None or prior[1] is None or latest_value is None:
            return 'FIRST_OBSERVATION'
        return 'HELD' if abs(prior[1] - latest_value) < 1e-9 else 'CHANGED_TODAY'
    finally:
        conn.close()


def _parse_number(raw):
    if raw is None:
        return None
    raw = raw.strip()
    if raw.upper() == 'N/A' or raw == '':
        return None
    try:
        return float(raw.replace(',', ''))
    except ValueError:
        return None


def _apply_patterns(content, patterns):
    """patterns: list of (regex, [series_id_or_None, ...]) where list position
    maps to the regex's capture group position. Returns {series_id: value}."""
    results = {}
    for pattern, series_ids in patterns:
        m = re.search(pattern, content)
        if not m:
            continue
        for idx, series_id in enumerate(series_ids):
            if series_id is None:
                continue
            val = _parse_number(m.group(idx + 1))
            if val is not None:
                results[series_id] = val
    return results


# Regex patterns matched against the known prose template produced by
# market_digest_engine's deterministic report (and, closely enough, its LLM
# variants). Best-effort only — used purely to bootstrap history from the
# ~28 files already sitting in the vault; a missed field just means one less
# backfilled data point, never an error.
_CB_DIGEST_PATTERNS = [
    (r'opened at ([\d.]+) and recorded an intraday low of ([\d.]+) and an intraday high of ([\d.]+), before settling at ([\d.]+)',
     [None, None, None, 'USDINR=X']),
    (r'effective funds rate \(EFFR\) stands at ([\d.]+)% with SOFR fixing at ([\d.]+)%', ['EFFR', 'SOFR']),
    (r'Dollar Index \(DXY\) is hovering around ([\d.]+|N/A)', ['DX-Y.NYB']),
    (r'Brent crude is trading near \$([\d.]+)', ['BZ=F']),
    (r'2-year and 10-year Treasury yields stand at ([\d.]+|N/A)% and ([\d.]+|N/A)%', ['DGS2', 'DGS10']),
    (r'RBI Repo Rate: ([\d.]+)%', ['RBI_REPO']),
    (r'BoJ Call Rate: ([\d.]+)%', ['BOJ_POLICY']),
    (r'RBA Cash Rate: ([\d.]+)%', ['RBA_CASH']),
    (r'ECB Deposit Rate: ([\d.]+)%', ['ECB_DFR']),
    (r'BoE Bank Rate: ([\d.]+)%', ['BOE_BANK_RATE']),
    (r'SNB Policy Rate: ([\d.]+)%', ['SNB_POLICY']),
    (r'PBoC 1Y LPR: ([\d.]+)%', ['PBOC_LPR_1Y']),
    (r'Riksbank Rate: ([\d.]+)%', ['RIKSBANK_POLICY']),
    (r'Sensex at ([\d.,]+)', ['^BSESN']),
    (r'Nifty 50 at ([\d.,]+)', ['^NSEI']),
    (r'S&P 500 at ([\d.,]+|N/A)', ['^GSPC']),
    (r'Nasdaq at ([\d.,]+|N/A)', ['^IXIC']),
    (r'Dow Jones at ([\d.,]+|N/A)', ['^DJI']),
    (r'Nikkei 225 at ([\d.,]+|N/A)', ['^N225']),
    (r'Hang Seng at ([\d.,]+|N/A)', ['^HSI']),
    (r'DXY Index: ([\d.]+|N/A)', ['DX-Y.NYB']),
    (r'EUR/USD: ([\d.]+|N/A)', ['EURUSD=X']),
    (r'GBP/USD: ([\d.]+|N/A)', ['GBPUSD=X']),
    (r'USD/JPY: ([\d.]+|N/A)', ['JPY=X']),
    (r'AUD/USD: ([\d.]+|N/A)', ['AUDUSD=X']),
    (r'Gold: \$([\d.]+|N/A)', ['GC=F']),
]


def _parse_cb_digest_file(path):
    m = re.search(r'CentralBank_Macro_Digest_(\d{4}-\d{2}-\d{2})\.md$', os.path.basename(path))
    if not m:
        return []
    obs_date = m.group(1)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    values = _apply_patterns(content, _CB_DIGEST_PATTERNS)
    return [(f"{sym.upper()}.value", obs_date, val, 'BACKFILL:CB_DIGEST') for sym, val in values.items()]


def _parse_market_digest_file(path):
    """Market_Digest_*.md uses a structured '### SYMBOL' / '- **Field**: value'
    format and may have several same-day '## Update at HH:MM:SS' sections
    appended through the day — later blocks for the same symbol naturally
    overwrite earlier ones since dict insertion order follows file order."""
    m = re.search(r'Market_Digest_(\d{4}-\d{2}-\d{2})\.md$', os.path.basename(path))
    if not m:
        return []
    obs_date = m.group(1)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    values = {}
    for block in re.finditer(r'### (\S+)\n(.*?)(?=\n### |\Z)', content, re.DOTALL):
        symbol = block.group(1).strip().upper()
        body = block.group(2)
        fields = {}
        for line in re.finditer(r'-\s*\*\*(\w+)\*\*:\s*(.+)', body):
            fields[line.group(1).lower()] = line.group(2).strip()
        for key in ('close', 'value', 'rate'):
            if key in fields:
                parsed = _parse_number(fields[key])
                if parsed is not None:
                    values[f"{symbol}.value"] = parsed
                    break

    return [(series_id, obs_date, val, 'BACKFILL:MARKET_DIGEST') for series_id, val in values.items()]


def backfill_from_vault(vault_dir, db_path=DB_PATH_DEFAULT):
    """One-time (idempotent, safe to re-run) seed of real history from the
    Market_Digest_*.md / CentralBank_Macro_Digest_*.md files already sitting
    in the vault. Returns {'files_scanned', 'observations_recorded', 'errors'}."""
    result = {'files_scanned': 0, 'observations_recorded': 0, 'errors': []}
    if not vault_dir or not os.path.isdir(vault_dir):
        result['errors'].append(f"Vault directory not found: {vault_dir}")
        return result

    for path in sorted(glob.glob(os.path.join(vault_dir, "Market_Digest_*.md"))):
        try:
            rows = _parse_market_digest_file(path)
            result['files_scanned'] += 1
            result['observations_recorded'] += record_observations_bulk(rows, db_path)
        except Exception as e:
            result['errors'].append(f"{os.path.basename(path)}: {e}")

    for path in sorted(glob.glob(os.path.join(vault_dir, "CentralBank_Macro_Digest_*.md"))):
        try:
            rows = _parse_cb_digest_file(path)
            result['files_scanned'] += 1
            result['observations_recorded'] += record_observations_bulk(rows, db_path)
        except Exception as e:
            result['errors'].append(f"{os.path.basename(path)}: {e}")

    if result['errors']:
        logger.warning(f"macro_history backfill had {len(result['errors'])} error(s): {result['errors'][:5]}")
    logger.info(
        f"macro_history backfill: {result['files_scanned']} files scanned, "
        f"{result['observations_recorded']} observations recorded."
    )
    return result
