from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import json
import os

# Fix macOS segmentation faults when native libraries (like gRPC, MLX, or Refinitiv) fork
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

import datetime
import atexit
from main import execute_sync, clear_vault_history, execute_sync_generator, cancel_event
from doc_processor import process_documents_generator, get_document_stats
from web_harvester import WebHarvester
from arxiv_harvester import ArxivHarvester
from research_harvester import ResearchHarvester
from database import db
from scheduler import add_schedule, list_schedules, cancel_schedule, delete_schedule, get_scheduler, shutdown_scheduler
from audio_overview_engine import AudioOverviewEngine, AVAILABLE_VOICES

app = Flask(__name__, static_folder='public')
CORS(app)

harvester = WebHarvester()
arxiv_harvester = ArxivHarvester()

# Start scheduler eagerly on import so pending jobs are re-registered
get_scheduler()
atexit.register(shutdown_scheduler)

CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.json'))

research_harvester = ResearchHarvester(config_path=CONFIG_PATH, arxiv=arxiv_harvester)
audio_engine = AudioOverviewEngine(config_path=CONFIG_PATH)


@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# Global state for migration
MAULT_SCANNED = False

@app.route('/api/config', methods=['GET'])
def get_config():
    global MAULT_SCANNED
    
    if not os.path.exists(CONFIG_PATH):
        # ... (default config logic)
        return jsonify({
            "obsidian_vault_path": "./Vault", 
            "raw_material_path": "./RawMaterials",
            "transcription_engine": "none", 
            "api_keys": {"assemblyai": ""}, 
            "shows": []
        })
    
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        
    # Auto-migration scan
    if not MAULT_SCANNED:
        vault_path = config.get("obsidian_vault_path", "./Vault")
        db.scan_vault_for_migration(vault_path)
        MAULT_SCANNED = True
        
    return jsonify(config)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        vault_path = config.get("obsidian_vault_path", "")
        if not vault_path or not os.path.exists(vault_path):
            return jsonify({
                "status": "error", 
                "total_insights": 0,
                "total_shows": len(config.get("shows", [])),
                "recent_insights": [],
                "message": "Vault path not configured"
            })
            
        all_md_files = []
        for root, dirs, files in os.walk(vault_path):
            # Prune hidden directories like .obsidian and .git
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md'):
                    full_path = os.path.join(root, file)
                    all_md_files.append({
                        "name": file,
                        "mtime": os.path.getmtime(full_path)
                    })
        
        # Sort by latest modification
        all_md_files.sort(key=lambda x: x["mtime"], reverse=True)
        recent_files = all_md_files[:5]
        
        recent_insights = []
        for rf in recent_files:
            # Format: 20240411_Channel_Show_Title.md
            parts = rf["name"].replace(".md", "").split("_", 3)
            date_str = parts[0] if len(parts) > 0 else "Unknown"
            channel = parts[1] if len(parts) > 1 else "Unknown"
            show = parts[2] if len(parts) > 2 else "Unknown"
            title = parts[3].replace("_", " ") if len(parts) > 3 else rf["name"]
            
            recent_insights.append({
                "title": title,
                "date": date_str,
                "channel": channel,
                "show": show
            })
            
        return jsonify({
            "status": "success",
            "total_insights": len(all_md_files),
            "total_shows": len(config.get("shows", [])),
            "recent_insights": recent_insights
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    new_config = request.json
    with open(CONFIG_PATH, 'w') as f:
        json.dump(new_config, f, indent=2)
    return jsonify({"status": "success", "message": "Config saved successfully"})

@app.route('/api/gemini/models', methods=['POST'])
def get_gemini_models():
    try:
        data = request.json or {}
        api_key = data.get('api_key')
        
        if not api_key:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                api_key = config.get("api_keys", {}).get("gemini", "")
                
        fallback_models = [
            {"value": "gemini-3.5-flash", "label": "Gemini 3.5 Flash (Latest/Speed)"},
            {"value": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite (Fastest/New)"},
            {"value": "gemini-3.1-flash", "label": "Gemini 3.1 Flash (High Efficiency)"},
            {"value": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite (Best Efficiency)"},
            {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (Balanced/Stable)"},
            {"value": "gemini-2.0-flash", "label": "Gemini 2.0 Flash (Scale/High Limits)"},
            {"value": "gemini-3.1-pro", "label": "Gemini 3.1 Pro (Highest Accuracy)"}
        ]
        
        if not api_key or "YOUR_GEMINI_KEY" in api_key:
            return jsonify({"status": "success", "models": fallback_models})
            
        from google import genai
        client = genai.Client(api_key=api_key)
        
        fetched_models = []
        for m in client.models.list():
            name = m.name or ""
            supported_actions = m.supported_actions or []
            if 'generateContent' in supported_actions and 'gemini' in name.lower():
                val = name.replace("models/", "")
                fetched_models.append({
                    "value": val,
                    "label": m.display_name or val
                })
                
        if fetched_models:
            return jsonify({"status": "success", "models": fetched_models})
        else:
            return jsonify({"status": "success", "models": fallback_models})
            
    except Exception as e:
        print(f"Error fetching Gemini models: {e}")
        return jsonify({"status": "success", "models": fallback_models})


@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
    try:
        import requests
        config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
        ollama_url = config.get("ollama_url", "http://localhost:11434").rstrip('/')
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = []
            for m in data.get('models', []):
                name = m.get('name')
                models.append({
                    "value": name,
                    "label": name
                })
            return jsonify({"status": "success", "models": models})
        else:
            return jsonify({"status": "error", "message": f"Ollama returned status {response.status_code}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Could not connect to local Ollama server ({str(e)})"}), 500


@app.route('/api/sync', methods=['POST'])
def run_sync():
    data = request.json or {}
    show_index = data.get('show_index')
    episode_index = data.get('episode_index')
    
    def generate():
        try:
            for item in execute_sync_generator(show_index=show_index, episode_index=episode_index):
                yield item
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Server stream error: {e}"}) + "\n"
            
    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
    
@app.route('/api/cancel_sync', methods=['POST'])
def cancel_sync():
    cancel_event.set()
    return jsonify({"status": "success", "message": "Cancellation signal sent"})

@app.route('/api/episodes', methods=['GET'])
def get_episodes():
    import feedparser
    import time
    from main import format_date, sanitize_filename
    
    try:
        show_index = int(request.args.get('show_index', -1))
        
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"status": "error", "message": "Config not found"}), 404
            
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            
        shows = config.get("shows", [])
        if show_index < 0 or show_index >= len(shows):
            return jsonify({"status": "error", "message": "Invalid show index"}), 400
            
        show = shows[show_index]
        rss_url = show.get("rss_url")
        if not rss_url:
            return jsonify({"status": "error", "message": "No RSS URL found"}), 400
            
        # Get vault paths for checking is_synced
        vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
        channel = show.get("channel_name", "UnknownChannel")
        show_name = show.get("show_name", "UnknownShow")
        clean_channel = sanitize_filename(channel)
        clean_show = sanitize_filename(show_name)
        # Logic for folder organisation path checking
        org_mode = config.get("folder_organisation", "per_channel")
        if org_mode == "flat":
            target_check_dir = vault_path
        else:
            target_check_dir = os.path.join(vault_path, clean_channel)
        
        # Load Cache
        cache_path = os.path.join(os.path.dirname(__file__), 'feed_cache.json')
        feed_cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                feed_cache = json.load(f)
                
        cache_entry = feed_cache.get(rss_url, {})
        etag = cache_entry.get("etag")
        modified = cache_entry.get("modified")
        last_checked = cache_entry.get("last_checked", 0)
        
        # Only do an HTTP conditional request if it's been > 5 minutes and we have data
        current_time = time.time()
        has_cached_entries = bool(cache_entry.get("entries"))
        
        if (current_time - last_checked > 300) or not has_cached_entries:
            # If we have no entries cached, DON'T use conditional headers; force a full reload
            p_etag = etag if has_cached_entries else None
            p_modified = modified if has_cached_entries else None
            
            feed = feedparser.parse(rss_url, etag=p_etag, modified=p_modified)
            
            # 304 means nothing changed, use what we have
            if hasattr(feed, 'status') and feed.status == 304:
                entries_data = cache_entry.get("entries", [])
            elif hasattr(feed, 'entries') and len(feed.entries) > 0:
                # Fresh content found
                entries_data = []
                for entry in feed.entries:
                    best_date = entry.get("published", entry.get("updated", ""))
                    pub_parsed = entry.get("published_parsed")
                    if isinstance(pub_parsed, (time.struct_time, tuple)):
                        best_date = time.strftime('%Y%m%d', pub_parsed)
                    elif isinstance(pub_parsed, list):
                        best_date = time.strftime('%Y%m%d', tuple(pub_parsed))
                    
                    entries_data.append({
                        "id": entry.get("id", entry.get("link", "")),
                        "link": entry.get("link", ""),
                        "title": entry.get("title", "Untitled Episode"),
                        "published": best_date
                    })
                
                # Update Cache with the new data
                feed_cache[rss_url] = {
                    "etag": getattr(feed, 'etag', None),
                    "modified": getattr(feed, 'modified', None),
                    "last_checked": current_time,
                    "entries": entries_data
                }
                with open(cache_path, 'w') as f:
                    json.dump(feed_cache, f)
            else:
                # If we got 0 entries (common on 301/302 redirects with Etags), 
                # keep existing data if available, otherwise just use empty
                entries_data = cache_entry.get("entries", [])
        else:
            entries_data = cache_entry.get("entries", [])
            
            
        episodes = []
        for i, entry_data in enumerate(entries_data):
            title = entry_data["title"]
            pub_date_raw = entry_data["published"]
            
            guid = entry_data.get("id", entry_data.get("link", ""))
            
            # Use database for checking sync status
            is_synced = db.is_synced(guid, vault_path=vault_path)
            
            # Fallback to title-based check for legacy/migrated items if not found by GUID
            if not is_synced:
                is_synced = db.is_synced(f"migrated-{title}", vault_path=vault_path)
            
            # Final fallback: physical file check (as before, but more of a secondary check now)
            if not is_synced:
                formatted_date = format_date(pub_date_raw)
                clean_title = sanitize_filename(title)
                filename = f"{formatted_date}_{clean_channel}_{clean_show}_{clean_title}.md"
                filepath = os.path.join(target_check_dir, filename)
                is_synced = os.path.exists(filepath)
            
            episodes.append({
                "index": i,
                "title": title,
                "date": pub_date_raw,
                "is_synced": is_synced
            })
            
        return jsonify({"status": "success", "episodes": episodes})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/clear_history', methods=['POST'])
def clear_history_api():
    try:
        data = request.json or {}
        days = data.get('days', 'all')
        logs = clear_vault_history(days=days)
        return jsonify({"status": "success", "logs": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/doc_stats', methods=['GET'])
def get_doc_stats_api():
    try:
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"status": "success", "count": 0})
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        raw_path = os.path.expanduser(config.get("raw_material_path", "./RawMaterials"))
        vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
        count, pending_files = get_document_stats(raw_path, vault_path)
        return jsonify({"status": "success", "count": count, "pending_files": pending_files})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/upload_docs', methods=['POST'])
def upload_docs():
    try:
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"status": "error", "message": "Config not found"}), 404
            
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            
        raw_path = os.path.expanduser(config.get("raw_material_path", "./RawMaterials"))
        if not os.path.exists(raw_path):
            os.makedirs(raw_path, exist_ok=True)
            
        files = request.files.getlist('files')
        if not files:
            return jsonify({"status": "error", "message": "No files uploaded"}), 400
            
        saved_files = []
        for file in files:
            if file.filename:
                # Secure filename extraction
                from werkzeug.utils import secure_filename
                filename = secure_filename(file.filename)
                if not filename:
                    filename = file.filename.replace('/', '_').replace('\\', '_')
                file_path = os.path.join(raw_path, filename)
                file.save(file_path)
                saved_files.append(filename)
                
        return jsonify({
            "status": "success",
            "message": f"Successfully uploaded {len(saved_files)} files",
            "files": saved_files
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sync_docs', methods=['POST'])
def run_doc_sync():
    import datetime
    
    data = request.get_json(silent=True) or {}
    target_files = data.get("target_files", None)
    
    def generate():
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            
            raw_path = os.path.expanduser(config.get("raw_material_path", "./RawMaterials"))
            vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
            gemini_key = config.get("api_keys", {}).get("gemini", "")
            gemini_model = config.get("gemini_model", "gemini-1.5-flash")
            engine = config.get("document_engine", "gemini")
            ollama_model = config.get("ollama_model", "")
            nuextract_model = config.get("nuextract_model", "numind/NuExtract3-mlx-4bits")
            restructure_prompt = config.get("restructure_prompt")
            chunk_size = config.get("chunk_size", 16000)
            chunk_overlap = config.get("chunk_overlap", 1000)
            archive_processed = config.get("archive_processed_docs", False)
            auto_restructure_ollama = config.get("auto_restructure_ollama", False)
            fidelity_min_ratio = config.get("fidelity_min_ratio", 0.5)

            for item in process_documents_generator(
                raw_path, vault_path, gemini_key, gemini_model,
                target_files=target_files, engine=engine, ollama_model=ollama_model,
                nuextract_model=nuextract_model,
                prompt_template=restructure_prompt, chunk_size=chunk_size, overlap=chunk_overlap,
                archive_processed=archive_processed, auto_restructure_ollama=auto_restructure_ollama,
                fidelity_min_ratio=fidelity_min_ratio
            ):
                yield item
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            
    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/harvest/status', methods=['GET'])
def get_harvest_status():
    return jsonify({
        "status": "success",
        "has_session": harvester.is_session_active()
    })

@app.route('/api/harvest/setup', methods=['POST'])
def setup_harvest_session():
    import asyncio
    try:
        # Run in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(harvester.setup_session())
        return jsonify({"status": "success" if success else "error"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/harvest/cookies', methods=['POST'])
def import_harvest_cookies():
    data = request.json
    cookie_string = data.get("cookies")
    if not cookie_string:
        return jsonify({"status": "error", "message": "No cookies provided"})
    
    success = harvester.import_cookies(cookie_string)
    return jsonify({"status": "success" if success else "error"})

@app.route('/api/harvest/reset', methods=['POST'])
def reset_harvest_session():
    try:
        removed = harvester.reset_session()
        return jsonify({"status": "success", "removed": removed})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/harvest/editions', methods=['GET'])
def list_harvest_editions():
    import asyncio
    date = request.args.get('date') or None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        editions = loop.run_until_complete(harvester.list_editions(date=date))
        return jsonify({"status": "success", "editions": editions})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "editions": []}), 500

@app.route('/api/harvest/run', methods=['POST'])
def run_harvest():
    data = request.json or {}
    url = data.get('url')
    publication = data.get('publication') or None
    date = data.get('date') or None

    def generate():
        import asyncio
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            gen = harvester.harvest_hindu(url=url, output_dir=vault_path,
                                          publication=publication, date=date)
            while True:
                try:
                    # Iterate through the async generator
                    item = loop.run_until_complete(gen.__anext__())
                    yield item
                except StopAsyncIteration:
                    break
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            
    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/resolve_youtube', methods=['POST'])
def resolve_youtube():
    """Resolve YouTube channel URL to direct Atom RSS feed URL."""
    try:
        data = request.json or {}
        url = data.get('url', '')
        if not url:
            return jsonify({"status": "error", "message": "URL is required"}), 400
            
        from main import resolve_youtube_feed
        resolved_url = resolve_youtube_feed(url)
        return jsonify({"status": "success", "resolved_url": resolved_url})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── Schedule API ──────────────────────────────────────────────────────────────


@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    """List all scheduled jobs."""
    try:
        jobs = list_schedules()
        return jsonify({"status": "success", "jobs": jobs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/podcast', methods=['POST'])
def schedule_podcast():
    """Schedule a podcast sync job."""
    try:
        data = request.json or {}
        trigger_type = data.get('trigger_type', 'once')
        run_at = data.get('run_at')
        cron_hour = data.get('cron_hour')
        cron_minute = data.get('cron_minute')
        interval_value = data.get('interval_value')
        interval_unit = data.get('interval_unit')
        show_index = data.get('show_index', None)
        episode_index = data.get('episode_index', None)
        job_id_param = data.get('job_id')

        if trigger_type == 'once' and not run_at:
            return jsonify({"status": "error", "message": "run_at is required for 'once' schedule."}), 400

        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        shows = config.get('shows', [])

        if show_index is not None and 0 <= show_index < len(shows):
            show_name = shows[show_index].get('show_name', f'Show {show_index}')
            label = f"Podcast · {show_name}"
            if episode_index is not None:
                label += f" (Episode {episode_index})"
        else:
            label = "Podcast · All Shows"

        payload = {'show_index': show_index, 'episode_index': episode_index}
        job_id = add_schedule(
            'podcast', payload, run_at, label, CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit,
            job_id=job_id_param
        )
        return jsonify({"status": "success", "job_id": job_id, "label": label})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/docs', methods=['POST'])
def schedule_docs():
    """Schedule a document harvest job."""
    try:
        data = request.json or {}
        trigger_type = data.get('trigger_type', 'once')
        run_at = data.get('run_at')
        cron_hour = data.get('cron_hour')
        cron_minute = data.get('cron_minute')
        interval_value = data.get('interval_value')
        interval_unit = data.get('interval_unit')
        target_files = data.get('target_files', None)
        job_id_param = data.get('job_id')

        if trigger_type == 'once' and not run_at:
            return jsonify({"status": "error", "message": "run_at is required for 'once' schedule."}), 400

        label = "Documents · "
        if target_files:
            label += ', '.join(target_files[:3])
            if len(target_files) > 3:
                label += f" +{len(target_files)-3} more"
        else:
            label += "All Pending"

        payload = {'target_files': target_files}
        job_id = add_schedule(
            'docs', payload, run_at, label, CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit,
            job_id=job_id_param
        )
        return jsonify({"status": "success", "job_id": job_id, "label": label})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/web', methods=['POST'])
def schedule_web():
    """Schedule a web harvest job."""
    try:
        data = request.json or {}
        trigger_type = data.get('trigger_type', 'once')
        run_at = data.get('run_at')
        cron_hour = data.get('cron_hour')
        cron_minute = data.get('cron_minute')
        interval_value = data.get('interval_value')
        interval_unit = data.get('interval_unit')
        url = data.get('url')
        job_id_param = data.get('job_id')

        if trigger_type == 'once' and not run_at:
            return jsonify({"status": "error", "message": "run_at is required for 'once' schedule."}), 400
        if not url:
            return jsonify({"status": "error", "message": "url is required"}), 400

        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        vault_path = os.path.expanduser(config.get('obsidian_vault_path', './Vault'))

        label = f"Web · {url[:50]}{'...' if len(url) > 50 else ''}"
        payload = {'url': url, 'vault_path': vault_path}
        job_id = add_schedule(
            'web', payload, run_at, label, CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit,
            job_id=job_id_param
        )
        return jsonify({"status": "success", "job_id": job_id, "label": label})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/<job_id>/cancel', methods=['POST'])
def cancel_schedule_route(job_id):
    """Cancel a pending or running scheduled job."""
    try:
        success, message = cancel_schedule(job_id)
        status = "success" if success else "error"
        code = 200 if success else 400
        return jsonify({"status": status, "message": message}), code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/<job_id>', methods=['DELETE'])
def delete_schedule_route(job_id):
    """Delete a job from the registry."""
    try:
        success, message = delete_schedule(job_id)
        status = "success" if success else "error"
        code = 200 if success else 400
        return jsonify({"status": status, "message": message}), code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── arXiv API ──────────────────────────────────────────────────────────────

@app.route('/api/arxiv/search', methods=['GET'])
def arxiv_search():
    try:
        query = request.args.get('query', '')
        limit = request.args.get('limit', 50, type=int)
        sort_by = request.args.get('sort_by', 'relevance')
        year_from = request.args.get('year_from', type=int)
        year_to = request.args.get('year_to', type=int)

        # sources: comma-separated list; default to arXiv for backwards compat.
        raw_sources = request.args.get('sources', 'arxiv')
        sources = [s.strip() for s in raw_sources.split(',') if s.strip()]
        if not sources:
            sources = ['arxiv']

        if not query:
            return jsonify({"status": "error", "message": "Query is required"}), 400

        outcome = research_harvester.search(
            query, sources=sources, max_results=limit, sort_by=sort_by,
            year_from=year_from, year_to=year_to)
        return jsonify({
            "status": "success",
            "results": outcome["results"],
            "errors": outcome["errors"],
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/arxiv/harvest', methods=['POST'])
def arxiv_harvest():
    data = request.json or {}
    paper_id = data.get('paper_id')
    if not paper_id:
        return jsonify({"status": "error", "message": "Paper ID is required"}), 400

    # Optional metadata supplied by the front-end so non-arXiv sources can be
    # harvested directly from their open-access PDF without a re-fetch.
    pdf_url = data.get('pdf_url')
    doi = data.get('doi')
    paper_title = data.get('title')

    source, native_id = ResearchHarvester.parse_id(paper_id)

    def generate():
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)

            vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
            engine = config.get("document_engine", "gemini")

            yield json.dumps({"type": "info", "message": f"Starting harvest for paper {paper_id}..."}) + "\n"

            # 1. Download
            yield json.dumps({"type": "info", "message": "Downloading paper..."}) + "\n"

            # The LaTeX-source path only exists on arXiv. Other sources go
            # straight to their open-access PDF.
            content = None
            if engine == 'latex' and source == 'arxiv':
                yield json.dumps({"type": "info", "message": "Attempting to download and convert LaTeX source..."}) + "\n"
                source_path = arxiv_harvester.download_source(native_id)
                content, error = arxiv_harvester.convert_latex_to_md(source_path)
                if error:
                    yield json.dumps({"type": "warning", "message": f"LaTeX conversion failed: {error}. Falling back to PDF."}) + "\n"
                else:
                    yield json.dumps({"type": "info", "message": "✓ Successfully converted LaTeX source to Markdown."}) + "\n"
                    # We need to save this. We'll use doc_processor's generate_obsidian_markdown logic
                    from doc_processor import generate_obsidian_markdown, sanitize_filename, get_file_mtime_date

                    # We'll need the paper metadata for the title
                    results = arxiv_harvester.search(f"id:{native_id}")
                    if results:
                        paper = results[0]
                        title = paper['title']
                        safe_title = sanitize_filename(title)
                        date = paper['published'].replace('-', '')
                        md_filename = f"{date}_Library_{safe_title}.md"
                        output_path = os.path.join(vault_path, md_filename)

                        markdown = generate_obsidian_markdown(content, title, f"arxiv:{native_id}", date)
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(markdown)

                        yield json.dumps({"type": "success", "message": f"🎊 Complete! Saved to {md_filename}"}) + "\n"
                        return

            # Standard path: Download PDF and let doc_processor handle it
            if not content:
                if source == 'arxiv':
                    pdf_path = arxiv_harvester.download_pdf(native_id)
                else:
                    try:
                        pdf_path = research_harvester.download_pdf(
                            paper_id, pdf_url=pdf_url, doi=doi, title=paper_title)
                    except ValueError as ve:
                        yield json.dumps({"type": "error", "message": str(ve)}) + "\n"
                        return
                filename = os.path.basename(pdf_path)
                
                # 2. Process using doc_processor
                raw_path = os.path.expanduser(config.get("raw_material_path", "./RawMaterials"))
                gemini_key = config.get("api_keys", {}).get("gemini", "")
                gemini_model = config.get("gemini_model", "gemini-1.5-flash")
                ollama_model = config.get("ollama_model", "")
                nuextract_model = config.get("nuextract_model", "numind/NuExtract3-mlx-4bits")
                restructure_prompt = config.get("restructure_prompt")
                chunk_size = config.get("chunk_size", 16000)
                chunk_overlap = config.get("chunk_overlap", 1000)
                archive_processed = config.get("archive_processed_docs", False)
                auto_restructure_ollama = config.get("auto_restructure_ollama", False)
                fidelity_min_ratio = config.get("fidelity_min_ratio", 0.5)

                for item in process_documents_generator(
                    raw_path, vault_path, gemini_key, gemini_model,
                    target_files=[filename], engine=engine, ollama_model=ollama_model,
                    nuextract_model=nuextract_model,
                    prompt_template=restructure_prompt, chunk_size=chunk_size, overlap=chunk_overlap,
                    archive_processed=archive_processed, auto_restructure_ollama=auto_restructure_ollama,
                    fidelity_min_ratio=fidelity_min_ratio
                ):
                    yield item
                
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            
    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')


@app.route('/api/youtube/channels', methods=['GET'])
def get_youtube_channels():
    if not os.path.exists(CONFIG_PATH):
        return jsonify({"channels": []})
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    return jsonify({"channels": config.get("youtube_channels", [])})

@app.route('/api/youtube/channels', methods=['POST'])
def save_youtube_channels():
    data = request.json or {}
    channels = data.get("channels", [])
    if not os.path.exists(CONFIG_PATH):
        config = {}
    else:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    config["youtube_channels"] = channels
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)
    return jsonify({"status": "success", "message": "YouTube channels saved successfully"})

# --- Telegram Channels API ---
@app.route('/api/telegram/channels', methods=['GET', 'POST'])
def handle_telegram_channels():
    if request.method == 'GET':
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"channels": []})
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        tg_config = config.get("telegram", {})
        return jsonify({"channels": tg_config.get("channels", [])})
    else:
        data = request.json or {}
        channels = data.get("channels", [])
        if not os.path.exists(CONFIG_PATH):
            config = {}
        else:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                
        if "telegram" not in config:
            config["telegram"] = {}
        config["telegram"]["channels"] = channels
        
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        return jsonify({"status": "success", "message": "Telegram channels saved successfully"})

@app.route('/api/telegram/harvest', methods=['POST'])
def harvest_telegram():
    data = request.json or {}
    channel_index = data.get('channel_index') # None means Sync All
    
    if not os.path.exists(CONFIG_PATH):
        return jsonify({"status": "error", "message": "Config not found"}), 404
        
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        
    tg_config = config.get('telegram', {})
    api_id = tg_config.get('api_id')
    api_hash = tg_config.get('api_hash')
    phone = tg_config.get('phone')
    channels = tg_config.get('channels', [])
    limit = tg_config.get('limit', 100)
    
    if not api_id or not api_hash or not phone or not channels:
        return jsonify({"status": "error", "message": "Telegram configuration is incomplete."}), 400
        
    target_channels = channels if channel_index is None else [channels[channel_index]]
    
    # We will trigger the background job via scheduler for a manual run (like we do for youtube)
    from scheduler import add_schedule
    label = "Telegram Sync All" if channel_index is None else f"Telegram Sync: {channels[channel_index].get('channel_name')}"
    
    try:
        job_id = add_schedule(
            engine='telegram',
            payload={"channel_index": channel_index},
            label=label,
            config_path=CONFIG_PATH,
            trigger_type='once',
            run_at_iso=(__import__('datetime').datetime.utcnow() + __import__('datetime').timedelta(seconds=5)).isoformat() + 'Z'
        )
        return jsonify({"status": "success", "message": "Telegram harvest job started", "job_id": job_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/youtube/episodes', methods=['GET'])
def get_youtube_episodes():
    import feedparser
    import time
    from main import format_date, sanitize_filename
    
    try:
        channel_index = int(request.args.get('channel_index', -1))
        
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"status": "error", "message": "Config not found"}), 404
            
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            
        channels = config.get("youtube_channels", [])
        if channel_index < 0 or channel_index >= len(channels):
            return jsonify({"status": "error", "message": "Invalid channel index"}), 400
            
        channel_info = channels[channel_index]
        rss_url = channel_info.get("rss_url")
        if not rss_url:
            return jsonify({"status": "error", "message": "No RSS URL found"}), 400
            
        vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
        channel_name = channel_info.get("channel_name", "UnknownCreator")
        
        # Load Cache
        cache_path = os.path.join(os.path.dirname(__file__), 'feed_cache.json')
        feed_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as cf:
                    feed_cache = json.load(cf)
            except:
                pass
                
        cached_data = feed_cache.get(rss_url)
        if cached_data and time.time() - cached_data['timestamp'] < 3600:
            feed = feedparser.FeedParserDict(cached_data['data'])
        else:
            feed = feedparser.parse(rss_url)
            
        if not feed.entries:
            return jsonify({"status": "error", "message": "No videos found in feed"}), 404
            
        episodes_list = []
        for i, entry in enumerate(feed.entries):
            title = entry.get("title", "Untitled Video")
            pub_date_raw = entry.get("published", "")
            pub_parsed = entry.get("published_parsed")
            if isinstance(pub_parsed, time.struct_time):
                formatted_date = time.strftime('%Y%m%d', pub_parsed)
            else:
                formatted_date = format_date(pub_date_raw)
                
            clean_title = sanitize_filename(title)
            filename = f"{formatted_date}_Transcripts_{clean_title}.md"
            
            org_mode = config.get("folder_organisation", "per_channel")
            if org_mode == "flat":
                target_check_dir = vault_path
            else:
                clean_channel = sanitize_filename(channel_name)
                target_check_dir = os.path.join(vault_path, clean_channel)
                
            filepath = os.path.join(target_check_dir, filename)
            is_synced = os.path.exists(filepath)
            
            episodes_list.append({
                "index": i,
                "title": title,
                "published": pub_date_raw,
                "is_synced": is_synced
            })
            
        return jsonify({"status": "success", "episodes": episodes_list})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/youtube/sync', methods=['POST'])
def run_youtube_sync():
    data = request.json or {}
    channel_index = data.get('channel_index')
    video_index = data.get('video_index')
    
    from main import execute_youtube_sync_generator
    def generate():
        try:
            for item in execute_youtube_sync_generator(channel_index=channel_index, video_index=video_index):
                yield item
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Server stream error: {e}"}) + "\n"
            
    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/schedule/youtube', methods=['POST'])
def schedule_youtube():
    data = request.json or {}
    channel_index = data.get('channel_index')
    run_at = data.get('run_at')
    
    # Advanced scheduling fields
    trigger_type = data.get('trigger_type', 'once')
    cron_hour = data.get('cron_hour')
    cron_minute = data.get('cron_minute')
    interval_value = data.get('interval_value')
    interval_unit = data.get('interval_unit')
    
    if trigger_type == 'once' and not run_at:
        return jsonify({"status": "error", "message": "run_at time is required for one-time schedules."}), 400

    try:
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"status": "error", "message": "Config not found"}), 404
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            
        channels = config.get("youtube_channels", [])
        if channel_index is None or channel_index < 0 or channel_index >= len(channels):
            return jsonify({"status": "error", "message": "Invalid channel index"}), 400
            
        channel = channels[channel_index]
        label = f"YouTube: {channel.get('channel_name', 'Unknown')}"
        
        payload = {
            "channel_index": channel_index,
            "video_index": None
        }
        
        job_id = add_schedule(
            engine='youtube',
            payload=payload,
            run_at_iso=run_at,
            label=label,
            config_path=CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit
        )
        return jsonify({"status": "success", "message": "YouTube schedule added.", "job_id": job_id})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/api/schedule/telegram', methods=['POST'])
def schedule_telegram():
    data = request.json or {}
    run_at = data.get('run_at')
    
    # Advanced scheduling fields
    trigger_type = data.get('trigger_type', 'once')
    cron_hour = data.get('cron_hour')
    cron_minute = data.get('cron_minute')
    interval_value = data.get('interval_value')
    interval_unit = data.get('interval_unit')
    
    if trigger_type == 'once' and not run_at:
        return jsonify({"status": "error", "message": "run_at time is required for one-time schedules."}), 400

    try:
        label = "Telegram Harvest"
        payload = {}
        
        job_id = add_schedule(
            engine='telegram',
            payload=payload,
            run_at_iso=run_at,
            label=label,
            config_path=CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit
        )
        return jsonify({"status": "success", "message": "Telegram schedule added.", "job_id": job_id})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@app.route('/api/harvest/market', methods=['POST'])
def run_market_harvest():
    data = request.json or {}
    index = data.get('index')
    
    try:
        import sys
        import importlib
        import market_harvester
        importlib.reload(market_harvester)
        from market_harvester import MarketHarvester
        harvester = MarketHarvester()
        
        if index is not None:
            success, message = harvester.harvest_single(int(index))
        else:
            success, message = harvester.harvest_all()
            
        return jsonify({
            "status": "success" if success else "error",
            "message": message
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/schedule/market_data', methods=['POST'])
def schedule_market_data():
    data = request.json or {}
    run_at = data.get('run_at')
    
    # Advanced scheduling fields
    trigger_type = data.get('trigger_type', 'once')
    cron_hour = data.get('cron_hour')
    cron_minute = data.get('cron_minute')
    interval_value = data.get('interval_value')
    interval_unit = data.get('interval_unit')
    index = data.get('index')
    
    if trigger_type == 'once' and not run_at:
        return jsonify({"status": "error", "message": "run_at time is required for one-time schedules."}), 400

    try:
        label = "Market Data Harvest"
        payload = {"index": index} if index is not None else {}
        
        job_id = add_schedule(
            engine='market_data',
            payload=payload,
            run_at_iso=run_at,
            label=label,
            config_path=CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit
        )
        return jsonify({"status": "success", "message": "Market Data schedule added.", "job_id": job_id})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@app.route('/api/harvest/central_bank', methods=['POST'])
def run_central_bank_harvest_api():
    try:
        import importlib
        import central_bank_harvester
        importlib.reload(central_bank_harvester)
        from central_bank_harvester import run_central_bank_harvest
        
        success, message = run_central_bank_harvest()
        return jsonify({
            "status": "success" if success else "error",
            "message": message
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule/central_bank', methods=['POST'])
def schedule_central_bank_data():
    data = request.json or {}
    run_at = data.get('run_at')
    
    trigger_type = data.get('trigger_type', 'once')
    cron_hour = data.get('cron_hour')
    cron_minute = data.get('cron_minute')
    interval_value = data.get('interval_value')
    interval_unit = data.get('interval_unit')
    
    if trigger_type == 'once' and not run_at:
        return jsonify({"status": "error", "message": "run_at time is required for one-time schedules."}), 400

    try:
        label = "Central Bank & Macro Digest Harvest"
        job_id = add_schedule(
            engine='central_bank',
            payload={},
            run_at_iso=run_at,
            label=label,
            config_path=CONFIG_PATH,
            trigger_type=trigger_type,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            interval_value=interval_value,
            interval_unit=interval_unit
        )
        return jsonify({"status": "success", "message": "Central Bank schedule added.", "job_id": job_id})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

# --- Audio Overview Podcast API Routes ---

@app.route('/api/audio-overview/voices', methods=['GET'])
def get_audio_voices():
    return jsonify({"status": "success", "voices": AVAILABLE_VOICES})

@app.route('/api/audio-overview/input-files', methods=['GET'])
def get_audio_input_files():
    try:
        folder = request.args.get('folder')
        files = audio_engine.scan_input_files(folder)
        return jsonify({
            "status": "success",
            "folder": folder or audio_engine.input_folder,
            "count": len(files),
            "files": files
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/audio-overview/generate', methods=['POST'])
def generate_audio_overview():
    data = request.json or {}
    file_paths = data.get('file_paths', [])
    raw_text = data.get('raw_text', '')
    title = data.get('title', 'Daily News Audio Overview')
    style = data.get('style', 'deep_dive')
    host1_voice = data.get('host1_voice', 'en-US-AndrewNeural')
    host2_voice = data.get('host2_voice', 'en-US-AvaNeural')
    target_duration = data.get('target_duration', '18-20')
    topic_focus = data.get('topic_focus', '')

    def generate_stream():
        def send_event(event_type, msg_data):
            payload = {"type": event_type, "data": msg_data}
            return f"data: {json.dumps(payload)}\n\n"

        try:
            yield send_event("status", {"message": "Reading input articles...", "progress": 10})

            articles_content = ""
            if file_paths:
                articles_content = audio_engine.read_article_contents(file_paths)

            if raw_text:
                articles_content += f"\n\n--- MANUAL TEXT ---\n{raw_text}\n"

            if not articles_content.strip():
                yield send_event("error", {"message": "No article content provided to process."})
                return

            yield send_event("status", {"message": f"Drafting {target_duration} min NotebookLM 2-host dialogue script via Gemini...", "progress": 15})

            current_progress = [15]
            event_queue = []

            def script_log(msg, progress=None):
                if progress is not None:
                    current_progress[0] = progress
                event_queue.append(send_event("status", {"message": msg, "progress": current_progress[0]}))

            script_turns = audio_engine.generate_notebooklm_script(
                articles_text=articles_content,
                overview_style=style,
                target_duration=target_duration,
                custom_topic=topic_focus,
                log_callback=script_log
            )

            for evt in event_queue:
                yield evt
            event_queue.clear()

            yield send_event("status", {"message": f"Generated {len(script_turns)} dialogue turns. Synthesizing multi-speaker speech with neural TTS...", "progress": 70})

            def synth_log(msg):
                pass

            synthesis_res = audio_engine.synthesize_audio(
                turns=script_turns,
                host1_voice=host1_voice,
                host2_voice=host2_voice,
                title=title,
                log_callback=synth_log
            )

            yield send_event("status", {"message": "Exporting podcast note and transcript to Obsidian Vault...", "progress": 85})

            obsidian_note_path = audio_engine.export_to_obsidian_vault(
                title=title,
                synthesis_meta=synthesis_res,
                script_turns=script_turns,
                timestamped_turns=synthesis_res["timestamped_turns"]
            )

            yield send_event("complete", {
                "message": "Audio Overview podcast successfully created!",
                "progress": 100,
                "title": title,
                "duration": synthesis_res["duration"],
                "audio_filename": synthesis_res["filename"],
                "audio_url": f"/api/audio-overview/audio/{synthesis_res['filename']}",
                "obsidian_note": os.path.basename(obsidian_note_path),
                "timestamped_turns": synthesis_res["timestamped_turns"]
            })

        except Exception as e:
            yield send_event("error", {"message": f"Audio overview generation failed: {str(e)}"})

    return Response(stream_with_context(generate_stream()), mimetype='text/event-stream')

@app.route('/api/audio-overview/history', methods=['GET'])
def get_audio_history():
    try:
        podcasts = audio_engine.get_podcast_history()
        return jsonify({"status": "success", "podcasts": podcasts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/audio-overview/audio/<path:filename>', methods=['GET'])
def serve_audio_file(filename):
    audio_dir = os.path.abspath(audio_engine.output_folder)
    return send_from_directory(audio_dir, filename)

@app.route('/<path:path>')
def static_proxy(path):

    return send_from_directory('public', path)

if __name__ == '__main__':
    print("Starting Podcast-to-Obsidian Web Management Interface on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
