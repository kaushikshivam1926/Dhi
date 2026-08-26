## 26-08-2024 - Optimizing `os.walk` in Obsidian Vaults
**Learning:** Checking `if '.obsidian' in root: continue` inside an `os.walk` loop is an anti-pattern. While it skips processing files in that directory, `os.walk` still physically traverses the entire directory structure first. For Obsidian vaults, the `.obsidian` and `.git` folders can contain thousands of cache/plugin/object files, causing severe performance bottlenecks during scans.
**Action:** Always modify the `dirs` list in-place (`dirs[:] = [d for d in dirs if not d.startswith('.')]`) so `os.walk` prunes the tree and completely skips descending into hidden directories.
## 27-02-2025 - Repeated Regex Compilation in Tight Loop
**Learning:** Parsing large markdown files by dynamically creating regex patterns via `re.finditer(pattern)` within a nested loop introduces unnecessary regex compilation/cache lookup overhead. Python's regex cache limits the overhead compared to full recompilation, but it still exists and adds up on large files.
**Action:** Extract repeating inline regex definitions and define them using `re.compile()` at the module level.
