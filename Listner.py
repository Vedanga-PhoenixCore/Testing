"""
webhook_listener.py

Receives GitHub push events and automatically runs the incremental
ingestion pipeline (parser -> sentences -> retain) on changed Python files.

Run this alongside your Hindsight container:
    pip install fastapi uvicorn requests
    python webhook_listener.py

Exposes: POST /webhook on port 8889
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading

import requests
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ── Configuration ────────────────────────────────────────────────────────────

WEBHOOK_SECRET   = os.environ.get("GITHUB_WEBHOOK_SECRET", "")   # must match what you set in GitHub
HINDSIGHT_URL    = os.environ.get("HINDSIGHT_URL", "http://localhost:8888")
BANK_NAME        = os.environ.get("BANK_NAME", "drone-test")
REPO_CLONE_DIR   = os.environ.get("REPO_CLONE_DIR", "./repos")   # where repos are cloned locally
PIPELINE_SCRIPT  = os.environ.get("PIPELINE_SCRIPT", "./Pipeline.py")  # your existing retain script

# Only process pushes to these branches (empty list = all branches)
TRACKED_BRANCHES = os.environ.get("TRACKED_BRANCHES", "main,master").split(",")

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI()


def verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify the HMAC-SHA256 signature GitHub sends with every webhook.
    This confirms the request genuinely came from GitHub, not a random caller.
    If no secret is configured, skip verification (dev/test only).
    """
    if not WEBHOOK_SECRET:
        print("⚠️  GITHUB_WEBHOOK_SECRET not set — skipping signature verification (dev mode)")
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def get_changed_python_files(commits: list) -> list:
    """
    Extract the set of unique .py files that were added or modified
    across all commits in this push. Ignores deleted files.
    """
    changed = set()
    for commit in commits:
        for filepath in commit.get("added", []) + commit.get("modified", []):
            if filepath.endswith(".py"):
                changed.add(filepath)
    return list(changed)


def should_skip(filepath: str) -> bool:
    """
    Return True for files we don't want to ingest:
    test files, vendored deps, auto-generated code, migrations.
    """
    skip_patterns = [
        "test_", "_test.py", "/tests/", "/vendor/",
        "__pycache__", "migrations/", "generated/", "setup.py",
    ]
    return any(p in filepath for p in skip_patterns)


def run_ingestion(repo_name: str, repo_url: str, changed_files: list):
    """
    Pull the latest code and run the ingestion pipeline on each changed file.
    Runs in a background thread so the webhook endpoint can respond in < 10s.
    """
    repo_path = os.path.join(REPO_CLONE_DIR, repo_name)

    # Clone the repo if it doesn't exist locally yet
    if not os.path.exists(repo_path):
        #print(f"Cloning {repo_url} into {repo_path} ...")
        #subprocess.run(["git", "clone", repo_url, repo_path], check=True)
        pass
    else:
        #print(f"Pulling latest for {repo_name} ...")
        #subprocess.run(["git", "-C", repo_path, "pull"], check=True)
        pass
    
    ingested = 0
    skipped  = 0

    for relative_path in changed_files:
        full_path = os.path.join(repo_path, relative_path)

        if should_skip(relative_path):
            print(f"  ⏭  Skipping {relative_path} (matches skip pattern)")
            skipped += 1
            continue

        if not os.path.exists(full_path):
            print(f"  ⚠️  {relative_path} not found after pull (may have been deleted)")
            continue

        print(f"  ▶  Ingesting {relative_path} ...")
        result = subprocess.run(
            [sys.executable, PIPELINE_SCRIPT, full_path],
            capture_output=True,
            text=True,
            env={**os.environ, "HINDSIGHT_URL": HINDSIGHT_URL, "BANK_NAME": BANK_NAME}
        )

        if result.returncode == 0:
            print(f"  ✅ {relative_path} — done")
            ingested += 1
        else:
            print(f"  ❌ {relative_path} — FAILED")
            print(result.stdout[-500:] if result.stdout else "")
            print(result.stderr[-500:] if result.stderr else "")

    print(f"\nIngestion complete for {repo_name}: {ingested} ingested, {skipped} skipped.")


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def github_webhook(request: Request):
    payload_bytes = await request.body()

    # 1. Verify signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(payload_bytes, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Only handle push events
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type == "ping":
        # GitHub sends a ping when the webhook is first created — respond 200
        return JSONResponse({"message": "pong"})

    if event_type != "push":
        return JSONResponse({"message": f"Ignoring event type: {event_type}"})

    payload = json.loads(payload_bytes)

    # 3. Check branch filter
    ref = payload.get("ref", "")                         # e.g. "refs/heads/main"
    branch = ref.replace("refs/heads/", "")
    if TRACKED_BRANCHES and branch not in TRACKED_BRANCHES:
        return JSONResponse({"message": f"Ignoring push to branch: {branch}"})

    # 4. Extract changed Python files
    commits = payload.get("commits", [])
    changed_files = get_changed_python_files(commits)

    if not changed_files:
        return JSONResponse({"message": "No Python files changed in this push"})

    repo_name = payload["repository"]["name"]
    repo_url  = payload["repository"]["clone_url"]

    print(f"\n📦 Push to {repo_name}/{branch} — {len(changed_files)} Python file(s) changed:")
    for f in changed_files:
        print(f"   {f}")

    # 5. Run ingestion in the background (respond to GitHub within 10s)
    thread = threading.Thread(
        target=run_ingestion,
        args=(repo_name, repo_url, changed_files),
        daemon=True
    )
    thread.start()

    return JSONResponse({
        "message": f"Ingestion queued for {len(changed_files)} file(s)",
        "files": changed_files
    })


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "bank": BANK_NAME, "hindsight": HINDSIGHT_URL}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Webhook listener starting on port 8889")
    print(f"Hindsight:  {HINDSIGHT_URL}")
    print(f"Bank:       {BANK_NAME}")
    print(f"Branches:   {TRACKED_BRANCHES}")
    print(f"Secret set: {'yes' if WEBHOOK_SECRET else 'NO (dev mode)'}")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8889)