#!/bin/bash

# --- Configuration ---
PROJECT_NAME="litellm-proxy"
PORT=4000
CONFIG_FILE="litellm_config.yaml"
LOG_FILE="proxy.log"
MASTER_KEY=$(grep "master_key:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"' | tr -d "'")

# --- Colors for Output ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Helper Functions ---
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_env() {
    if [ ! -f .env ]; then
        log_warn ".env file not found. Creating a template..."
        echo "OLLAMA_API_BASE=http://127.0.0.1:11434" > .env
        echo "OPENAI_API_KEY=sk-..." >> .env
        echo "TAVILY_API_KEY=tvly-..." >> .env
        log_info "Please edit .env with your API keys."
    fi
}

check_ollama() {
    if ! pgrep -x "Ollama" > /dev/null; then
        log_warn "Ollama is not running. Local models will fail."
        log_info "Tip: On M4 Pro, ensure Ollama is installed to use Metal acceleration."
    else
        log_success "Ollama detected and running."
    fi
}

print_connection_info() {
    echo -e "\n${BOLD}--- Connection Details ---${NC}"
    echo -e "Base URL:   ${GREEN}http://localhost:$PORT${NC}"
    echo -e "API Key:    ${GREEN}$MASTER_KEY${NC}"
    echo -e "Logs:       ${YELLOW}$LOG_FILE${NC} (Check here for intercepted requests/responses)"
    echo -e "Example:    curl http://localhost:$PORT/v1/models -H \"Authorization: Bearer $MASTER_KEY\""
    echo -e "---------------------------\n"
}

# --- Main Commands ---

start_native() {
    check_env
    check_ollama
    
    # Check if port is already in use
    EXISTING_PID=$(lsof -ti :$PORT)
    if [ ! -z "$EXISTING_PID" ]; then
        log_error "Port $PORT is already in use by PID $EXISTING_PID. Run './manage.sh stop' first."
        exit 1
    fi

    # Load env vars reliably
    if [ -f .env ]; then
        set -a
        source .env
        set +a
    fi

    export CONFIG_FILE="$CONFIG_FILE"
    export PORT="$PORT"

    log_info "Scanning for Ollama models..."
    uv run python main.py --discover

    log_info "Starting LiteLLM Proxy on port $PORT (Native via uv)..."
    
    # Run in background
    PYTHONPATH=. nohup uv run python main.py > "$LOG_FILE" 2>&1 &
    
    # Wait for the service to actually start and bind to the port
    log_info "Waiting for service to bind to port $PORT..."
    COUNT=0
    while ! lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; do
        if [ $COUNT -gt 20 ]; then
            log_error "Timeout: Service failed to start on port $PORT. Check $LOG_FILE for details."
            exit 1
        fi
        sleep 1
        let COUNT=COUNT+1
    done

    # Get the actual PID listening on the port (uv might spawn child processes)
    ACTUAL_PID=$(lsof -ti :$PORT)
    echo $ACTUAL_PID > .proxy.pid
    
    log_success "LiteLLM Proxy is now ACTIVE on port $PORT."
    log_info "Listening Process PID: $ACTUAL_PID"
    
    log_info "Starting Frontend (Next.js) in background..."
    (cd frontend && nohup npm run dev > ../frontend.log 2>&1 &)
    log_success "Frontend is starting on http://localhost:3000"

    print_connection_info
}

start_docker() {
    check_env
    log_info "Starting LiteLLM Proxy via Docker Compose..."
    docker-compose up -d
    log_success "Docker containers started."
    print_connection_info
}

stop() {
    log_info "Stopping all services related to port $PORT..."
    
    # Stop Native by PID file
    if [ -f .proxy.pid ]; then
        PID=$(cat .proxy.pid)
        if ps -p $PID > /dev/null; then
            kill $PID && rm .proxy.pid
            log_success "Native proxy (PID $PID) terminated."
        else
            log_warn "PID file found but process $PID is already dead. Cleaning up."
            rm .proxy.pid
        fi
    fi
    
    # Force kill anything else on the port just in case
    REMAINING=$(lsof -ti :$PORT)
    if [ ! -z "$REMAINING" ]; then
        log_info "Cleaning up orphaned process $REMAINING on port $PORT..."
        kill -9 $REMAINING
        log_success "Port $PORT cleared."
    fi
    
    # Stop Docker
    if command -v docker-compose &> /dev/null && [ -f docker-compose.yml ]; then
        docker-compose down &> /dev/null
        log_success "Docker services stopped."
    fi
}

status() {
    echo -e "\n--- ${BLUE}Service Status Report${NC} ---"
    
    # Port Check (The source of truth)
    LISTENING_PID=$(lsof -ti :$PORT)
    if [ ! -z "$LISTENING_PID" ]; then
        echo -e "Port $PORT:      ${GREEN}LISTENING${NC} (PID: $LISTENING_PID)"
        
        # Check if it's our native proxy or docker
        if [ -f .proxy.pid ] && [ "$LISTENING_PID" == "$(cat .proxy.pid)" ]; then
            echo -e "Mode:           ${BOLD}Native (uv)${NC}"
        else
            echo -e "Mode:           ${BOLD}Docker or Other${NC}"
        fi
        
        print_connection_info
    else
        echo -e "Port $PORT:      ${RED}NOT LISTENING${NC}"
        log_warn "Service is not running."
    fi
    
    # Docker Check
    if command -v docker &> /dev/null; then
        DOCKER_RUNNING=$(docker ps --filter "name=litellm-proxy" --format "{{.Status}}")
        if [ ! -z "$DOCKER_RUNNING" ]; then
            echo -e "Docker Container: ${GREEN}$DOCKER_RUNNING${NC}"
        fi
    fi
    echo ""
}

# --- CLI Router ---

case "$1" in
    start)
        start_native
        ;;
    docker)
        start_docker
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 2
        start_native
        ;;
    status)
        status
        ;;
    logs)
        log_info "Tailing proxy logs (CTRL+C to exit)..."
        tail -f "$LOG_FILE"
        ;;
    view)
        log_info "Launching Visually Friendly Payload Viewer..."
        uv run python view_payloads.py
        ;;
    test)
        log_info "Running internal logic tests..."
        PYTHONPATH=. uv run pytest tests/test_hooks.py
        ;;
    help|*)
        echo -e "${BOLD}LiteLLM Proxy Manager${NC}"
        echo "Usage: $0 {start|docker|stop|restart|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start    : [RECOMMENDED] Start natively using 'uv'. Optimized for M4 Pro."
        echo "  docker   : Start using Docker Compose."
        echo "  stop     : Stop any process running on port $PORT."
        echo "  restart  : Stop and then start natively."
        echo "  status   : Verify PID, Port, and show connection credentials."
        echo "  logs     : View the live log stream (includes plugin interceptions)."
        echo "  view     : [NEW] Visually friendly viewer for detailed request/response payloads."
        echo "  test     : Run pytest on the custom hook logic."
        ;;
esac
