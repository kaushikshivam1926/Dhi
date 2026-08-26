import os
import sys
import time
import tempfile
import datetime
from unittest.mock import MagicMock

# Mock optional heavy modules imported by doc_processor if not installed
for mod in ['docx', 'pypandoc', 'bs4', 'google', 'google.genai', 'google.genai.types']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

try:
    import pytest
except ImportError:
    import math
    class _MockPytest:
        @staticmethod
        def approx(val, rel=1e-6, abs=1e-12):
            class _Approx:
                def __eq__(self, other):
                    return math.isclose(val, other, rel_tol=rel, abs_tol=abs)
            return _Approx()
    pytest = _MockPytest()

import macro_history
from market_digest_engine import MarketDigestEngine

def test_compute_deltas_bulk_correctness():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        macro_history.init_db(db_path)

        # Empty inputs
        assert macro_history.compute_deltas_bulk([], "2026-03-01", db_path) == {}
        assert macro_history.compute_deltas_bulk(["", None], "2026-03-01", db_path) == {}

        # Non-existent series
        res = macro_history.compute_deltas_bulk(["NONEXISTENT.value"], "2026-03-01", db_path)
        assert res["NONEXISTENT.value"] == {
            'latest': None, 'prev_day': None, 'prev_week': None,
            'prev_month': None, 'range_30d': None, 'n_obs': 0
        }

        # Seed data for multiple series across 60 days
        rows = []
        base_date = datetime.date(2026, 1, 1)
        series_list = [f"SYM_{i}.value" for i in range(20)]
        for i in range(60):
            d_str = (base_date + datetime.timedelta(days=i)).isoformat()
            for sym in series_list:
                rows.append((sym, d_str, 100.0 + i * 0.5, "TEST"))

        macro_history.record_observations_bulk(rows, db_path)
        obs_date = "2026-03-01"

        # Compare output of compute_deltas_bulk against individual compute_deltas calls
        bulk_res = macro_history.compute_deltas_bulk(series_list + ["SYM_0.value", "NONEXISTENT.value"], obs_date, db_path)

        for sym in series_list + ["NONEXISTENT.value"]:
            single_res = macro_history.compute_deltas(sym, obs_date, db_path)
            assert bulk_res[sym] == single_res

def test_market_digest_engine_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        macro_history.init_db(db_path)

        rows = [
            ("USDINR=X.value", "2026-02-28", 82.50, "TEST"),
            ("USDINR=X.value", "2026-03-01", 82.75, "TEST"),
            ("FED_RATE.value", "2026-02-28", 5.25, "TEST"),
            ("FED_RATE.value", "2026-03-01", 5.25, "TEST"),
        ]
        macro_history.record_observations_bulk(rows, db_path)

        engine = MarketDigestEngine()
        engine.cb_config["macro_history_db_path"] = db_path

        market_results = [
            ({'symbol': 'USDINR=X', 'type': 'FX', 'provider': 'yfinance'}, {'close': 82.75, 'low': 82.40, 'high': 82.90})
        ]
        cb_data = {
            'central_bank_rates': {
                'fed_rate': {'value': 5.25, 'name': 'Fed Funds', 'country': 'US', 'date': '2026-03-01', 'provenance': 'LIVE'}
            }
        }

        deltas = engine._compute_history_deltas(market_results, cb_data, "2026-03-01")
        assert "USDINR=X.value" in deltas
        assert "FED_RATE.value" in deltas
        assert deltas["USDINR=X.value"]["latest"]["value"] == 82.75
        assert deltas["USDINR=X.value"]["prev_day"]["change"] == pytest.approx(0.25)
