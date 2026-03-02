#!/bin/bash
# ccdb pre-start script — runs as ExecStartPre before bot process.
# Ensures code is at latest and dependencies are synced.
set -e
cd /home/ebi/claude-code-discord-bridge

UV=/home/ebi/.local/bin/uv

# ── Webhook helper ──
DISCORD_WEBHOOK_URL=""
if [ -f .env ]; then
    DISCORD_WEBHOOK_URL=$(grep -E '^DISCORD_WEBHOOK_URL=' .env | cut -d'=' -f2- | tr -d '"' || true)
fi
send_webhook() {
    local message="$1"
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        local escaped
        escaped=$(printf '%s' "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
        curl -s -o /dev/null -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"content\": $escaped}" || echo "[pre-start] WARNING: webhook failed" >&2
    fi
}

# ── Step 1: Pull latest code ──
echo "[pre-start] Pulling latest code..." >&2
set +e
STASHED=0
if ! git diff --quiet 2>/dev/null; then
    git stash push -m "pre-start auto-stash" --include-untracked 2>&1
    STASHED=1
fi
git pull --ff-only origin main 2>&1
PULL_EXIT=$?
if [ $STASHED -eq 1 ]; then
    git stash drop 2>&1 || true
fi
set -e

if [ $PULL_EXIT -ne 0 ]; then
    echo "[pre-start] WARNING: git pull failed (exit $PULL_EXIT), continuing with current code" >&2
fi

# ── Step 2: Sync dependencies ──
echo "[pre-start] Syncing dependencies..." >&2
$UV sync 2>&1

COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "[pre-start] Code at: ${COMMIT}" >&2

# ── Step 3: Validate imports ──
echo "[pre-start] Validating imports..." >&2
set +e
IMPORT_ERROR=$(.venv/bin/python -c "from claude_discord.main import main" 2>&1)
IMPORT_EXIT=$?
set -e

if [ $IMPORT_EXIT -ne 0 ]; then
    echo "[pre-start] ERROR: Import validation failed:" >&2
    echo "$IMPORT_ERROR" >&2
    send_webhook "⚠️ **ccdb pre-start failed**: Import error.\n\`\`\`\n${IMPORT_ERROR}\n\`\`\`\nAttempting rollback..."

    echo "[pre-start] Rolling back..." >&2
    git revert --no-edit HEAD 2>&1 || git checkout HEAD~1 2>&1
    $UV sync 2>&1

    set +e
    ROLLBACK_ERROR=$(.venv/bin/python -c "from claude_discord.main import main" 2>&1)
    ROLLBACK_EXIT=$?
    set -e

    if [ $ROLLBACK_EXIT -ne 0 ]; then
        echo "[pre-start] FATAL: Import still fails after rollback" >&2
        send_webhook "🔴 **ccdb rollback also failed**.\n\`\`\`\n${ROLLBACK_ERROR}\n\`\`\`\nManual intervention required."
        exit 1
    fi

    send_webhook "✅ **ccdb rollback succeeded**: running on $(git rev-parse --short HEAD)."
fi

# ── Step 4: Cleanup stale worktrees ──
if [ -x /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh ]; then
    /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh 2>&1 || true
fi

echo "[pre-start] All checks passed. Starting bot (${COMMIT})." >&2
