import json
import os
import re

class SyncHistory:
    def __init__(self, db_path='sync_history.json'):
        self.db_path = db_path
        self.history = self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.history, f, indent=2)

    def add_record(self, guid, info):
        """
        guid: unique identifier (str)
        info: dict with rss_url, title, file_path, sync_date
        """
        self.history[guid] = info
        self._save()

    def get_record(self, guid):
        return self.history.get(guid)

    def is_synced(self, guid, vault_path=None):
        record = self.get_record(guid)
        if not record:
            return False
            
        file_path = record.get('file_path')
        if not file_path:
            return False
            
        # Ensure path is absolute for checking
        # Logic: 
        # 1. If absolute, check it
        # 2. If relative, it's relative to vault_path
        abs_path = os.path.expanduser(file_path)
        if not os.path.isabs(abs_path):
            if vault_path:
                abs_path = os.path.join(os.path.expanduser(vault_path), file_path)
            else:
                # Fallback to app root if no vault_path provided
                abs_path = os.path.join(os.path.dirname(self.db_path), file_path)
            
        return os.path.exists(abs_path)

    def remove_record(self, guid):
        if guid in self.history:
            del self.history[guid]
            self._save()

    def clear(self):
        self.history = {}
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def scan_vault_for_migration(self, vault_path):
        """
        Scans existing vault for MD files and populate history based on frontmatter
        """
        vault_path = os.path.expanduser(vault_path)
        if not os.path.exists(vault_path):
            return
            
        count = 0
        for root, dirs, files in os.walk(vault_path):
            # Prune hidden directories like .obsidian and .git
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md'):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read(1000) # Only read start for frontmatter
                            
                            # Extremely simple frontmatter parsing
                            title_match = re.search(r'^title: "(.*?)"', content, re.M)
                            url_match = re.search(r'^audio_url: (.*?)$', content, re.M) # We might need audio_url as a backup ID
                            
                            if title_match:
                                title = title_match.group(1)
                                # We'll use a title-based key if no GUID is found during scan
                                # This is a best-effort migration
                                key = f"migrated-{title}"
                                if key not in self.history:
                                    self.history[key] = {
                                        "title": title,
                                        "file_path": os.path.relpath(path, start=vault_path),
                                        "migrated": True
                                    }
                                    count += 1
                    except:
                        continue
        if count > 0:
            self._save()
        return count

# Global instance
db = SyncHistory()
