# SAMVIT & DHĪ Project Migration Guide

To migrate your complete setup to your new Mac Mini, you need to migrate both your **SAMVIT Obsidian Vault** (which holds your data) and the **Podcast to Obsidian (DHĪ)** background service (which fetches and transcribes podcasts).

Follow these step-by-step instructions.

## Part 1: Migrating the SAMVIT Obsidian Vault

Since your vault is stored in iCloud (`iCloud~md~obsidian/Documents/SAMVIT`), Apple handles most of the heavy lifting.

1. **Sign in to iCloud:** On your new Mac Mini, ensure you are signed in with the same Apple ID and that **iCloud Drive** is enabled.
2. **Wait for Sync:** Allow your Mac a few minutes to download your files from iCloud Drive. You can check the progress in Finder under the iCloud Drive section.
3. **Install Obsidian:** Download and install [Obsidian](https://obsidian.md/) if you haven't already.
4. **Open the Vault:** Launch Obsidian, click **Open folder as vault**, and navigate to:
   `iCloud Drive -> Obsidian -> SAMVIT`
   *(Or its absolute path: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SAMVIT`)*

---

## Part 2: Migrating the "Podcast to Obsidian" Pipeline

Your background Python scripts and web interface are located locally in `~/Podcast to Obsidian`. You will need to manually move this folder and reinstall its environment.

### 1. Transfer the Folder
On your **old Mac**, it's best to compress the folder to avoid copying the heavy virtual environments:
1. Open Terminal and zip the folder, excluding the generated caches:
   ```bash
   cd ~
   zip -r pod2obs.zip "Podcast to Obsidian" -x "Podcast to Obsidian/.venv*" -x "Podcast to Obsidian/__pycache__/*"
   ```
2. Transfer `pod2obs.zip` to your new Mac Mini (via AirDrop, a USB drive, or iCloud Drive).
3. On the **new Mac Mini**, unzip the file into your Home folder (`~`).

### 2. Install System Dependencies (FFmpeg)
Since the DHĪ pipeline processes audio files (and based on our previous troubleshooting), you'll need FFmpeg installed to avoid audio conversion errors.
On your **new Mac Mini**, open Terminal and run:
```bash
# Install Homebrew if you don't have it:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install FFmpeg:
brew install ffmpeg
```

### 3. Setup the Python Environment
Once the folder is on your new Mac Mini, you need to recreate the Python virtual environment and reinstall your libraries (like PyTorch, Whisper, Markitdown, etc.).

Open Terminal on the **new Mac Mini** and run:
```bash
cd ~/Podcast\ to\ Obsidian

# Create a new virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install all the required packages
pip install -r requirements.txt
```

### 4. Verify Configuration Paths
If your username on the new Mac Mini is different from `shivamkaushik`, you must update your `config.json`.
1. Open `~/Podcast to Obsidian/config.json`.
2. Ensure the `obsidian_vault_path` points to your correct home directory. For example, change `/Users/shivamkaushik/...` to `/Users/YOUR_NEW_USERNAME/...`.

### 5. Start the App
You are fully migrated! Start your service just like before:
```bash
cd ~/Podcast\ to\ Obsidian
source .venv/bin/activate
python3 main.py
```
*(Or whatever script you use to launch the web interface `app.py` / `Pod2Obs.html`)*
