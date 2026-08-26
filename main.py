import json
import os
import re
import datetime
import requests
import feedparser
import time
import tempfile
import sys
import threading
from database import db
from doc_processor import _wait_for_gemini_rate_limit, get_gemini_stats

# Global event for canceling the sync process
cancel_event = threading.Event()

# Ensure that local packages like imageio-ffmpeg can be found by subprocesses
# Ensure that local packages and common Mac binary paths are found by subprocesses
common_paths = [
    os.path.dirname(sys.executable),
    "/usr/local/bin",
    "/opt/homebrew/bin"
]
for path in common_paths:
    if path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + path

REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def sanitize_filename(name):
    """Remove special characters and replace spaces with underscores to create a safe file name."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "_")
    return name

def resolve_youtube_feed(url):
    """If the URL is a YouTube channel URL, extract/resolve the channel ID to return the RSS feed URL."""
    if not url:
        return url
    
    # Check if it's already a YouTube feed XML url
    if "youtube.com/feeds/videos.xml" in url:
        return url
        
    if "youtube.com" in url or "youtu.be" in url or "@" in url:
        try:
            # Normalize url if it doesn't have http schema
            target_url = url
            if not target_url.startswith("http://") and not target_url.startswith("https://"):
                target_url = "https://" + target_url
            
            resp = requests.get(target_url, headers=REQ_HEADERS, timeout=10)
            if resp.status_code == 200:
                # 1. Find the RSS link in the page source
                match = re.search(r'href="https://www\.youtube\.com/feeds/videos\.xml\?channel_id=([a-zA-Z0-9_-]+)"', resp.text)
                if match:
                    channel_id = match.group(1)
                    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                
                # 2. Alternatively look for channel_id inside meta tags
                match_meta = re.search(r'meta itemprop="channelId" content="([a-zA-Z0-9_-]+)"', resp.text)
                if match_meta:
                    channel_id = match_meta.group(1)
                    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    
                # 3. Alternatively look for "channelId":"UC..."
                match_json = re.search(r'"channelId"\s*:\s*"([a-zA-Z0-9_-]+)"', resp.text)
                if match_json:
                    channel_id = match_json.group(1)
                    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        except Exception as e:
            print(f"Failed to resolve YouTube channel ID from {url}: {e}")
            
    return url

def format_date(date_str):
    """Attempt to parse standard pubDate formats to YYYYMMDD format."""
    if not date_str:
        return datetime.datetime.now().strftime('%Y%m%d')
        
    try:
        # Standard RSS pubDate is RFC 822 e.g., "Wed, 02 Oct 2002 13:00:00 GMT"
        # feedparser._parse_date is robust for most RSS/Atom date strings
        dt = feedparser._parse_date(date_str)
        if dt:
            return time.strftime('%Y%m%d', dt)
    except Exception:
        pass
    
    # Try basic ISO format if feedparser fails
    try:
        # Handle cases like "2024-03-21T..."
        clean_date = date_str.split('T')[0]
        if '-' in clean_date:
            parts = clean_date.split('-')
            if len(parts) >= 3:
                return f"{parts[0]}{parts[1].zfill(2)}{parts[2].zfill(2)}"
    except Exception:
        pass

    # Fallback to current date if all else fails
    return datetime.datetime.now().strftime('%Y%m%d')

def download_audio_with_retries(audio_url, temp_path, log_callback, max_retries=3):
    """Downloads audio file robustly with retries to prevent SSL EOF errors."""
    for attempt in range(max_retries):
        try:
            with open(temp_path, 'wb') as f:
                # Use a longer timeout and stream
                resp = requests.get(audio_url, stream=True, timeout=(30, 120), headers=REQ_HEADERS)
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                last_pct = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            if pct >= last_pct + 10:
                                log_callback(f"Downloading audio... {pct}%", progress=pct)
                                last_pct = pct
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                log_callback(f"Download interrupted ({e}), retrying ({attempt+1}/{max_retries})...")
                time.sleep(3)
            else:
                raise Exception(f"Failed to download audio after {max_retries} attempts: {e}")

def fetch_native_transcript(entry):
    """Attempts to find and download a transcript natively provided by the RSS feed."""
    links = entry.get('links', [])
    for link in links:
        # Look for explicit podcast-transcript rel or text types
        if link.get('rel') == 'podcast-transcript' or 'transcript' in link.get('type', '').lower():
            url = link.get('href')
            if url:
                try:
                    resp = requests.get(url, timeout=10, headers=REQ_HEADERS)
                    if resp.status_code == 200:
                        return resp.text
                except Exception as e:
                    print(f"Failed to fetch native transcript from {url}: {e}")
                    
    # Feedparser sometimes stores podcast:transcript in a specific key
    if 'podcast_transcript' in entry:
        url = entry.podcast_transcript.get('url')
        if url:
             try:
                 resp = requests.get(url, timeout=10, headers=REQ_HEADERS)
                 if resp.status_code == 200:
                     return resp.text
             except Exception as e:
                 print(f"Failed to fetch native transcript from {url}: {e}")
                 
    return None

def transcribe_with_assemblyai(audio_url, api_key):
    """Uses AssemblyAI to transcribe the audio URL as a fallback."""
    if not api_key or api_key == "YOUR_ASSEMBLYAI_KEY_HERE":
        print("AssemblyAI API key not configured. Skipping STT.")
        return None
        
    print(f"Sending transcription request to AssemblyAI for {audio_url}...")
    headers = {
        "authorization": api_key,
        "content-type": "application/json"
    }
    
    # 1. Submit for transcription
    submit_url = "https://api.assemblyai.com/v2/transcript"
    data = {"audio_url": audio_url}
    
    try:
        response = requests.post(submit_url, json=data, headers=headers, timeout=30)
        if response.status_code != 200:
             print(f"AssemblyAI Submit Error {response.status_code}: {response.text}")
             return None

        transcript_id = response.json()['id']

        # 2. Poll for completion
        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        max_polls = 80  # ~20 minutes at 15s intervals
        for _ in range(max_polls):
            poll_response = requests.get(polling_url, headers=headers, timeout=30)
            res_data = poll_response.json()
            status = res_data['status']
            if status == 'completed':
                text = res_data.get('text', '')
                return text.strip() if text and text.strip() else None
            elif status == 'error':
                print("AssemblyAI Transcription Error:", res_data.get('error'))
                return None

            print(f"Waiting for transcription to complete. Status: {status}...")
            time.sleep(15)
        print("AssemblyAI polling timed out after max attempts.")
        return None
    except Exception as e:
        print(f"AssemblyAI API request failed: {e}")
        return None

def transcribe_with_whisper(local_audio_path, model_size, log_callback):
    """Uses native MLX or HuggingFace Transformers for free transcription."""
    if not local_audio_path or not os.path.exists(local_audio_path):
        return None
        
    try:
        import platform
        log_callback(f"Preparing Whisper Model '{model_size}'...", progress="indeterminate")
        # Ensure model size has a default
        if not model_size: model_size = "base"
        
        text = ""
        use_mlx = False
        
        # 1. Attempt Apple Silicon Native MLX Optimization
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                import mlx_whisper
                use_mlx = True
            except ImportError:
                log_callback("Apple Silicon detected, but 'mlx-whisper' not found. Falling back to Transformers...")
        
        if use_mlx:
            mlx_repo = f"mlx-community/whisper-{model_size}-mlx"
            log_callback(f"MLX Engine Active. Loading '{mlx_repo}' natively on GPU...", progress="indeterminate")
            log_callback(f"Model loaded. Transcribing audio with Apple MLX (blazing fast)...", progress="indeterminate")
            
            result = mlx_whisper.transcribe(local_audio_path, path_or_hf_repo=mlx_repo)
            text = result.get("text", "")
            
        else:
            # 2. Fallback to HuggingFace Transformers
            try:
                from transformers import pipeline
                import torch
            except ImportError:
                log_callback("Error: 'transformers' or 'torch' package is not installed.")
                if os.path.exists(temp_path): os.remove(temp_path)
                return None
                
            model_id = f"openai/whisper-{model_size}"
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            
            log_callback(f"Transformers Fallback. Loading '{model_id}' onto device {device.upper()}...", progress="indeterminate")
            
            pipe = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                device=device,
                chunk_length_s=30,
            )
            
            log_callback(f"Model loaded. Transcribing audio (this will take a while, please wait)...", progress="indeterminate")
            result = pipe(local_audio_path)
            text = result.get("text", "")
        
        log_callback("Whisper transcription complete.")
        
        return text.strip() if text and text.strip() else None
        
    except Exception as e:
        log_callback(f"Local Whisper Transcription Failed: {e}")
        return None

def transcribe_with_gemini(local_audio_path, api_key, model_id, log_callback):
    """Uses Google Gemini 1.5/2.0 to transcribe audio."""
    if not local_audio_path or not os.path.exists(local_audio_path):
        return None
        
    if not api_key:
        log_callback("Error: Gemini API key not configured.", "error")
        return None
        
    try:
        from google import genai
    except ImportError:
        log_callback("Error: 'google-genai' package is not installed.", "error")
        return None

    try:
        log_callback(f"Uploading to Gemini ({model_id})...", progress="indeterminate")
        
        # Initialize Gemini Client
        client = genai.Client(api_key=api_key)
        
        # Upload file to Gemini with retries
        myfile = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                myfile = client.files.upload(file=local_audio_path)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_callback(f"Upload interrupted ({e}), retrying ({attempt+1}/{max_retries})...")
                    time.sleep(5)
                else:
                    raise Exception(f"Failed to upload audio to Gemini: {e}")
        
        log_callback("Gemini is listening to the audio and generating transcript...", progress="indeterminate")
        
        # 4. Generate Content (Transcript) with retries
        prompt = "Provide a clean, word-for-word transcript of this audio file. Format with clear paragraphs and indicate speaker changes if possible. Do not add any conversational filler or meta-commentary."
        
        response = None
        for attempt in range(max_retries):
            try:
                _wait_for_gemini_rate_limit()
                response = client.models.generate_content(
                    model=model_id,
                    contents=[prompt, myfile]
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_callback(f"Generation interrupted ({e}), retrying ({attempt+1}/{max_retries})...")
                    time.sleep(5)
                else:
                    raise Exception(f"Failed to generate transcript via Gemini API: {e}")
        
        transcript_text = response.text if response and response.text else ""
        
        # Cleanup remote file (optional but good practice)
        try:
            if myfile:
                client.files.delete(name=myfile.name)
        except:
            pass
            
        if transcript_text and transcript_text.strip():
            log_callback("Gemini transcription successful.", progress=100)
            return transcript_text.strip()
        else:
            log_callback("Gemini processing finished but returned no text content.", "warn")
            return None

    except Exception as e:
        log_callback(f"Gemini Transcription Failed: {e}", "error")
        return None

def execute_sync_generator(show_index=None, episode_index=None):
    import queue
    import threading
    q = queue.Queue()
    
    # Reset cancellation state at the start of a flow
    cancel_event.clear()

    def worker():
        import platform
        import subprocess
        caffeinate_proc = None
        if platform.system() == "Darwin":
            try:
                # Keep system awake while processing
                caffeinate_proc = subprocess.Popen(['caffeinate', '-d', '-i'])
            except Exception:
                pass

        def log(msg, p_type="info", progress=None):
            # Prepend timestamp to each log message
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            msg_with_ts = f"[{ts}] {msg}"
            q.put(json.dumps({"message": msg_with_ts, "type": p_type, "progress": progress, "gemini_stats": get_gemini_stats()}) + "\n")
            print(msg_with_ts)
            
        # Support overriding config location via environment variables for Docker deployments
        config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.json'))
        
        log("Synchronization engine engaged. Initializing pipeline...")

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            log(f"Configuration file not found at {config_path}. Please create one.", "error")
            q.put(None)
            return

        vault_path = config.get("obsidian_vault_path", "./Vault")
        vault_path = os.path.expanduser(vault_path)
        
        if not os.path.exists(vault_path):
            log(f"Creating vault directory mapping at: {vault_path}")
            os.makedirs(vault_path, exist_ok=True)
            
        engine = config.get("transcription_engine", "none").lower()
        whisper_model = config.get("whisper_model", "base")
        gemini_model = config.get("gemini_model", "gemini-1.5-flash")
        assembly_key = config.get("api_keys", {}).get("assemblyai", "")
        gemini_key = config.get("api_keys", {}).get("gemini", "")
        sync_limit = config.get("sync_limit", 1)

        shows_to_process = config.get("shows", [])
        if show_index is not None and isinstance(show_index, int) and 0 <= show_index < len(shows_to_process):
            shows_to_process = [shows_to_process[show_index]]

        try:
            for show in shows_to_process:
                if cancel_event.is_set():
                    log("Sync cancelled by user.", "warning")
                    break
                
                channel = show.get("channel_name", "UnknownChannel")
                show_name = show.get("show_name", "UnknownShow")
                rss_url = show.get("rss_url", "")
                
                if not rss_url:
                    continue
                    
                log(f"\n--- Checking feed: {channel} | {show_name} ---")
                feed = feedparser.parse(rss_url)
                
                if not feed.entries:
                    log(f"No episodes found or invalid RSS feed for {show_name}.")
                    continue
                    
                if episode_index is not None and isinstance(episode_index, int) and 0 <= episode_index < len(feed.entries):
                    entries_to_process = [feed.entries[episode_index]]
                else:
                    entries_to_process = feed.entries if sync_limit == "all" else feed.entries[:int(sync_limit)]
                
                for entry in entries_to_process:
                    if cancel_event.is_set():
                        log("Sync cancelled by user.", "warning")
                        break
                    
                    title = entry.get("title", "Untitled Episode")
                    
                    # Prioritize the pre-parsed date from feedparser if available
                    pub_date_raw = entry.get("published", "")
                    pub_parsed = entry.get("published_parsed")
                    if isinstance(pub_parsed, (time.struct_time, tuple)):
                        formatted_date = time.strftime('%Y%m%d', pub_parsed)
                    elif isinstance(pub_parsed, list):
                        formatted_date = time.strftime('%Y%m%d', tuple(pub_parsed))
                    else:
                        formatted_date = format_date(pub_date_raw)
                    
                    guid = entry.get("id", entry.get("link", ""))
                    link = entry.get("link", "")
                    
                    audio_url = ""
                    for lnk in entry.get("links", []):
                        if 'audio' in lnk.get("type", ""):
                             audio_url = lnk.get("href", "")
                             break
                             
                    clean_channel = sanitize_filename(channel)
                    clean_show = sanitize_filename(show_name)
                    clean_title = sanitize_filename(title)
                    
                    filename = f"{formatted_date}_{clean_channel}_{clean_show}_{clean_title}.md"
                    
                    # Logic for folder organisation
                    org_mode = config.get("folder_organisation", "per_channel")
                    if org_mode == "flat":
                        target_sync_dir = vault_path
                    else:
                        target_sync_dir = os.path.join(vault_path, clean_channel)
                        os.makedirs(target_sync_dir, exist_ok=True)
                        
                    filepath = os.path.join(target_sync_dir, filename)
                    
                    if os.path.exists(filepath):
                        log(f"✓ Already grabbed: {filename}. Skipping.")
                        continue
                        
                    log(f"New instance found: {title}")
                    
                    # Tier 1: Native Extraction
                    transcript_text = None
                    note_type = ""
                    
                    transcript_text = fetch_native_transcript(entry)
                    if transcript_text:
                        note_type = "Native Transcript"
                    
                    local_audio_path = None
                    
                    def get_local_audio():
                        nonlocal local_audio_path
                        if local_audio_path is None and audio_url:
                            import tempfile
                            fd, local_audio_path = tempfile.mkstemp(suffix=".mp3")
                            os.close(fd)
                            log(f"Downloading {audio_url} to local cache...", progress=0)
                            download_audio_with_retries(audio_url, local_audio_path, log)
                        return local_audio_path
                    
                    try:
                        # Tier 2: User-Selected STT Engine
                        if not transcript_text and audio_url and engine != 'none':
                            if engine == 'assemblyai':
                                log("Native transcript not found. Trying primary engine: AssemblyAI...")
                                transcript_text = transcribe_with_assemblyai(audio_url, assembly_key)
                                if transcript_text: note_type = "AssemblyAI (Primary Engine)"
                            elif engine == 'whisper':
                                log("Native transcript not found. Trying primary engine: Local Whisper...")
                                try:
                                    ap = get_local_audio()
                                    transcript_text = transcribe_with_whisper(ap, whisper_model, log)
                                except Exception as e:
                                    log(f"Failed to prepare local audio: {e}", "error")
                                if transcript_text: note_type = f"Local Whisper ({whisper_model}) (Primary Engine)"
                            elif engine == 'gemini':
                                log(f"Native transcript not found. Trying primary engine: Google Gemini ({gemini_model})...")
                                try:
                                    ap = get_local_audio()
                                    transcript_text = transcribe_with_gemini(ap, gemini_key, gemini_model, log)
                                except Exception as e:
                                    log(f"Failed to prepare local audio: {e}", "error")
                                if transcript_text: note_type = f"Gemini ({gemini_model}) (Primary Engine)"
                        
                        # Tier 3: AssemblyAI Cloud Fallback (if not already tried)
                        if not transcript_text and audio_url and engine != 'assemblyai' and assembly_key:
                            log("Cloud primary failed/skipped. Attempting AssemblyAI fallback...")
                            transcript_text = transcribe_with_assemblyai(audio_url, assembly_key)
                            if transcript_text: note_type = "AssemblyAI (Secondary Cloud Fallback)"
                        
                        # Tier 4: Local Whisper On-Device Fallback (if not already tried)
                        if not transcript_text and audio_url and engine != 'whisper':
                            log("All cloud options failed/skipped. Attempting Local Whisper fallback...")
                            try:
                                ap = get_local_audio()
                                transcript_text = transcribe_with_whisper(ap, whisper_model, log)
                            except Exception as e:
                                log(f"Failed to prepare local audio for fallback: {e}", "error")
                            if transcript_text: note_type = f"Local Whisper ({whisper_model}) (Tertiary Local Fallback)"
                            
                        # Tier 5: Show Notes (Final Resort)
                        if not transcript_text:
                            log("No transcription available from any AI tier. Saving show notes instead.")
                            transcript_text = entry.get("description", "No transcript or description available.")
                            note_type = "Episode Show Notes (Fallback)"
                            
                        markdown_content = f"""---
title: "{title}"
channel: "{channel}"
show: "{show_name}"
date: {formatted_date}
tags: [podcast, transcript]
---

# {title}

**Channel:** {channel}
**Show:** {show_name}
**Published:** {pub_date_raw}
**Source Type:** {note_type}
**Audio Link:** {audio_url}

---

{transcript_text}
"""
                        try:
                            with open(filepath, 'w', encoding='utf-8') as mf:
                                mf.write(markdown_content)
                            
                            # Record in database
                            db.add_record(guid, {
                                "rss_url": rss_url,
                                "link": link,
                                "title": title,
                                "file_path": os.path.relpath(filepath, start=vault_path),
                                "sync_date": datetime.datetime.now().isoformat()
                            })
                            
                            log(f"Successfully saved as: {filename}", progress=100)
                        except Exception as e:
                            log(f"Failed to write file {filename}: {e}", "error")
                    finally:
                        if local_audio_path and os.path.exists(local_audio_path):
                            os.remove(local_audio_path)
                            log("Local audio cache cleaned up.")
        except Exception as e:
            log(f"Fatal execution error: {e}", "error")
        finally:
            log("Sync complete.", progress=100)
            q.put(None)
            if caffeinate_proc:
                try:
                    caffeinate_proc.terminate()
                except Exception:
                    pass

    t = threading.Thread(target=worker)
    t.start()
    
    while True:
        import queue
        try:
            item = q.get(timeout=15)
            if item is None:
                break
            yield item
        except queue.Empty:
            # Prevent TCP connection drops during long ML inference by sending a heartbeat
            yield json.dumps({"type": "heartbeat", "message": None, "progress": "indeterminate"}) + "\n"

def execute_sync(show_index=None, episode_index=None):
    logs = []
    for item_str in execute_sync_generator(show_index, episode_index):
        item = json.loads(item_str)
        logs.append(item["message"])
    return logs

def execute_youtube_sync_generator(channel_index=None, video_index=None):
    import queue
    import threading
    q = queue.Queue()
    
    cancel_event.clear()

    def worker():
        import platform
        import subprocess
        caffeinate_proc = None
        if platform.system() == "Darwin":
            try:
                caffeinate_proc = subprocess.Popen(['caffeinate', '-d', '-i'])
            except Exception:
                pass

        def log(msg, p_type="info", progress=None):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            msg_with_ts = f"[{ts}] {msg}"
            q.put(json.dumps({"message": msg_with_ts, "type": p_type, "progress": progress, "gemini_stats": get_gemini_stats()}) + "\\n")
            print(msg_with_ts)
            
        config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.json'))
        
        log("YouTube Harvesting engine engaged. Initializing pipeline...")

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            log(f"Configuration file not found at {config_path}. Please create one.", "error")
            q.put(None)
            return

        vault_path = config.get("obsidian_vault_path", "./Vault")
        vault_path = os.path.expanduser(vault_path)
        
        if not os.path.exists(vault_path):
            log(f"Creating vault directory mapping at: {vault_path}")
            os.makedirs(vault_path, exist_ok=True)
            
        sync_limit = config.get("sync_limit", 1)

        channels_to_process = config.get("youtube_channels", [])
        if channel_index is not None and isinstance(channel_index, int) and 0 <= channel_index < len(channels_to_process):
            channels_to_process = [channels_to_process[channel_index]]

        try:
            for channel_info in channels_to_process:
                if cancel_event.is_set():
                    log("Sync cancelled by user.", "warning")
                    break
                
                channel_name = channel_info.get("channel_name", "UnknownCreator")
                channel_url = channel_info.get("rss_url", "")
                
                if not channel_url:
                    continue
                    
                log(f"\\n--- Checking YouTube feed: {channel_name} ---")
                feed = feedparser.parse(channel_url)
                
                if not feed.entries:
                    log(f"No videos found or invalid RSS feed for {channel_name}.")
                    continue
                    
                if video_index is not None and isinstance(video_index, int) and 0 <= video_index < len(feed.entries):
                    entries_to_process = [feed.entries[video_index]]
                else:
                    entries_to_process = feed.entries if sync_limit == "all" else feed.entries[:int(sync_limit)]
                
                total_entries = len(entries_to_process)
                processed_entries = 0
                
                for entry in entries_to_process:
                    if cancel_event.is_set():
                        log("Sync cancelled by user.", "warning")
                        break
                    
                    processed_entries += 1
                    current_progress = int((processed_entries / total_entries) * 100)
                    
                    title = entry.get("title", "Untitled Video")
                    
                    # Use parsed published date for Date of video as requested
                    pub_date_raw = entry.get("published", "")
                    pub_parsed = entry.get("published_parsed")
                    if isinstance(pub_parsed, (time.struct_time, tuple)):
                        formatted_date = time.strftime('%Y%m%d', pub_parsed)
                    elif isinstance(pub_parsed, list):
                        formatted_date = time.strftime('%Y%m%d', tuple(pub_parsed))
                    else:
                        formatted_date = format_date(pub_date_raw)
                    
                    guid = entry.get("id", entry.get("link", ""))
                    link = entry.get("link", "")
                    
                    video_id = entry.get('yt_videoid')
                    if not video_id:
                        match = re.search(r'(?:v=|\\/embed\\/|\\/watch\\?v=|\\/\\d{1,2}\\/|\\/vi\\/|v\\/|https:\\/\\/youtu\\.be\\/)([a-zA-Z0-9_-]{11})', link)
                        if match:
                            video_id = match.group(1)
                            
                    clean_title = sanitize_filename(title)
                    filename = f"{formatted_date}_Transcripts_{clean_title}.md"
                    
                    # Logic for folder organisation
                    org_mode = config.get("folder_organisation", "per_channel")
                    if org_mode == "flat":
                        target_sync_dir = vault_path
                    else:
                        clean_channel = sanitize_filename(channel_name)
                        target_sync_dir = os.path.join(vault_path, clean_channel)
                        os.makedirs(target_sync_dir, exist_ok=True)
                        
                    filepath = os.path.join(target_sync_dir, filename)
                    
                    if os.path.exists(filepath):
                        log(f"✓ Already grabbed: {filename}. Skipping.", progress=current_progress)
                        continue
                        
                    log(f"New video found: {title}", progress=current_progress)
                    
                    transcript_text = None
                    note_type = ""
                    
                    if video_id:
                        log(f"Retrieving YouTube transcript for video {video_id}...")
                        try:
                            from youtube_transcript_api import YouTubeTranscriptApi
                            api = YouTubeTranscriptApi()
                            try:
                                transcript_list = api.fetch(video_id, languages=['en', 'en-US'])
                            except Exception:
                                t_list = api.list(video_id)
                                transcript_list = next(iter(t_list)).fetch()
                            
                            transcript_text = " ".join([t.text for t in transcript_list])
                            note_type = "YouTube Transcript API"
                        except Exception as e:
                            log(f"Could not retrieve YouTube transcript: {e}", "warning")
                            transcript_text = entry.get("description", "No transcript or description available.")
                            note_type = "Video Description (Fallback)"
                    else:
                        log("Could not extract YouTube Video ID from entry.", "error")
                        transcript_text = entry.get("description", "No transcript or description available.")
                        note_type = "Video Description (Fallback)"
                        
                    markdown_content = f"""---
title: "{title}"
channel: "{channel_name}"
date: {formatted_date}
tags: [youtube, transcript]
---

# {title}

**Channel:** {channel_name}
**Published:** {pub_date_raw}
**Source Type:** {note_type}
**Video Link:** {link}

---

{transcript_text}
"""
                    try:
                        with open(filepath, 'w', encoding='utf-8') as mf:
                            mf.write(markdown_content)
                        
                        db.add_record(guid, {
                            "rss_url": channel_url,
                            "link": link,
                            "title": title,
                            "file_path": os.path.relpath(filepath, start=vault_path),
                            "sync_date": datetime.datetime.now().isoformat()
                        })
                        
                        log(f"Successfully saved as: {filename}", progress=current_progress)
                    except Exception as e:
                        log(f"Failed to write file {filename}: {e}", "error", progress=current_progress)
                        
        except Exception as e:
            log(f"Fatal execution error: {e}", "error")
        finally:
            log("YouTube Harvest complete.", progress=100)
            q.put(None)
            if caffeinate_proc:
                try:
                    caffeinate_proc.terminate()
                except Exception:
                    pass

    t = threading.Thread(target=worker)
    t.start()
    
    while True:
        import queue
        try:
            item = q.get(timeout=15)
            if item is None:
                break
            yield item
        except queue.Empty:
            yield json.dumps({"type": "heartbeat", "message": None, "progress": "indeterminate"}) + "\\n"

def execute_youtube_sync(channel_index=None, video_index=None):
    logs = []
    for item_str in execute_youtube_sync_generator(channel_index, video_index):
        item = json.loads(item_str)
        logs.append(item["message"])
    return logs

def clear_vault_history(days='all'):
    logs = []
    def log(msg):
        logs.append(msg)
        print(msg)
        
    config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.json'))
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        log(f"Configuration file not found at {config_path}.")
        return logs

    vault_path = config.get("obsidian_vault_path", "./Vault")
    vault_path = os.path.expanduser(vault_path)
    
    if not os.path.exists(vault_path):
        log("Vault path does not exist. Nothing to clear.")
        return logs

    now = time.time()
    threshold_seconds = None
    
    if days != 'all':
        try:
            threshold_seconds = int(days) * 86400
        except ValueError:
            log(f"Invalid days parameter: {days}")
            return logs

    deleted_count = 0
    # Walk through the vault directory
    for root, dirs, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                
                if threshold_seconds is not None:
                    # Check modification time
                    mtime = os.path.getmtime(file_path)
                    age_seconds = now - mtime
                    if age_seconds <= threshold_seconds:
                        try:
                            os.remove(file_path)
                            log(f"Deleted (Created <{days}d ago): {file}")
                            deleted_count += 1
                        except Exception as e:
                            log(f"Failed to delete {file}: {e}")
                else:
                    # Clear all
                    try:
                        os.remove(file_path)
                        log(f"Deleted: {file}")
                        deleted_count += 1
                    except Exception as e:
                        log(f"Failed to delete {file}: {e}")
                        
    log(f"History clearance complete. Removed {deleted_count} files.")
    
    # If clearing all, also clear the sync history database
    if days == 'all':
        db.clear()
        log("Sync history database cleared.")
        
    return logs

if __name__ == "__main__":
    execute_sync()
