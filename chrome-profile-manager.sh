#!/bin/bash

# Chrome Profile Manager with CDP
# Manages Chrome profiles with remote debugging enabled

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILES_DIR="$SCRIPT_DIR/chrome-profiles"
PIDS_DIR="$SCRIPT_DIR/.pids"
CONFIG_FILE="$SCRIPT_DIR/profiles.json"

# Create necessary directories
mkdir -p "$PROFILES_DIR"
mkdir -p "$PIDS_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default Chrome path for Mac
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Function to display usage
usage() {
    echo "Usage: $0 {create|start|stop|list|status|remove} [profile-name] [options]"
    echo ""
    echo "Commands:"
    echo "  create <name> [port]     Create a new Chrome profile (default port: 9222)"
    echo "  start <name> [--headless]     Start Chrome with the specified profile"
    echo "  stop <name>              Stop Chrome instance for the profile"
    echo "  list                     List all profiles"
    echo "  status [name]            Show status of profile(s)"
    echo "  remove <name>            Remove a profile"
    echo ""
    echo "Examples:"
    echo "  $0 create profile1 9222"
    echo "  $0 start profile1"
    echo "  $0 stop profile1"
    echo "  $0 list"
    exit 1
}

# Function to create profile config
create_profile() {
    local profile_name=$1
    local specified_port=$2
    local profile_path="$PROFILES_DIR/$profile_name"
    
    if [ -d "$profile_path" ]; then
        echo -e "${RED}Profile '$profile_name' already exists${NC}"
        return 1
    fi

    # Get all used ports
    local used_ports=()
    if [ -d "$PROFILES_DIR" ]; then
        for config in "$PROFILES_DIR"/*/config.json; do
            if [ -f "$config" ]; then
                local p=$(grep -o '"port": [0-9]*' "$config" | head -1 | grep -o '[0-9]*')
                if [ -n "$p" ]; then
                    used_ports+=($p)
                fi
            fi
        done
    fi
    
    local port
    if [ -n "$specified_port" ]; then
        for p in "${used_ports[@]}"; do
            if [ "$p" == "$specified_port" ]; then
                echo -e "${RED}Port $specified_port is already in use by another profile${NC}"
                return 1
            fi
        done
        port=$specified_port
    else
        # Find next available port starting from 9222
        port=9222
        while true; do
            local found=0
            for p in "${used_ports[@]}"; do
                if [ "$p" == "$port" ]; then
                    found=1
                    break
                fi
            done
            if [ $found -eq 0 ]; then
                break
            fi
            ((port++))
        done
    fi
    
    mkdir -p "$profile_path"
    
    # Create profile config
    cat > "$profile_path/config.json" <<EOF
{
  "name": "$profile_name",
  "port": $port,
  "created": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
    
    echo -e "${GREEN}Profile '$profile_name' created successfully${NC}"
    echo "Profile directory: $profile_path"
    echo "CDP Port: $port"
}

# Function to start Chrome with profile
start_profile() {
    local profile_name=$1
    local headless_mode=$2 # "true" or "false"
    local profile_path="$PROFILES_DIR/$profile_name"
    local config_file="$profile_path/config.json"
    local pid_file="$PIDS_DIR/$profile_name.pid"
    
    if [ ! -d "$profile_path" ]; then
        echo -e "${RED}Profile '$profile_name' does not exist${NC}"
        return 1
    fi
    
    # Check if already running
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}Profile '$profile_name' is already running (PID: $pid)${NC}"
            return 0
        else
            rm "$pid_file"
        fi
    fi
    
    # Read port from config
    local port=$(grep -o '"port": [0-9]*' "$config_file" | grep -o '[0-9]*')
    
    echo "Starting Chrome with profile '$profile_name' on port $port..."
    
    # Start Chrome with remote debugging
    local chrome_args="--remote-debugging-port=$port --user-data-dir="$profile_path" --no-first-run --no-default-browser-check"
    if [ "$headless_mode" = "true" ]; then
        chrome_args="$chrome_args --headless=new"
    fi

    nohup "$CHROME_PATH" $chrome_args > "$profile_path/chrome.log" 2>&1 &
    
    local chrome_pid=$!
    echo $chrome_pid > "$pid_file"
    
    # Wait a moment for Chrome to start
    sleep 5
    
    # We assume Chrome started successfully if nohup didn't immediately fail.
    # The calling script (perplexity-automation-ax.js) will handle connection errors.
    echo -e "${GREEN}Chrome launch initiated for profile '$profile_name'${NC}"
    echo "PID: $chrome_pid (may not be the final Chrome process PID)"
    echo "CDP endpoint: http://localhost:$port"
    echo "WebSocket: ws://localhost:$port/devtools/browser"
    return 0 # Indicate success of launch initiation
}

# Function to stop Chrome profile
stop_profile() {
    local profile_name=$1
    local pid_file="$PIDS_DIR/$profile_name.pid"
    
    if [ ! -f "$pid_file" ]; then
        echo -e "${YELLOW}Profile '$profile_name' is not running${NC}"
        return 0
    fi
    
    local pid=$(cat "$pid_file")
    
    if ps -p $pid > /dev/null 2>&1; then
        echo "Stopping Chrome (PID: $pid)..."
        kill $pid
        
        # Wait for process to terminate
        local count=0
        while ps -p $pid > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            ((count++))
        done
        
        if ps -p $pid > /dev/null 2>&1; then
            echo "Force killing Chrome..."
            kill -9 $pid
        fi
        
        echo -e "${GREEN}Chrome stopped${NC}"
    else
        echo -e "${YELLOW}Process $pid not found${NC}"
    fi
    
    rm "$pid_file"
}

# Function to list all profiles
list_profiles() {
    echo "Available Chrome Profiles:"
    echo "----------------------------------------"
    
    if [ ! -d "$PROFILES_DIR" ] || [ -z "$(ls -A $PROFILES_DIR)" ]; then
        echo "No profiles found"
        return
    fi
    
    for profile_dir in "$PROFILES_DIR"/*; do
        if [ -d "$profile_dir" ]; then
            local profile_name=$(basename "$profile_dir")
            local config_file="$profile_dir/config.json"
            
            if [ -f "$config_file" ]; then
                local port=$(grep -o '"port": [0-9]*' "$config_file" | grep -o '[0-9]*')
                local status="Stopped"
                local pid_file="$PIDS_DIR/$profile_name.pid"
                
                if [ -f "$pid_file" ]; then
                    local pid=$(cat "$pid_file")
                    if ps -p $pid > /dev/null 2>&1; then
                        status="${GREEN}Running (PID: $pid)${NC}"
                    fi
                fi
                
                echo -e "  - $profile_name (Port: $port) - $status"
            fi
        fi
    done
}

# Function to show status
show_status() {
    local profile_name=$1
    
    if [ -n "$profile_name" ]; then
        local pid_file="$PIDS_DIR/$profile_name.pid"
        local profile_path="$PROFILES_DIR/$profile_name"
        local config_file="$profile_path/config.json"
        
        if [ ! -d "$profile_path" ]; then
            echo -e "${RED}Profile '$profile_name' does not exist${NC}"
            return 1
        fi
        
        local port=$(grep -o '"port": [0-9]*' "$config_file" | grep -o '[0-9]*')
        
        echo "Profile: $profile_name"
        echo "Port: $port"
        echo "Path: $profile_path"
        
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if ps -p $pid > /dev/null 2>&1; then
                echo -e "Status: ${GREEN}Running${NC}"
                echo "PID: $pid"
                echo "CDP: http://localhost:$port"
            else
                echo -e "Status: ${RED}Stopped (stale PID file)${NC}"
                rm "$pid_file"
            fi
        else
            echo -e "Status: ${RED}Stopped${NC}"
        fi
    else
        list_profiles
    fi
}

# Function to remove profile
remove_profile() {
    local profile_name=$1
    local profile_path="$PROFILES_DIR/$profile_name"
    
    if [ ! -d "$profile_path" ]; then
        echo -e "${RED}Profile '$profile_name' does not exist${NC}"
        return 1
    fi
    
    # Stop if running
    stop_profile "$profile_name"
    
    # Remove profile directory
    rm -rf "$profile_path"
    
    echo -e "${GREEN}Profile '$profile_name' removed${NC}"
}

# Main command handler
case "${1:-}" in
    create)
        if [ -z "$2" ]; then
            echo -e "${RED}Error: Profile name required${NC}"
            usage
        fi
        create_profile "$2" "$3"
        ;;
    start)
        if [ -z "$2" ]; then
            usage
        fi
        profile_name=$2
        headless_flag="false"
        for i in "${@:3}"; do
            if [ "$i" == "--headless" ]; then
                headless_flag="true"
                break
            fi
        done
        start_profile "$profile_name" "$headless_flag"
        ;;
    stop)
        if [ -z "$2" ]; then
            echo -e "${RED}Error: Profile name required${NC}"
            usage
        fi
        stop_profile "$2"
        ;;
    list)
        list_profiles
        ;;
    status)
        show_status "$2"
        ;;
    remove)
        if [ -z "$2" ]; then
            echo -e "${RED}Error: Profile name required${NC}"
            usage
        fi
        remove_profile "$2"
        ;;
    *)
        usage
        ;;
esac
