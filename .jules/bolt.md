## 26-08-2026 - Bulk Query Optimization for Historical Macro Deltas
**Learning:** Calling sequential single-item SQLite lookup functions inside a loop creates an N+1 query pattern with significant connection overhead and redundant queries per series. Using SQLite window functions (`ROW_NUMBER() OVER (PARTITION BY series_id ...)`) and `IN` chunking allows calculating historical comparisons across dozens of series in a batch.
**Action:** When computing historical comparisons or deltas across multiple series from SQLite, export a bulk lookup API (`compute_deltas_bulk`) that uses window functions and batched SQL statements rather than looping individual lookups.

## 26-08-2024 - Optimizing `os.walk` in Obsidian Vaults
**Learning:** Checking `if '.obsidian' in root: continue` inside an `os.walk` loop is an anti-pattern. While it skips processing files in that directory, `os.walk` still physically traverses the entire directory structure first. For Obsidian vaults, the `.obsidian` and `.git` folders can contain thousands of cache/plugin/object files, causing severe performance bottlenecks during scans.
**Action:** Always modify the `dirs` list in-place (`dirs[:] = [d for d in dirs if not d.startswith('.')]`) so `os.walk` prunes the tree and completely skips descending into hidden directories.

## 26-08-2026 - Optimize vault scanning via multiprocessing and fast string matching
**Learning:** Synchronous file I/O and regex processing inside os.walk loops is a significant bottleneck when processing thousands of markdown files (e.g., an Obsidian vault). Multiprocessing significantly improves both cold and warm cache performance by decoupling disk reads from directory traversal and distributing parsing. Using native string searching over regex provides a major speedup for simple frontmatter extraction.
**Action:** Use multiprocessing.Pool with chunking for large I/O bound batch file processing operations, ensuring worker functions are defined at the top level for pickling. Always evaluate if string finding can replace simple regex extractions.

## 27-02-2025 - Repeated Regex Compilation in Tight Loop
**Learning:** Parsing large markdown files by dynamically creating regex patterns via `re.finditer(pattern)` within a nested loop introduces unnecessary regex compilation/cache lookup overhead. Python's regex cache limits the overhead compared to full recompilation, but it still exists and adds up on large files.
**Action:** Extract repeating inline regex definitions and define them using `re.compile()` at the module level.
