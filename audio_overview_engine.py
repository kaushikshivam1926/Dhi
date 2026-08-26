import os
import re
import json
import time
import asyncio
import tempfile
import datetime
from pathlib import Path
from pydub import AudioSegment
import edge_tts

from doc_processor import call_gemini_text, sanitize_filename

AVAILABLE_VOICES = [
    {
        "id": "en-US-AndrewNeural",
        "name": "Andrew (US Male - Warm & Conversational)",
        "gender": "Male",
        "locale": "en-US"
    },
    {
        "id": "en-US-AvaNeural",
        "name": "Ava (US Female - Clear & Dynamic)",
        "gender": "Female",
        "locale": "en-US"
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy (US Male - Deep & Professional)",
        "gender": "Male",
        "locale": "en-US"
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny (US Female - Engaging & Friendly)",
        "gender": "Female",
        "locale": "en-US"
    },
    {
        "id": "en-US-BrianNeural",
        "name": "Brian (US Male - Analytical & Authoritative)",
        "gender": "Male",
        "locale": "en-US"
    },
    {
        "id": "en-US-EmmaNeural",
        "name": "Emma (US Female - Articulate & Energetic)",
        "gender": "Female",
        "locale": "en-US"
    },
    {
        "id": "en-GB-RyanNeural",
        "name": "Ryan (UK Male - Polished British)",
        "gender": "Male",
        "locale": "en-GB"
    },
    {
        "id": "en-GB-SoniaNeural",
        "name": "Sonia (UK Female - Refined British)",
        "gender": "Female",
        "locale": "en-GB"
    },
    {
        "id": "en-IN-PrabhatNeural",
        "name": "Prabhat (Indian Male - Clear & Natural)",
        "gender": "Male",
        "locale": "en-IN"
    },
    {
        "id": "en-IN-NeerjaNeural",
        "name": "Neerja (Indian Female - Expressive & Professional)",
        "gender": "Female",
        "locale": "en-IN"
    }
]

class AudioOverviewEngine:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.reload_config()

    def reload_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}

        audio_cfg = self.config.get("audio_overview", {})
        self.input_folder = audio_cfg.get("input_folder", "/Users/shivamkaushik/Library/Mobile Documents/iCloud~md~obsidian/Documents/SAMVIT/05_Digests")
        self.output_folder = audio_cfg.get("output_folder", "./Vault/Podcasts")
        self.host1_voice = audio_cfg.get("host1_voice", "en-US-AndrewNeural")
        self.host2_voice = audio_cfg.get("host2_voice", "en-US-AvaNeural")
        self.default_style = audio_cfg.get("default_style", "deep_dive")
        self.gemini_key = self.config.get("api_keys", {}).get("gemini", "")
        self.gemini_model = self.config.get("gemini_model", "gemini-3.1-flash-lite")

    def scan_input_files(self, folder_path=None):
        """Scan input folder for articles/syntheses (.md, .txt, .docx, .pdf)"""
        target_dir = folder_path or self.input_folder
        if not os.path.isabs(target_dir):
            target_dir = os.path.abspath(target_dir)

        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            return []

        supported_exts = [".md", ".txt", ".docx", ".pdf"]
        found_files = []

        for root, dirs, files in os.walk(target_dir):
            if ".obsidian" in root or ".git" in root or "Podcasts" in root:
                continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, target_dir)
                    mtime = os.path.getmtime(full_path)
                    date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

                    # Read preview
                    preview = ""
                    word_count = 0
                    try:
                        if ext in [".md", ".txt"]:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                                words = content.split()
                                word_count = len(words)
                                preview = " ".join(words[:40]) + ("..." if len(words) > 40 else "")
                    except Exception:
                        preview = "(Binary or unreadable content)"

                    # Extract display title
                    display_title = os.path.splitext(file)[0].replace("_", " ").replace("-", " ")

                    found_files.append({
                        "filename": file,
                        "relative_path": rel_path,
                        "full_path": full_path,
                        "title": display_title,
                        "extension": ext,
                        "word_count": word_count,
                        "mtime": mtime,
                        "date_str": date_str,
                        "preview": preview
                    })

        # Sort newest first
        found_files.sort(key=lambda x: x["mtime"], reverse=True)
        return found_files

    def read_article_contents(self, file_paths):
        """Read text from a list of relative or absolute file paths."""
        combined_text = []
        for path in file_paths:
            full_p = path if os.path.isabs(path) else os.path.abspath(path)
            if not os.path.exists(full_p):
                # Try finding relative to input folder
                alt_p = os.path.join(os.path.abspath(self.input_folder), path)
                if os.path.exists(alt_p):
                    full_p = alt_p

            if not os.path.exists(full_p):
                continue

            fname = os.path.basename(full_p)
            ext = os.path.splitext(fname)[1].lower()

            try:
                if ext in [".md", ".txt"]:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                        combined_text.append(f"--- ARTICLE: {fname} ---\n{text}\n")
                elif ext == ".pdf":
                    import fitz
                    doc = fitz.open(full_p)
                    pdf_text = "\n".join([page.get_text() for page in doc])
                    combined_text.append(f"--- ARTICLE: {fname} ---\n{pdf_text}\n")
                elif ext == ".docx":
                    from docx import Document
                    doc = Document(full_p)
                    docx_text = "\n".join([p.text for p in doc.paragraphs if p.text])
                    combined_text.append(f"--- ARTICLE: {fname} ---\n{docx_text}\n")
            except Exception as e:
                print(f"Error reading {full_p}: {e}")

        return "\n\n".join(combined_text)

    def _call_gemini_with_retry(self, prompt, temperature=0.4, retries=3):
        import doc_processor
        doc_processor._gemini_quota_exhausted = False  # Clear any stale quota flag

        models_to_try = [self.gemini_model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        # Remove duplicates while preserving order
        seen = set()
        models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

        last_error = None
        for model_id in models:
            for attempt in range(retries):
                try:
                    res = call_gemini_text(prompt, self.gemini_key, model_id, temperature=temperature)
                    if res and res.strip():
                        return res
                    time.sleep(2)
                except Exception as e:
                    last_error = e
                    time.sleep(2)

        raise RuntimeError(f"Gemini API failed to return text content after retries across models {models}. Error: {last_error}")

    def _parse_json_turns(self, raw_text):
        if not raw_text:
            raise ValueError("Gemini returned empty text response.")
        clean = raw_text.strip()
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean, re.DOTALL)
            if match:
                clean = match.group(1)
            else:
                lines = clean.split("\n")
                clean = "\n".join([l for l in lines if not l.startswith("```")])
        try:
            return json.loads(clean)
        except Exception:
            match = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Failed to parse Gemini dialogue JSON output. Raw snippet: {raw_text[:300]}")

    def generate_notebooklm_script(self, articles_text, overview_style="deep_dive", target_duration="18-20", host1_name="Alex", host2_name="Jamie", custom_topic=None, log_callback=None):
        """Generate a multi-section 2-host NotebookLM podcast dialogue script targeting 18-20+ minutes (~60-80 turns)."""
        self.reload_config()
        if not self.gemini_key:
            raise ValueError("Gemini API key is missing in config.json. Please add your Gemini key in Settings.")

        # Determine section count based on target duration
        if target_duration in ["18-20", "20", "long"]:
            section_count = 6
        elif target_duration in ["10-12", "12", "medium"]:
            section_count = 4
        else:
            section_count = 1  # 4-5 min single-pass fast podcast

        if log_callback:
            log_callback(f"Analyzing articles for a {target_duration} min NotebookLM podcast ({section_count} deep dive sections)...")

        # Fast single pass for short podcasts
        if section_count == 1:
            prompt = f"""You are a master podcast producer scripting a 2-person audio overview show in the exact style of Google NotebookLM's Deep Dive.
Format: {overview_style}
Host 1 (Alex - curious interviewer), Host 2 (Jamie - expert analyst).

CRITICAL RULES:
1. OUTPUT MUST BE STRICTLY VALID JSON ONLY. Do not include Markdown blocks (```json) or prose outside the JSON array.
2. The JSON array must contain dialogue turns. Each item must have "speaker" ("Host 1" or "Host 2") and "text".
3. Write 15 to 22 turns of dialogue.

JSON Format:
[
  {{"speaker": "Host 1", "text": "Welcome back to today's Audio Overview!..."}},
  {{"speaker": "Host 2", "text": "Thanks Alex! Today we have some fascinating developments..."}}
]

SOURCE ARTICLES:
{articles_text[:30000]}
"""
            script_raw = self._call_gemini_with_retry(prompt, temperature=0.5)
            turns = self._parse_json_turns(script_raw)
            return turns

        # Multi-section generation for 18-20 min or 10-12 min deep dive
        outline_prompt = f"""You are a senior executive podcast producer outlining an extended {target_duration} minute NotebookLM Deep Dive audio overview episode.

Analyze the source articles and create an outline with exactly {section_count} distinct, logical thematic sections.
For each section, provide a clear section title and 3 specific sub-topics/data points to explore in detail.

Return STRICTLY JSON array:
[
  {{"section_num": 1, "title": "Headline News & Macro Setting", "topics": ["Major central bank moves", "Core CPI vs food inflation", "Initial market reaction"]}},
  ...
]

SOURCE ARTICLES:
{articles_text[:35000]}
"""

        outline_raw = self._call_gemini_with_retry(outline_prompt, temperature=0.4)
        sections = self._parse_json_turns(outline_raw)

        if log_callback:
            log_callback(f"Created episode outline with {len(sections)} sections. Expanding detailed dialogue turns...")

        all_turns = []

        style_instructions = {
            "deep_dive": "Engaging 2-host conversational chemistry. Host 1 (Alex) asks probing follow-up questions, asks for concrete examples and metaphors. Host 2 (Jamie) provides granular, detailed analysis, data breakdowns, and real-world implications. Natural speech fillers like 'Right', 'Exactly', 'Wait, so...', 'That's a huge shift because...'.",
            "executive_brief": "Fast-paced, high-density strategic dialogue. Host 1 asks strategic questions, Host 2 delivers multi-layer financial & policy analysis.",
            "debate_analysis": "Debate style. Host 1 presents optimistic opportunities/upside, Host 2 presents critical risks/challenges and opposing scenarios."
        }
        chosen_style = style_instructions.get(overview_style, style_instructions["deep_dive"])

        for i, sec in enumerate(sections, 1):
            sec_title = sec.get("title", f"Section {i}")
            sec_topics = sec.get("topics", [])

            if log_callback:
                progress_pct = int(15 + (i / len(sections)) * 55)
                log_callback(f"[Section {i}/{len(sections)}] Drafting deep dialogue for: '{sec_title}'...", progress=progress_pct)

            last_turns_context = ""
            if all_turns:
                prev_turns = all_turns[-2:]
                last_turns_context = f"Previous conversation snippet to seamlessly transition from:\nHost 1: {prev_turns[0]['text']}\nHost 2: {prev_turns[1]['text']}\n"

            sec_prompt = f"""You are writing Section {i} of {len(sections)} for an extended {target_duration} minute NotebookLM Deep Dive podcast episode between Host 1 (Alex) and Host 2 (Jamie).

Section Focus: {sec_title}
Sub-topics & Data to cover in granular depth:
{json.dumps(sec_topics)}

Style & Mannerisms:
{chosen_style}

{last_turns_context}

CRITICAL RULES:
1. Write 12 to 16 turns of dialogue for this section alone.
2. DO NOT RUSH or summarize superficially. Unpack exact numbers, quotes, causes, sector impacts, and analogies.
3. Host 1 (Alex) MUST ask probing follow-up questions ("Wait, why did that happen?", "How does that affect...", "Can you walk us through the numbers there?").
4. Host 2 (Jamie) MUST provide detailed multi-sentence explanations (3-5 sentences per turn).
5. Output STRICTLY a JSON array: [{{"speaker": "Host 1", "text": "..."}}, {{"speaker": "Host 2", "text": "..."}}]

SOURCE ARTICLES:
{articles_text[:35000]}
"""

            sec_raw = self._call_gemini_with_retry(sec_prompt, temperature=0.55)
            sec_turns = self._parse_json_turns(sec_raw)
            all_turns.extend(sec_turns)

        if log_callback:
            total_words = sum(len(t["text"].split()) for t in all_turns)
            est_mins = round(total_words / 160.0, 1)
            log_callback(f"Successfully generated {len(all_turns)} turns ({total_words} words, ~{est_mins} mins estimated audio).")

        return all_turns


    async def _async_synthesize_turn(self, text, voice, output_path):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    def synthesize_audio(self, turns, host1_voice=None, host2_voice=None, output_path=None, title="Audio Overview Podcast", log_callback=None):
        """Synthesize multi-speaker turns into a seamless MP3 file using edge-tts and pydub."""
        h1_v = host1_voice or self.host1_voice
        h2_v = host2_voice or self.host2_voice

        voices = {
            "Host 1": h1_v,
            "Host 2": h2_v,
            "Alex": h1_v,
            "Jamie": h2_v
        }

        if log_callback:
            log_callback(f"Synthesizing speech for {len(turns)} turns (Host 1: {h1_v}, Host 2: {h2_v})...")

        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=350)  # 350ms gap between speakers
        timestamped_turns = []
        current_time_ms = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            for idx, turn in enumerate(turns):
                speaker = turn.get("speaker", "Host 1")
                # Normalize speaker name
                norm_speaker = "Host 1" if "1" in speaker or "Alex" in speaker else "Host 2"
                text = turn.get("text", "").strip()
                if not text:
                    continue

                voice = voices.get(norm_speaker, h1_v)
                temp_file = os.path.join(temp_dir, f"turn_{idx:03d}.mp3")

                # Run async edge-tts synthesis
                asyncio.run(self._async_synthesize_turn(text, voice, temp_file))

                segment = AudioSegment.from_file(temp_file)
                duration_ms = len(segment)

                # Time formatting MM:SS
                start_sec = int(current_time_ms / 1000)
                m, s = divmod(start_sec, 60)
                time_code = f"{m:02d}:{s:02d}"

                timestamped_turns.append({
                    "turn_index": idx,
                    "speaker": norm_speaker,
                    "text": text,
                    "timestamp": time_code,
                    "start_ms": current_time_ms,
                    "end_ms": current_time_ms + duration_ms
                })

                combined += segment + silence
                current_time_ms += duration_ms + 350

                if log_callback and (idx + 1) % 3 == 0:
                    log_callback(f"Rendered voice turn {idx+1}/{len(turns)}...")

        total_sec = int(current_time_ms / 1000)
        tot_m, tot_s = divmod(total_sec, 60)
        duration_str = f"{tot_m:02d}:{tot_s:02d}"

        # Export combined audio file
        if not output_path:
            safe_t = sanitize_filename(title)
            date_prefix = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"{date_prefix}_{safe_t}.mp3"
            target_dir = os.path.abspath(self.output_folder)
            os.makedirs(target_dir, exist_ok=True)
            output_path = os.path.join(target_dir, filename)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        combined.export(output_path, format="mp3", bitrate="192k")

        if log_callback:
            log_callback(f"Successfully generated podcast audio ({duration_str}) at {output_path}")

        return {
            "output_path": output_path,
            "filename": os.path.basename(output_path),
            "duration": duration_str,
            "duration_ms": current_time_ms,
            "timestamped_turns": timestamped_turns
        }

    def export_to_obsidian_vault(self, title, synthesis_meta, script_turns, timestamped_turns, output_dir=None):
        """Export formatted podcast note with audio player embed and transcript to Obsidian Vault."""
        target_dir = output_dir or self.output_folder
        if not os.path.isabs(target_dir):
            target_dir = os.path.abspath(target_dir)

        os.makedirs(target_dir, exist_ok=True)

        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        safe_t = sanitize_filename(title)
        md_filename = f"{datetime.datetime.now().strftime('%Y%m%d')}_Podcast_{safe_t}.md"
        md_path = os.path.join(target_dir, md_filename)

        mp3_filename = synthesis_meta["filename"]

        # Format transcript turns
        transcript_blocks = []
        for t in timestamped_turns:
            speaker_badge = "**Host 1 (Alex)**" if t["speaker"] == "Host 1" else "**Host 2 (Jamie)**"
            transcript_blocks.append(f"`{t['timestamp']}` {speaker_badge}: {t['text']}")

        transcript_markdown = "\n\n".join(transcript_blocks)

        md_content = f"""---
date: {date_str}
type: audio_overview
title: "{title}"
duration: "{synthesis_meta['duration']}"
audio_file: "{mp3_filename}"
tags:
  - podcast
  - audio-overview
  - notebooklm
  - samvit
---

# 🎙️ {title}

![[{mp3_filename}]]

> **Audio Overview Podcast**  
> *Generated by NotebookLM Audio Overview Engine (DHĪ)*  
> **Duration**: {synthesis_meta['duration']} | **Date**: {date_str}

---

## 📜 Complete Podcast Transcript

{transcript_markdown}
"""

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return md_path

    def get_podcast_history(self, output_dir=None):
        """Fetch past audio overview podcast notes and audio files."""
        target_dir = output_dir or self.output_folder
        if not os.path.isabs(target_dir):
            target_dir = os.path.abspath(target_dir)

        if not os.path.exists(target_dir):
            return []

        podcasts = []
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".md") and ("Podcast" in file or "audio_overview" in file):
                    full_p = os.path.join(root, file)
                    mtime = os.path.getmtime(full_p)
                    date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

                    # Parse note for mp3 filename and metadata
                    mp3_name = ""
                    title = os.path.splitext(file)[0].replace("_", " ")
                    duration = "Unknown"

                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            match_mp3 = re.search(r"audio_file:\s*\"?([^\n\"]+)\"?", content)
                            if match_mp3:
                                mp3_name = match_mp3.group(1).strip()
                            else:
                                match_embed = re.search(r"!\[\[(.*\.mp3)\]\]", content)
                                if match_embed:
                                    mp3_name = match_embed.group(1).strip()

                            match_dur = re.search(r"duration:\s*\"?([^\n\"]+)\"?", content)
                            if match_dur:
                                duration = match_dur.group(1).strip()

                            match_title = re.search(r"title:\s*\"?([^\n\"]+)\"?", content)
                            if match_title:
                                title = match_title.group(1).strip()
                    except Exception:
                        pass

                    mp3_path = os.path.join(target_dir, mp3_name) if mp3_name else ""
                    has_audio = os.path.exists(mp3_path)

                    podcasts.append({
                        "title": title,
                        "date_str": date_str,
                        "duration": duration,
                        "md_filename": file,
                        "md_path": full_p,
                        "mp3_filename": mp3_name,
                        "has_audio": has_audio,
                        "mtime": mtime
                    })

        podcasts.sort(key=lambda x: x["mtime"], reverse=True)
        return podcasts
