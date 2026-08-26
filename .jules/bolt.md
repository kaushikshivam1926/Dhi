## 26-08-2026 - Bulk Query Optimization for Historical Macro Deltas
**Learning:** Calling sequential single-item SQLite lookup functions inside a loop creates an N+1 query pattern with significant connection overhead and redundant queries per series. Using SQLite window functions (`ROW_NUMBER() OVER (PARTITION BY series_id ...)`) and `IN` chunking allows calculating historical comparisons across dozens of series in a batch.
**Action:** When computing historical comparisons or deltas across multiple series from SQLite, export a bulk lookup API (`compute_deltas_bulk`) that uses window functions and batched SQL statements rather than looping individual lookups.

## 26-08-2024 - Optimizing `os.walk` in Obsidian Vaults
**Learning:** Checking `if '.obsidian' in root: continue` inside an `os.walk` loop is an anti-pattern. While it skips processing files in that directory, `os.walk` still physically traverses the entire directory structure first. For Obsidian vaults, the `.obsidian` and `.git` folders can contain thousands of cache/plugin/object files, causing severe performance bottlenecks during scans.
**Action:** Always modify the `dirs` list in-place (`dirs[:] = [d for d in dirs if not d.startswith('.')]`) so `os.walk` prunes the tree and completely skips descending into hidden directories.
