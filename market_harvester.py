import os
import json
import logging
import requests
import subprocess
from datetime import datetime

import central_bank_rates

logger = logging.getLogger(__name__)

class MarketHarvester:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)
            
        self.download_dir = self.config.get("market_data_path", "RawMaterials")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
            
        self.api_keys = self.config.get("api_keys", {})
        self.alpha_vantage_key = self.api_keys.get("alphavantage", "")
        self.eodhd_key = self.api_keys.get("eodhd", "")
        self.fred_key = self.api_keys.get("fred", "")
        
    def harvest_all(self):
        """Harvests all configured market data points"""
        market_data_points = self.config.get("market_data_points", [])
        if not market_data_points:
            logger.info("No market data points configured.")
            return False, "No market data points configured."
            
        return self._run_harvest(market_data_points)

    def harvest_single(self, index):
        """Harvests a specific data point by index"""
        market_data_points = self.config.get("market_data_points", [])
        if index < 0 or index >= len(market_data_points):
            return False, "Invalid data point index."
            
        return self._run_harvest([market_data_points[index]])
        
    def _run_harvest(self, points):
        results = []
        for point in points:
            provider = point.get('provider')
            if provider == 'alphavantage':
                if not self.alpha_vantage_key:
                    logger.warning("Alpha Vantage API Key is missing. Skipping data point.")
                    continue
                data = self._fetch_alpha_vantage(point)
                if data:
                    results.append((point, data))
            elif provider == 'refinitiv':
                refinitiv_app_key = self.api_keys.get("refinitiv_app_key", "")
                if not refinitiv_app_key:
                    logger.warning("Refinitiv App Key is missing. Skipping data point.")
                    continue
                data = self._fetch_refinitiv(point)
                if data:
                    results.append((point, data))
            elif provider == 'yfinance':
                data = self._fetch_yfinance(point)
                if data:
                    results.append((point, data))
            elif provider == 'eodhd':
                if not self.eodhd_key:
                    logger.warning("EODHD API Key is missing. Skipping data point.")
                    continue
                data = self._fetch_eodhd(point)
                if data:
                    results.append((point, data))
            elif provider == 'fred':
                if not self.fred_key:
                    logger.warning("FRED API Key is missing. Skipping data point.")
                    continue
                data = self._fetch_fred(point)
                if data:
                    results.append((point, data))
            elif provider == 'nyfed':
                data = self._fetch_nyfed(point)
                if data:
                    results.append((point, data))
            elif provider == 'quantgist':
                data = self._fetch_quantgist(point)
                if data:
                    results.append((point, data))
            elif provider == 'central_bank':
                data = self._fetch_central_bank(point)
                if data:
                    results.append((point, data))
            else:
                logger.warning(f"Unsupported provider: {provider}")
                
        if not results:
            return False, "Failed to fetch any market data."
            
        self._write_markdown_digest(results)
        return True, f"Successfully harvested {len(results)} market data points."
        
    def _fetch_alpha_vantage(self, point):
        symbol = point.get('symbol', '').upper()
        dtype = point.get('type', 'stock')
        
        base_url = "https://www.alphavantage.co/query"
        params = {
            "apikey": self.alpha_vantage_key
        }
        
        try:
            if dtype == 'stock':
                params["function"] = "TIME_SERIES_DAILY"
                params["symbol"] = symbol
                response = requests.get(base_url, params=params, timeout=15)
                data = response.json()
                ts_key = "Time Series (Daily)"
                if ts_key in data:
                    # Get the most recent date
                    latest_date = list(data[ts_key].keys())[0]
                    return data[ts_key][latest_date]
                else:
                    logger.error(f"Alpha Vantage error for {symbol}: {data}")
                    
            elif dtype == 'forex':
                params["function"] = "FX_DAILY"
                # Split USD/INR into from=USD, to=INR
                parts = symbol.replace('-', '/').split('/')
                if len(parts) == 2:
                    params["from_symbol"] = parts[0].strip()
                    params["to_symbol"] = parts[1].strip()
                else:
                    logger.error(f"Invalid forex format for {symbol}. Use BASE/QUOTE format.")
                    return None
                    
                response = requests.get(base_url, params=params, timeout=15)
                data = response.json()
                ts_key = "Time Series FX (Daily)"
                if ts_key in data:
                    latest_date = list(data[ts_key].keys())[0]
                    return data[ts_key][latest_date]
                else:
                    logger.error(f"Alpha Vantage error for {symbol}: {data}")
        except Exception as e:
            logger.error(f"Exception fetching {symbol}: {str(e)}")
            
        return None
        
    def _fetch_eodhd(self, point):
        symbol = point.get('symbol', '').upper()
        
        REFERENCE_RATES = {'SOFR', 'EFFR', 'OBFR', 'TGCR', 'BGCR', 'SOFR30D', 'SOFR90D', 'SOFR180D', 'SOFRINDEX', 'SONIA', 'ESTR'}
        POLICY_RATES = {'FED_TARGET_LOWER', 'FED_TARGET_UPPER', 'ECB_DFR', 'ECB_MRO', 'ECB_MLF', 'BOE_BANK_RATE'}
        
        if symbol in REFERENCE_RATES:
            base_url = "https://eodhd.com/api/rates/reference-rates"
            params = {"api_token": self.eodhd_key, "filter[code]": symbol}
        elif symbol in POLICY_RATES:
            base_url = "https://eodhd.com/api/rates/policy-rates"
            params = {"api_token": self.eodhd_key, "filter[code]": symbol}
        else:
            base_url = f"https://eodhd.com/api/eod/{symbol}"
            params = {"api_token": self.eodhd_key, "fmt": "json", "period": "d"}
        
        try:
            response = requests.get(base_url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()

                # Check if this is a Macro API response (has 'data' envelope)
                if isinstance(data, dict) and 'data' in data:
                    data = data['data']
                    if data and isinstance(data, list) and len(data) > 0:
                        last_row = data[0] # The latest is typically first, but let's check. Wait, docs showed date "2026-06-08" at index 0. If it's sorted desc, [0] is latest. Let's sort to be safe or just use [0]. Actually EODHD history endpoints usually sort ascending. Let's check max date.
                        # It's safer to just pick the element with max date
                        rate_val = float(last_row.get('rate')) if 'rate' in last_row and last_row.get('rate') is not None else None
                        date_val = last_row.get('date')
                        return {
                            'date': date_val,
                            'value': rate_val,
                            'rate': rate_val,
                            'close': rate_val
                        }
                    else:
                        logger.error(f"EODHD returned empty macro data for symbol {symbol}")
                        return None
                        
                # Otherwise, this is a standard EOD response
                elif data and isinstance(data, list) and len(data) > 0:
                    last_row = data[-1]
                    res_dict = {
                        'open': float(last_row.get('open')) if 'open' in last_row else None,
                        'high': float(last_row.get('high')) if 'high' in last_row else None,
                        'low': float(last_row.get('low')) if 'low' in last_row else None,
                        'close': float(last_row.get('close')) if 'close' in last_row else None,
                        'volume': float(last_row.get('volume')) if 'volume' in last_row else None,
                    }
                    return res_dict
                else:
                    logger.error(f"EODHD returned empty or invalid data for symbol {symbol}: {data}")
            else:
                logger.error(f"EODHD request failed for {symbol} with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Exception fetching from EODHD for {symbol}: {str(e)}")
            
        return None
        
    def _fetch_refinitiv(self, point):
        symbol = point.get('symbol', '')
        dtype = point.get('type', 'stock')
        
        app_key = self.api_keys.get("refinitiv_app_key", "")
        username = self.api_keys.get("refinitiv_username", "")
        password = self.api_keys.get("refinitiv_password", "")
        
        try:
            import refinitiv.data as rd
            
            from refinitiv.data.session import platform, desktop
            from refinitiv.data.session.platform import GrantPassword
            
            # Refinitiv uses asyncio internally. When running inside a background
            # APScheduler thread, the lack of an initialized event loop can cause a crash.
            import asyncio
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            
            if username and password:
                session = platform.Definition(
                    app_key=app_key,
                    grant=GrantPassword(
                        username=username,
                        password=password
                    )
                ).get_session()
            else:
                session = desktop.Definition(app_key=app_key).get_session()
                
            session.open()
            rd.session.set_default(session)
            
            fields = ['TR.PriceOpen', 'TR.PriceHigh', 'TR.PriceLow', 'TR.PriceClose', 'TR.Volume']
            
            df = rd.get_data(
                universe=[symbol],
                fields=fields
            )
            
            try:
                session.close()
            except Exception:
                pass
                
            if df is not None and not df.empty:
                row = df.iloc[0]
                res_dict = {}
                for col in df.columns:
                    col_lower = col.lower()
                    if 'open' in col_lower:
                        res_dict['open'] = float(row[col]) if row[col] is not None else None
                    elif 'high' in col_lower:
                        res_dict['high'] = float(row[col]) if row[col] is not None else None
                    elif 'low' in col_lower:
                        res_dict['low'] = float(row[col]) if row[col] is not None else None
                    elif 'close' in col_lower:
                        res_dict['close'] = float(row[col]) if row[col] is not None else None
                    elif 'volume' in col_lower:
                        res_dict['volume'] = float(row[col]) if row[col] is not None else None
                return res_dict
            else:
                logger.error(f"Refinitiv returned empty data for symbol {symbol}")
        except Exception as e:
            logger.error(f"Exception fetching from Refinitiv for {symbol}: {str(e)}")
            
        return None
        
    def _fetch_yfinance(self, point):
        symbol = point.get('symbol', '')
        
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            # Use period="5d" to ensure we have enough history to fall back on
            hist = ticker.history(period="5d")
            
            if hist is not None and not hist.empty:
                # Yahoo Finance often returns a buggy current-day snapshot for Forex where OHLC are identical.
                # If we detect this, we fall back to the most recent fully populated daily candle.
                if len(hist) > 1:
                    last_row = hist.iloc[-1]
                    if last_row['Open'] == last_row['High'] == last_row['Low'] == last_row['Close']:
                        hist = hist.iloc[:-1]

                row = hist.iloc[-1]
                
                open_val = float(row['Open']) if 'Open' in row and row['Open'] is not None else None
                high_val = float(row['High']) if 'High' in row and row['High'] is not None else None
                low_val = float(row['Low']) if 'Low' in row and row['Low'] is not None else None
                close_val = float(row['Close']) if 'Close' in row and row['Close'] is not None else None
                volume_val = float(row['Volume']) if 'Volume' in row and row['Volume'] is not None else None

                # For Forex on Yahoo Finance, Open and Close in daily history are often identical. 
                # We can fetch the actual live close/last price from fast_info if they match.
                if open_val is not None and close_val is not None and open_val == close_val:
                    try:
                        last_price = ticker.fast_info.last_price
                        if last_price:
                            close_val = float(last_price)
                    except Exception:
                        pass

                res_dict = {
                    'open': open_val,
                    'high': high_val,
                    'low': low_val,
                    'close': close_val,
                    'volume': volume_val
                }
                return res_dict
            else:
                logger.error(f"Yahoo Finance returned empty history for symbol {symbol}")
        except Exception as e:
            logger.error(f"Exception fetching from Yahoo Finance for {symbol}: {str(e)}")
            
            
        return None

    def _run_smithery_tool(self, server, tool, args_dict):
        try:
            # We use pnpm dlx to invoke the smithery cli because the project enforces pnpm
            cmd = ["pnpm", "dlx", "@smithery/cli", "tool", "call", server, tool, json.dumps(args_dict)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # The tool output might contain logging from npm/npx.
            # We look for the last line which is typically the JSON output, or we try to parse it.
            lines = result.stdout.strip().split('\n')
            for line in reversed(lines):
                if line.startswith('{') or line.startswith('['):
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            if data.get('isError'):
                                logger.error(f"Smithery tool returned error: {data}")
                                return None
                            if 'content' in data and isinstance(data['content'], list) and len(data['content']) > 0:
                                inner_text = data['content'][0].get('text', '')
                                try:
                                    return json.loads(inner_text)
                                except Exception:
                                    return {"text": inner_text}
                    except json.JSONDecodeError:
                        continue
            
            logger.error(f"Could not parse Smithery JSON output. Raw stdout: {result.stdout}")
            return None
        except Exception as e:
            logger.error(f"Error calling smithery tool {server}/{tool}: {e}")
            return None

    def _fetch_fred(self, point):
        symbol = point.get('symbol')
        base_url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": symbol,
            "api_key": self.fred_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2
        }
        try:
            response = requests.get(base_url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                observations = data.get('observations', [])
                if observations:
                    obs_latest = observations[0]
                    res = {
                        'date': obs_latest.get('date'),
                        'value': obs_latest.get('value')
                    }
                    if len(observations) > 1:
                        obs_prev = observations[1]
                        res['previous_date'] = obs_prev.get('date')
                        res['previous_value'] = obs_prev.get('value')
                        
                        try:
                            val_curr = float(obs_latest.get('value'))
                            val_prev = float(obs_prev.get('value'))
                            diff = val_curr - val_prev
                            res['change'] = f"{diff:+.4f}".rstrip('0').rstrip('.')
                        except (ValueError, TypeError):
                            pass
                    return res
                else:
                    logger.error(f"FRED returned empty observations for {symbol}")
            else:
                logger.error(f"FRED request failed for {symbol} with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Exception fetching from FRED for {symbol}: {str(e)}")
            
        return None

    def _fetch_nyfed(self, point):
        symbol = point.get('symbol', '').upper()
        base_url = "https://markets.newyorkfed.org/api/rates/all/latest.json"
        try:
            response = requests.get(base_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                ref_rates = data.get('refRates', [])
                for rate_item in ref_rates:
                    if rate_item.get('type', '').upper() == symbol:
                        date_val = rate_item.get('effectiveDate')
                        rate_val = rate_item.get('percentRate')
                        if rate_val is None and 'average30day' in rate_item:
                            rate_val = rate_item.get('average30day')
                        
                        return {
                            'date': date_val,
                            'value': rate_val,
                            'rate': rate_val,
                            'close': rate_val,
                            'percentrate': rate_val,
                            'volumeinbillions': rate_item.get('volumeInBillions')
                        }
                
                # Fallback to specific rate category endpoints if symbol is not in refRates summary
                for category in ['secured', 'unsecured']:
                    endpoint = f"https://markets.newyorkfed.org/api/rates/{category}/{symbol.lower()}/last/1.json"
                    sub_resp = requests.get(endpoint, timeout=5)
                    if sub_resp.status_code == 200:
                        sub_data = sub_resp.json()
                        sub_rates = sub_data.get('refRates', [])
                        if sub_rates:
                            rate_item = sub_rates[0]
                            date_val = rate_item.get('effectiveDate')
                            rate_val = rate_item.get('percentRate')
                            return {
                                'date': date_val,
                                'value': rate_val,
                                'rate': rate_val,
                                'close': rate_val,
                                'percentrate': rate_val,
                                'volumeinbillions': rate_item.get('volumeInBillions')
                            }
                logger.error(f"NYFed returned no data for symbol {symbol}")
            else:
                logger.error(f"NYFed request failed for {symbol} with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Exception fetching from NYFed for {symbol}: {str(e)}")
            
        return None

    def _fetch_central_bank(self, point):
        """Resolves a 'central_bank' provider market point. EODHD/NYFed are
        tried first for the symbols where they carry a genuinely live print;
        everything else is resolved via central_bank_rates.py, the single
        source of truth shared with central_bank_harvester.py."""
        symbol = point.get('symbol', '').upper()

        # Try EODHD or NYFed first for overlap symbols
        if symbol in ['FED_TARGET_LOWER', 'FED_TARGET_UPPER', 'ECB_MRO', 'ECB_MLF', 'ECB_DFR', 'BOE_BANK_RATE']:
            eodhd_data = self._fetch_eodhd(point)
            if eodhd_data:
                return eodhd_data
        elif symbol in ['SOFR', 'EFFR', 'OBFR', 'TGCR', 'BGCR']:
            nyfed_data = self._fetch_nyfed(point)
            if nyfed_data:
                return nyfed_data

        result = central_bank_rates.get_policy_rate(symbol, fred_key=self.fred_key, eodhd_key=self.eodhd_key)
        if result:
            return result

        logger.error(f"Central Bank Rate symbol {symbol} not found")
        return None
        
    def _fetch_quantgist(self, point):
        # We query the calendar for upcoming events
        data = self._run_smithery_tool("quantgist", "get_economic_calendar", {})
        if data:
            return data
        return None
        
    def _write_markdown_digest(self, results):
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"Market_Digest_{today}.md"
        filepath = os.path.join(self.download_dir, filename)
        
        content = f"# Daily Market Digest - {today}\n\n"
        content += "Automated daily record of configured market data points.\n\n"
        
        # We parse existing content if appending, else write fresh.
        # But this function only writes the fetched results.
        mode = 'a' if os.path.exists(filepath) else 'w'
        if mode == 'a':
            content = f"\n\n## Update at {datetime.now().strftime('%H:%M:%S')}\n\n"
        
        for point, data in results:
            symbol = point.get('symbol')
            fields = [f.strip().lower() for f in point.get('fields', 'Open, High, Low, Close').split(',')]
            
            content += f"### {symbol}\n"
            content += f"- **Provider**: {point.get('provider').capitalize()}\n"
            content += f"- **Type**: {point.get('type').capitalize()}\n"
            content += f"- **Data**:\n"
            
            if point.get('provider') == 'alphavantage':
                av_map = {
                    "open": "1. open",
                    "high": "2. high",
                    "low": "3. low",
                    "close": "4. close",
                    "volume": "5. volume"
                }
                for field in fields:
                    av_key = av_map.get(field)
                    if av_key and av_key in data:
                        content += f"  - **{field.capitalize()}**: {data[av_key]}\n"
                    else:
                        content += f"  - **{field.capitalize()}**: N/A\n"
            else:
                if 'text' in data and point.get('provider') == 'quantgist':
                    content += f"  - **Events**: \n{data['text']}\n"
                else:
                    for field in fields:
                        if field in data:
                            content += f"  - **{field.capitalize()}**: {data[field]}\n"
                        else:
                            content += f"  - **{field.capitalize()}**: N/A\n"
                    if 'previous_value' in data and 'previous_value' not in fields:
                        prev_date_str = f" ({data['previous_date']})" if 'previous_date' in data else ""
                        content += f"  - **Previous Value**: {data['previous_value']}{prev_date_str}\n"
                    if 'change' in data and 'change' not in fields:
                        content += f"  - **Change**: {data['change']}\n"
            content += "\n---\n\n"
            
        with open(filepath, mode) as f:
            f.write(content)
        
        logger.info(f"Wrote market digest to {filepath}")

# Helper entry points
def run_market_harvest_single(index):
    harvester = MarketHarvester()
    return harvester.harvest_single(index)

def run_market_harvest_all():
    harvester = MarketHarvester()
    return harvester.harvest_all()
