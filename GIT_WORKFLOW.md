# Git & GitHub Synchronization Guide

This reference guide details how to sync changes between your local machine and your GitHub repository (`kaushikshivam1926/Dhi`), protect operational files, and manage your everyday workflow.

---

## 1. Quick Cheat Sheet

| Task | Command |
| :--- | :--- |
| **Check current status** | `git status` |
| **Stage all code changes** | `git add .` |
| **Commit staged changes** | `git commit -m "Description of changes"` |
| **Push local commits to GitHub** | `git push origin main` |
| **Pull GitHub changes to local** | `git pull origin main` |
| **Temporarily stash uncommitted changes** | `git stash` |
| **Restore stashed changes** | `git stash pop` |

---

## 2. Daily Development Workflow

### A. Publishing Local Changes to GitHub
When you have added features or made bug fixes locally:

```bash
# 1. Check what files were modified/added
git status

# 2. Stage the changes (tracked and new files respecting .gitignore)
git add .

# 3. Commit your changes with a descriptive message
git commit -m "feat: added new harvesting engine"

# 4. Push to GitHub
git push origin main
```

---

### B. Pulling Changes from GitHub to Local
If you made edits directly on GitHub (or another device) and want to reflect them locally on your Mac:

```bash
git pull origin main
```

---

## 3. Pulling When You Have Uncommitted Local Work

If you have local edits that haven't been committed yet, Git may block `git pull` to avoid overwriting your work.

### Approach 1: Commit first, then pull (Recommended)
```bash
# 1. Save your local work
git add .
git commit -m "WIP: save local changes before pulling"

# 2. Pull remote changes (Git will automatically merge them)
git pull origin main

# 3. Push the combined result back
git push origin main
```

### Approach 2: Stash, Pull, and Pop
If you don't want to create a commit yet:
```bash
# 1. Shelve your uncommitted work temporarily
git stash

# 2. Pull latest version from GitHub
git pull origin main

# 3. Re-apply your local changes on top
git stash pop
```

---

## 4. Inspecting GitHub Changes Before Applying

If you want to review what was changed on GitHub before merging it into your code:

```bash
# 1. Fetch metadata without merging
git fetch origin main

# 2. View incoming commit messages
git log HEAD..origin/main --oneline

# 3. View line-by-line diff of changes
git diff HEAD..origin/main

# 4. Apply the changes once verified
git merge origin/main
```

---

## 5. Protecting Operational & Data Files

The project `.gitignore` is configured to prevent operational data and sensitive keys from ever reaching GitHub:

- **Operational Folders**: `RawMaterials/`, `Sources/`, `Vault/`, `Bin/`
- **Cache & Sessions**: `.data/`, `feed_cache.json`, `sync_history.json`, `web_session.json`, `*.db`
- **Media Outputs**: `*.mp3`, `*.wav`, `*.m4a`
- **Secrets**: `config.json`
- **Logs & Scratch**: `*.log`, `scratch/`, `.venv/`, `node_modules/`

### If you accidentally track an ignored file in the future:
Remove it from Git tracking without deleting it from your computer:
```bash
git rm -r --cached <folder_or_file_name>
git commit -m "Stop tracking <folder_or_file_name>"
```

---

## 6. Resolving Merge Conflicts (If Needed)

If the same line in a file was modified both on GitHub and locally:
1. `git pull origin main` will mark conflict markers (`<<<<<<< HEAD ... >>>>>>>`) inside the affected file.
2. Open the file, edit it to keep the desired code, and delete the marker lines.
3. Mark it resolved and push:
   ```bash
   git add <conflicted_file>
   git commit -m "Resolve merge conflict in <file>"
   git push origin main
   ```

---

## 7. How to Revert / Undo a Merge or Pull

Yes! You can always undo or revert a merge at any point:

### Case 1: You just pulled/merged and want to immediately undo it
If you just ran `git pull` or `git merge` and realized it broke something:
```bash
# Instantly roll back to the state right before the pull/merge
git reset --hard ORIG_HEAD
```
*(Git automatically saves `ORIG_HEAD` as a backup bookmark right before any pull or merge).*

### Case 2: A merge is currently failing or stuck in conflicts
If you are in the middle of a messy merge and want to cancel everything back to clean state:
```bash
git merge --abort
```

### Case 3: You already pushed the merge and want to reverse it safely
If you already shared the merge and want to cleanly reverse its changes via a new commit:
```bash
# Revert a merge commit (keeps branch history intact)
git revert -m 1 <commit-hash-of-the-merge>
git push origin main
```

### Case 4: The Ultimate Safety Net (`git reflog`)
Git tracks every action you take with timestamps. You can jump back to any previous moment:
```bash
# 1. View your history of actions
git reflog

# 2. Reset your workspace to any exact step in the list (e.g., HEAD@{1})
git reset --hard HEAD@{1}
```

