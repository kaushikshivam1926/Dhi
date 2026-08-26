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
        Scans existing vault for MD files and populate history based on frontmatter.
        Optimized with multiprocessing for large vaults.
        """
        import multiprocessing

        vault_path = os.path.expanduser(vault_path)
        if not os.path.exists(vault_path):
            return 0
            
        md_files = []
        for root, dirs, files in os.walk(vault_path):
            # Prune hidden directories like .obsidian and .git
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md'):
                    md_files.append(os.path.join(root, file))

        if not md_files:
            return 0

        count = 0

        # Determine whether to use multiprocessing or synchronous execution
        if len(md_files) > 100:
            num_workers = min(os.cpu_count() or 4, len(md_files))
            chunk_size = max(1, len(md_files) // (num_workers * 2))

            with multiprocessing.Pool(processes=num_workers) as pool:
                for res in pool.imap_unordered(_process_file_for_migration, md_files, chunksize=chunk_size):
                    if res:
                        title = res["title"]
                        key = f"migrated-{title}"
                        if key not in self.history:
                            self.history[key] = {
                                "title": title,
                                "file_path": os.path.relpath(res["file_path"], start=vault_path),
                                "migrated": True
                            }
                            count += 1
        else:
            # For small number of files, sync execution is faster due to lower overhead
            for file_path in md_files:
                res = _process_file_for_migration(file_path)
                if res:
                    title = res["title"]
                    key = f"migrated-{title}"
                    if key not in self.history:
                        self.history[key] = {
                            "title": title,
                            "file_path": os.path.relpath(res["file_path"], start=vault_path),
                            "migrated": True
                        }
                        count += 1

        if count > 0:
            self._save()
        return count

def _process_file_for_migration(file_path):
    """
    Helper top-level function for multiprocessing.
    Reads the file, extracts the title using fast string matching, and returns metadata.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(1000) # Only read start for frontmatter

            # Fast substring match for title instead of regex
            title_idx = content.find('\ntitle: "')
            if title_idx == -1 and content.startswith('title: "'):
                title_idx = 0
            elif title_idx != -1:
                title_idx += 1

            if title_idx != -1:
                end_idx = content.find('"', title_idx + 8)
                if end_idx != -1:
                    title = content[title_idx + 8:end_idx]
                    return {
                        "title": title,
                        "file_path": file_path
                    }
    except Exception:
        pass
    return None

# Global instance
db = SyncHistory()
