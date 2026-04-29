#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
    echo -e "\n${CYAN}Shutting down...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null

    # Free GPU memory — unload all models from Ollama
    echo -e "${CYAN}Unloading LLM models from GPU...${NC}"
    curl -s http://127.0.0.1:11434/api/generate -d '{"model":"qwen3:8b","keep_alive":0}' > /dev/null 2>&1
    echo -e "${GREEN}Done. GPU memory freed.${NC}"
}
trap cleanup EXIT INT TERM

# --- Check prerequisites ---

# Python venv
if [ ! -f "$ROOT/.venv/bin/python" ]; then
    echo -e "${CYAN}Creating Python venv...${NC}"
    python3 -m venv "$ROOT/.venv"
    "$ROOT/.venv/bin/pip" install -e "$ROOT" --quiet
fi

# Node.js (via nvm)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

if ! command -v node &>/dev/null; then
    echo -e "${RED}Node.js not found. Install it with: nvm install 22${NC}"
    exit 1
fi

# Frontend dependencies
if [ ! -d "$ROOT/frontend/node_modules" ]; then
    echo -e "${CYAN}Installing frontend dependencies...${NC}"
    cd "$ROOT/frontend" && npm install --quiet
fi

# Data directory
mkdir -p "$ROOT/data/uploads"

# Check for GPU-hogging processes from other projects (skip Ollama and desktop apps)
GPU_PIDS=""
while IFS=',' read -r pid mem; do
    pid=$(echo "$pid" | xargs)
    mem_val=$(echo "$mem" | grep -oP '\d+')
    [ -z "$mem_val" ] || [ "$mem_val" -le 500 ] && continue
    CMD=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')
    # Skip Ollama, gnome-shell, chrome, and other system processes
    echo "$CMD" | grep -qiE "ollama|gnome-shell|chrome|Xwayland|nautilus|ptyxis" && continue
    GPU_PIDS="$GPU_PIDS $pid"
    echo -e "  ${RED}PID $pid: ${mem_val} MiB — ${CMD:0:80}${NC}"
done < <(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null)

if [ -n "$GPU_PIDS" ]; then
    echo -e "${RED}Warning: Non-system processes using >500MB GPU memory detected (above)${NC}"
    echo -e "${CYAN}Free GPU memory for faster LLM inference? (kill these processes) [y/N]${NC}"
    read -r ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        kill $GPU_PIDS 2>/dev/null
        sleep 2
        echo -e "${GREEN}GPU memory freed.${NC}"
    fi
fi

# --- Start services ---

echo -e "${GREEN}Starting Space Dashboard${NC}"
echo -e "${CYAN}Backend:  ${NC}http://localhost:8000"
echo -e "${CYAN}Frontend: ${NC}http://localhost:3000"
echo ""

# Backend
cd "$ROOT"
"$ROOT/.venv/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --reload \
    --log-level info &
BACKEND_PID=$!

# Frontend
cd "$ROOT/frontend"
npx vite --host 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}Both servers running. Press Ctrl+C to stop.${NC}"
echo ""

wait
