# Podcast to Obsidian Sync

An automated pipeline that reads Podcast RSS feeds, extracts or generates the absolute full transcript of new episodes, and saves them directly to your Obsidian Vault as heavily formatted Markdown files.

## Features
- **RSS Native Parsing:** Zero web-scraping brittleness. 
- **Automated Directory Management:** Saves securely and cleanly in `<Date>_<Channel>_<Show>_<Title>.md` nomenclature.
- **Multiple Transcripts Protocols:**
  - Will safely pull native 100% free VTT/SRT files located in `<podcast:transcript>` tags when available.
  - Connects to AI Speech-to-Text (STT) services like *AssemblyAI* via configuration switch for shows that do not natively provide transcripts.

## 🚀 How to Share / Quick Start

To share this app with others, just send them this folder! To run the script locally on any Mac/Linux machine:

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Configure your vault and shows
# Edit the config.json file to map where you want the transcripts to go

# 4. Run the sync
python3 main.py
```

---

## 🐳 Deploying via Docker (For Servers, NAS, Raspberry Pi)

To make this app permanently deployable and completely decoupled from your operating system, we have fully "Dockerized" the script. This means you can run it perfectly on a cheap cloud VPS, a Raspberry Pi, or a Synology NAS without ever installing Python.

### 1. Build the Docker Image
Inside this directory, run:
```bash
docker build -t podcast-obsidian-sync .
```

### 2. Run the Container
Because the script saves files, we must "mount" your real-world folders into the container. We also use an environment variable so the container knows where your configuration is.

```bash
docker run -d \
  --name pod-sync \
  -e CONFIG_PATH="/app/config/config.json" \
  -v /path/to/your/actual/config.json:/app/config/config.json \
  -v /path/to/your/actual/ObsidianVault:/app/Vault \
  podcast-obsidian-sync
```

> **Note on Scheduling:** 
> A Docker container runs once and stops. To emulate a daily scheduled "cron" job with Docker, you can run the `docker run` command via your server's crontab or via standard Docker workflow orchestration tools like Docker Swarm or run it within a simple bash `while true; do docker start -i pod-sync; sleep 86400; done` loop!
57: 
58: ---
59: 
60: ## 🗺️ Roadmap & Future Upgrades
61: 
62: - **Python 3.10+ Migration:** Plan to upgrade the environment to support Microsoft's `markitdown` for more advanced document processing (PowerPoint, Excel, etc.). Currently running on Python 3.9 with compatible libraries (`PyMuPDF`, `python-docx`).
63: - **SAMVIT Integration:** Enhance deeper cross-linking between document harvests and podcast transcripts.
