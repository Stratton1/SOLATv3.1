#!/bin/bash
#
# SOLAT Development Script
# Starts both the Python engine and Tauri UI in development mode
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Ensure uv (and other user-installed tools) are on PATH
export PATH="$HOME/.local/bin:$PATH"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi

    # Check uv (Python package manager)
    if ! command -v uv &> /dev/null; then
        log_warn "uv not found. Installing..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    # Check pnpm
    if ! command -v pnpm &> /dev/null; then
        log_error "pnpm is not installed. Install with: npm install -g pnpm"
        exit 1
    fi

    # Check Rust/Cargo
    if ! command -v cargo &> /dev/null; then
        log_error "Rust/Cargo is not installed. Install from https://rustup.rs"
        exit 1
    fi

    log_success "All dependencies found"
}

# Install Python dependencies
setup_engine() {
    log_info "Setting up Python engine..."
    cd "$ROOT_DIR/engine"

    # Create virtual environment and install dependencies using uv
    if [ ! -d ".venv" ]; then
        log_info "Creating Python virtual environment..."
        uv venv
    fi

    log_info "Installing Python dependencies..."
    uv pip install -e ".[dev]"

    log_success "Python engine ready"
}

# Install Node dependencies
setup_ui() {
    log_info "Setting up UI..."
    cd "$ROOT_DIR"

    if [ ! -d "node_modules" ]; then
        log_info "Installing Node dependencies..."
        pnpm install
    fi

    log_success "UI ready"
}

cleanup_stale_engine_pid() {
    if [ -f "$ROOT_DIR/.engine.pid" ]; then
        OLD_PID=$(cat "$ROOT_DIR/.engine.pid")
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            log_warn "Stopping stale engine process (PID: $OLD_PID)..."
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$ROOT_DIR/.engine.pid"
    fi
}

ensure_port_free() {
    local port=8765
    if command -v lsof &> /dev/null; then
        local pids
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            log_warn "Port $port is in use. Releasing..."
            echo "$pids" | xargs kill -9 2>/dev/null || true
            sleep 1
        fi
    fi
}

wait_for_engine_ready() {
    local retries=30
    local delay=1
    local health_url="http://127.0.0.1:8765/health"

    for ((i=1; i<=retries; i++)); do
        if curl -sf --max-time 2 "$health_url" > /dev/null; then
            log_success "Engine health check passed"
            return 0
        fi
        sleep "$delay"
    done

    log_warn "Engine health check timed out; starting UI anyway"
    return 1
}

# Start the Python engine
start_engine() {
    log_info "Starting Python engine on http://127.0.0.1:8765..."
    cleanup_stale_engine_pid
    ensure_port_free
    cd "$ROOT_DIR/engine"
    uv run uvicorn solat_engine.main:app --host 127.0.0.1 --port 8765 --reload &
    ENGINE_PID=$!
    echo $ENGINE_PID > "$ROOT_DIR/.engine.pid"
    log_success "Engine started (PID: $ENGINE_PID)"
}

# Start the Tauri development server
start_ui() {
    log_info "Starting Tauri development server..."
    cd "$ROOT_DIR"
    wait_for_engine_ready || true
    pnpm --filter solat-desktop tauri dev
}

# Cleanup on exit
cleanup() {
    log_info "Shutting down..."

    if [ -f "$ROOT_DIR/.engine.pid" ]; then
        ENGINE_PID=$(cat "$ROOT_DIR/.engine.pid")
        if kill -0 "$ENGINE_PID" 2>/dev/null; then
            log_info "Stopping engine (PID: $ENGINE_PID)..."
            kill "$ENGINE_PID" 2>/dev/null || true
        fi
        rm -f "$ROOT_DIR/.engine.pid"
    fi

    log_success "Shutdown complete"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Main
main() {
    log_info "Starting SOLAT Development Environment"
    echo ""

    check_dependencies
    setup_engine
    setup_ui

    echo ""
    log_info "Starting services..."
    echo ""

    start_engine
    start_ui
}

main "$@"
