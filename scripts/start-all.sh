#!/usr/bin/env bash
# One-click startup for the Deep Research Agent Platform — all 3 services.
#
# Usage:
#   bash scripts/start-all.sh              # Start everything
#   bash scripts/start-all.sh --no-frontend # Skip Vue frontend
#   bash scripts/start-all.sh --no-java     # Skip Java backend
#   bash scripts/start-all.sh --agent-only  # Only Python agent + MCP
#   bash scripts/start-all.sh --no-mcp      # Skip MCP search stack
#
# Press Ctrl+C to stop all services gracefully.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

# ---- ports ----
MCP_PORT=3210
AGENT_PORT=8001
JAVA_PORT=8082
WEB_PORT=3000

# ---- flags ----
NO_MCP=false; NO_AGENT=false; NO_JAVA=false; NO_FRONTEND=false
AGENT_ONLY=false; SKIP_HEALTH=false; HEALTH_TIMEOUT=120

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-mcp)       NO_MCP=true ;;
        --no-agent)     NO_AGENT=true ;;
        --no-java)      NO_JAVA=true ;;
        --no-frontend)  NO_FRONTEND=true ;;
        --agent-only)   AGENT_ONLY=true ;;
        --skip-health)  SKIP_HEALTH=true ;;
        --timeout)      HEALTH_TIMEOUT="$2"; shift ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
    shift
done

# ---- track PIDs for cleanup ----
PIDS=()

cleanup() {
    echo ""
    echo "=== Shutting down all services ==="
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "[..] Stopping PID $pid ..."
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
    echo "[OK] All services stopped."
    exit 0
}
trap cleanup INT TERM

# ---- helpers ----
http_health() {
    local url="$1" timeout="${2:-5}"
    curl -sf --max-time "$timeout" "$url" >/dev/null 2>&1 && return 0 || return 1
}

wait_health() {
    local url="$1" label="$2" timeout="${3:-$HEALTH_TIMEOUT}"
    local deadline=$(($(date +%s) + timeout))
    while [[ $(date +%s) -lt $deadline ]]; do
        if http_health "$url" 3; then return 0; fi
        sleep 2
    done
    return 1
}

start_bg() {
    local label="$1" workdir="$2" logname="$3"
    shift 3
    local stdout_log="$LOG_DIR/${logname}.out.log"
    local stderr_log="$LOG_DIR/${logname}.err.log"
    echo "[..] Starting $label ..."
    echo "     logs: $stdout_log"
    (
        cd "$workdir"
        "$@" >"$stdout_log" 2>"$stderr_log"
    ) &
    local pid=$!
    PIDS+=($pid)
    echo "$pid"
}

# ─────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Deep Research Agent Platform                   ║"
echo "║   One-Click Startup                              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

parts=()
$NO_MCP      || $AGENT_ONLY || parts+=("MCP Search (:$MCP_PORT)")
$NO_AGENT    || parts+=("Python Agent (:$AGENT_PORT)")
$NO_JAVA     || $AGENT_ONLY || parts+=("Java Backend (:$JAVA_PORT)")
$NO_FRONTEND || $AGENT_ONLY || parts+=("Vue Frontend (:$WEB_PORT)")
echo "Services: ${parts[*]}"
echo ""

# ─────────────────────────────────────────────────────────
# Phase 1: MCP Search
# ─────────────────────────────────────────────────────────
if ! $NO_MCP; then
    echo "─── MCP Search Stack ───"
    if http_health "http://127.0.0.1:$MCP_PORT/health"; then
        echo "[OK] MCP Search already running on :$MCP_PORT"
    else
        echo "[..] Starting MCP Search (npx open-websearch) ..."
        start_bg "MCP Search" "$REPO_ROOT" "mcp-search" \
            npx -y open-websearch@latest serve --port "$MCP_PORT" &
        if ! $SKIP_HEALTH; then
            if wait_health "http://127.0.0.1:$MCP_PORT/health" "MCP Search" 60; then
                echo "[OK] MCP Search started: http://127.0.0.1:$MCP_PORT/health"
            else
                echo "[FAIL] MCP Search health check timed out"
            fi
        fi
    fi
fi

# ─────────────────────────────────────────────────────────
# Phase 2: Python Agent
# ─────────────────────────────────────────────────────────
if ! $NO_AGENT; then
    echo "─── Python Agent ───"
    if http_health "http://127.0.0.1:$AGENT_PORT/agent/health"; then
        echo "[OK] Python Agent already running on :$AGENT_PORT"
    else
        # Ensure .env exists
        if [[ ! -f "$REPO_ROOT/apps/agent-python/.env" ]] && [[ -f "$REPO_ROOT/apps/agent-python/.env.example" ]]; then
            echo "[WARN] .env not found, copying .env.example -> .env"
            cp "$REPO_ROOT/apps/agent-python/.env.example" "$REPO_ROOT/apps/agent-python/.env"
        fi

        start_bg "Python Agent" "$REPO_ROOT/apps/agent-python" "python-agent" \
            bash -c "export PYTHONPATH='$REPO_ROOT/apps/agent-python'; uvicorn app.main:app --host 127.0.0.1 --port $AGENT_PORT --reload"

        if ! $SKIP_HEALTH; then
            if wait_health "http://127.0.0.1:$AGENT_PORT/agent/health" "Python Agent" "$HEALTH_TIMEOUT"; then
                echo "[OK] Python Agent started: http://127.0.0.1:$AGENT_PORT/agent/health"
            else
                echo "[FAIL] Python Agent health check timed out"
            fi
        else
            echo "[OK] Python Agent starting (health check skipped)"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────
# Phase 3: Java Backend
# ─────────────────────────────────────────────────────────
if ! $NO_JAVA && ! $AGENT_ONLY; then
    echo "─── Java Backend ───"
    if http_health "http://127.0.0.1:$JAVA_PORT/api/health"; then
        echo "[OK] Java Backend already running on :$JAVA_PORT"
    else
        if ! command -v mvn &>/dev/null; then
            echo "[WARN] Maven not found — skipping Java backend"
        elif [[ ! -f "$REPO_ROOT/apps/api-java/pom.xml" ]]; then
            echo "[WARN] pom.xml not found — skipping Java backend"
        else
            start_bg "Java Backend" "$REPO_ROOT/apps/api-java" "java-backend" \
                mvn spring-boot:run -q

            if ! $SKIP_HEALTH; then
                if wait_health "http://127.0.0.1:$JAVA_PORT/api/health" "Java Backend" "$HEALTH_TIMEOUT"; then
                    echo "[OK] Java Backend started: http://127.0.0.1:$JAVA_PORT/api/health"
                else
                    echo "[FAIL] Java Backend health check timed out (first startup may take 60-120s)"
                    echo "       Check logs: $LOG_DIR/java-backend.out.log"
                fi
            else
                echo "[OK] Java Backend starting (health check skipped)"
            fi
        fi
    fi
fi

# ─────────────────────────────────────────────────────────
# Phase 4: Vue Frontend
# ─────────────────────────────────────────────────────────
if ! $NO_FRONTEND && ! $AGENT_ONLY; then
    echo "─── Vue Frontend ───"
    if http_health "http://127.0.0.1:$WEB_PORT"; then
        echo "[OK] Vue Frontend already running on :$WEB_PORT"
    else
        if ! command -v npm &>/dev/null; then
            echo "[WARN] npm not found — skipping Vue frontend"
        elif [[ ! -f "$REPO_ROOT/apps/web/package.json" ]]; then
            echo "[WARN] package.json not found — skipping Vue frontend"
        else
            if [[ ! -d "$REPO_ROOT/apps/web/node_modules" ]]; then
                echo "[..] Installing npm dependencies ..."
                (cd "$REPO_ROOT/apps/web" && npm install)
            fi

            start_bg "Vue Frontend" "$REPO_ROOT/apps/web" "vue-frontend" \
                npm run dev

            if ! $SKIP_HEALTH; then
                if wait_health "http://127.0.0.1:$WEB_PORT" "Vue Frontend" "$HEALTH_TIMEOUT"; then
                    echo "[OK] Vue Frontend started: http://127.0.0.1:$WEB_PORT"
                else
                    echo "[FAIL] Vue Frontend health check timed out"
                fi
            else
                echo "[OK] Vue Frontend starting (health check skipped)"
            fi
        fi
    fi
fi

# ─────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   All services started                           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

printf "%-20s %-50s %s\n" "SERVICE" "URL" "STATUS"
printf "%-20s %-50s %s\n" "--------------------" "--------------------------------------------------" "------"

if ! $NO_AGENT; then
    http_health "http://127.0.0.1:$AGENT_PORT/agent/health" && s="✓" || s="✗"
    printf "%-20s %-50s %s\n" "Python Agent" "http://127.0.0.1:$AGENT_PORT/agent/health" "$s"
fi
if ! $NO_JAVA && ! $AGENT_ONLY; then
    http_health "http://127.0.0.1:$JAVA_PORT/api/health" && s="✓" || s="✗"
    printf "%-20s %-50s %s\n" "Java Backend" "http://127.0.0.1:$JAVA_PORT/api/health" "$s"
fi
if ! $NO_FRONTEND && ! $AGENT_ONLY; then
    http_health "http://127.0.0.1:$WEB_PORT" && s="✓" || s="✗"
    printf "%-20s %-50s %s\n" "Vue Frontend" "http://127.0.0.1:$WEB_PORT" "$s"
fi

echo ""
echo "Press Ctrl+C to stop all services and exit."
echo ""

# Keep alive
while true; do sleep 2; done
