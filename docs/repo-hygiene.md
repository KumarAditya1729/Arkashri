# Repo Hygiene Runbook

This repository previously carried local SQLite databases, runtime logs, macOS metadata, and one-off debug artifacts in Git. Part 1 of the hardening plan is to keep them out of the repo now and remove them from history in a controlled rewrite.

## What is blocked now

The versioned pre-commit hook blocks staged files that match these classes:

- SQLite databases and WAL/shm sidecars
- Log, trace, and PID files
- Local runtime folders such as `logs/`, `scratch/`, `backups/`, `tmp/`, and `uploads/`
- Known debug artifacts such as `test_websocket.html` and `run_e2e_local.py`
- OS metadata such as `.DS_Store`

Install the hook once per clone:

```bash
./scripts/install-git-hooks.sh
```

## Remove already tracked junk from the current branch

This keeps local files on disk but stops tracking them in Git:

```bash
git rm --cached -r -- .DS_Store '*/.DS_Store' logs backups scratch tmp temp uploads
git rm --cached -- '*.db' '*.db-*' '*.sqlite' '*.sqlite3' '*.sqlite-shm' '*.sqlite-wal' '*.log' '*.out' '*.err' '*.pid' '*.trace' '*.har' test_websocket.html run_e2e_local.py frontend.pid frontend2.pid uvicorn.log uvicorn2.log server.log
git commit -m "chore: stop tracking local runtime artifacts"
```

If your shell does not expand the globs the way you expect, quote them exactly as shown above.

## Remove the files from all history

History rewriting is destructive and should be done once, with team coordination:

```bash
brew install git-filter-repo
./scripts/clean_git_history.sh
git push --force-with-lease origin <branch>
```

After the force-push, every collaborator must either re-clone or reset to the new branch tip.

## CI baseline

GitHub Actions now validates:

- Python dependency install
- `ruff check .`
- `pytest`
- `frontend/` dependency install, lint, and build when that subproject is present in CI checkout
- Docker image build

That gives us a real merge gate before Part 2 backend hardening begins.

## Current repo caveat

`frontend/` is currently tracked as a gitlink/subproject in the root repository, but the root repo does not have a healthy `.gitmodules` mapping for all nested projects yet. The workflow therefore treats frontend validation as conditional on the `frontend/` checkout actually being present. If you want frontend checks to be mandatory on every PR, the next cleanup step is to either:

- formalize the submodule mapping in `.gitmodules`, or
- flatten the frontend code into the root repository and remove the nested Git metadata
