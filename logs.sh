#!/bin/bash

################################################################################
# ISP App Log Viewer
# Stream and view Django/Gunicorn application logs
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

SERVICE_NAME="ssm-api"
APP_DIR="/opt/ssm_api"
LOG_DIR="/var/log/ssm_api"
GUNICORN_ACCESS_LOG="$LOG_DIR/gunicorn/access.log"
GUNICORN_ERROR_LOG="$LOG_DIR/gunicorn/error.log"

print_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${WHITE}          ISP Application Log Viewer                      ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if service exists
check_service() {
    if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
        print_error "Service '${SERVICE_NAME}' not found!"
        print_info "Make sure you've run the setup script first."
        exit 1
    fi
}

# Show service status
show_status() {
    print_header
    echo -e "${MAGENTA}=== Service Status ===${NC}\n"

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service is running"
    else
        print_warning "Service is not running"
    fi

    echo ""
    systemctl status "$SERVICE_NAME" --no-pager | head -n 20
    echo ""
}

# Stream live Gunicorn logs
stream_logs() {
    print_header
    echo -e "${MAGENTA}=== Live Gunicorn Logs (Press Ctrl+C to exit) ===${NC}\n"

    # Check which log files exist
    local has_access=false
    local has_error=false

    if [ -f "$GUNICORN_ACCESS_LOG" ]; then
        has_access=true
        print_success "Access log found: $GUNICORN_ACCESS_LOG"
    fi

    if [ -f "$GUNICORN_ERROR_LOG" ]; then
        has_error=true
        print_success "Error log found: $GUNICORN_ERROR_LOG"
    fi

    if [ "$has_access" = false ] && [ "$has_error" = false ]; then
        print_error "No Gunicorn log files found!"
        print_info "Expected locations:"
        echo "  - $GUNICORN_ACCESS_LOG"
        echo "  - $GUNICORN_ERROR_LOG"
        echo ""
        print_warning "Falling back to systemd journal logs..."
        echo ""
        sudo journalctl -u "$SERVICE_NAME" -f --no-pager
        return
    fi

    echo ""
    print_info "Following Gunicorn logs (both access and error)"
    print_info "Access log: HTTP requests (GET, POST, etc.)"
    print_info "Error log: Application errors, exceptions, Django output"
    echo ""

    # Follow both files simultaneously with color coding
    if [ "$has_access" = true ] && [ "$has_error" = true ]; then
        sudo tail -f "$GUNICORN_ACCESS_LOG" "$GUNICORN_ERROR_LOG" 2>/dev/null | sed \
            -e "s/\(ERROR\|CRITICAL\|Exception\|Traceback\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g" \
            -e "s/\(WARNING\|WARN\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
            -e "s/\(INFO\)/$(printf '\033[1;36m')\1$(printf '\033[0m')/g" \
            -e "s/\(GET\|POST\|PUT\|DELETE\|PATCH\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 200\|\" 201\|\" 204\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 400\|\" 401\|\" 403\|\" 404\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 500\|\" 502\|\" 503\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g"
    elif [ "$has_access" = true ]; then
        sudo tail -f "$GUNICORN_ACCESS_LOG" 2>/dev/null | sed \
            -e "s/\(GET\|POST\|PUT\|DELETE\|PATCH\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 200\|\" 201\|\" 204\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 400\|\" 401\|\" 403\|\" 404\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
            -e "s/\(\" 500\|\" 502\|\" 503\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g"
    else
        sudo tail -f "$GUNICORN_ERROR_LOG" 2>/dev/null | sed \
            -e "s/\(ERROR\|CRITICAL\|Exception\|Traceback\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g" \
            -e "s/\(WARNING\|WARN\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
            -e "s/\(INFO\)/$(printf '\033[1;36m')\1$(printf '\033[0m')/g"
    fi
}

# Show recent logs
show_recent() {
    local lines=${1:-100}

    print_header
    echo -e "${MAGENTA}=== Recent Logs (Last $lines lines) ===${NC}\n"

    sudo journalctl -u "$SERVICE_NAME" -n "$lines" --no-pager

    echo ""
    print_info "Use 'logs.sh tail <number>' to show more/fewer lines"
}

# Show logs since a time period
show_since() {
    local period=${1:-"1 hour ago"}

    print_header
    echo -e "${MAGENTA}=== Logs Since: $period ===${NC}\n"

    sudo journalctl -u "$SERVICE_NAME" --since "$period" --no-pager

    echo ""
}

# Show error logs only
show_errors() {
    local lines=${1:-50}

    print_header
    echo -e "${MAGENTA}=== Error Logs (Last $lines errors) ===${NC}\n"

    sudo journalctl -u "$SERVICE_NAME" -p err -n "$lines" --no-pager

    echo ""
}

# Show logs with grep filter
show_filtered() {
    local filter=$1
    local lines=${2:-100}

    print_header
    echo -e "${MAGENTA}=== Filtered Logs (Pattern: $filter) ===${NC}\n"

    sudo journalctl -u "$SERVICE_NAME" -n "$lines" --no-pager | grep --color=always -i "$filter"

    echo ""
}

# Export logs to file
export_logs() {
    local output_file=${1:-"ssm-api-logs-$(date +%Y%m%d-%H%M%S).log"}

    print_header
    echo -e "${MAGENTA}=== Export Logs ===${NC}\n"

    print_info "Exporting logs to: $output_file"

    sudo journalctl -u "$SERVICE_NAME" --no-pager > "$output_file"

    if [ $? -eq 0 ]; then
        print_success "Logs exported successfully!"
        print_info "File: $(pwd)/$output_file"
        print_info "Size: $(du -h "$output_file" | cut -f1)"
    else
        print_error "Failed to export logs"
    fi

    echo ""
}

# Show Django application logs from file (if exists)
show_django_logs() {
    print_header
    echo -e "${MAGENTA}=== Django Application Logs ===${NC}\n"

    if [ -d "$LOG_DIR" ]; then
        print_info "Log directory: $LOG_DIR"
        echo ""

        # List log files
        if ls -lh "$LOG_DIR"/*.log 2>/dev/null; then
            echo ""
            read -p "Enter log file name to view (or press Enter to skip): " logfile

            if [ -n "$logfile" ]; then
                if [ -f "$LOG_DIR/$logfile" ]; then
                    echo ""
                    print_info "Showing: $LOG_DIR/$logfile"
                    echo ""
                    sudo tail -f "$LOG_DIR/$logfile"
                else
                    print_error "File not found: $LOG_DIR/$logfile"
                fi
            fi
        else
            print_warning "No log files found in $LOG_DIR"
        fi
    else
        print_warning "Django log directory not found: $LOG_DIR"
        print_info "Application logs are in systemd journal only"
    fi

    echo ""
}

# Interactive menu
show_menu() {
    while true; do
        print_header
        echo -e "${MAGENTA}=== Log Viewer Menu ===${NC}\n"
        echo -e "${CYAN}1.${NC} Stream Live Logs (Follow)"
        echo -e "${CYAN}2.${NC} Show Recent Logs (Last 100 lines)"
        echo -e "${CYAN}3.${NC} Show Service Status"
        echo -e "${CYAN}4.${NC} Show Error Logs Only"
        echo -e "${CYAN}5.${NC} Show Logs Since (time period)"
        echo -e "${CYAN}6.${NC} Search Logs (grep filter)"
        echo -e "${CYAN}7.${NC} Export Logs to File"
        echo -e "${CYAN}8.${NC} Show Django App Logs (from file)"
        echo -e "${CYAN}9.${NC} Exit"
        echo ""
        read -p "Choose an option: " choice

        case $choice in
            1)
                stream_logs
                ;;
            2)
                read -p "Number of lines to show [100]: " lines
                lines=${lines:-100}
                show_recent "$lines"
                read -p "Press Enter to continue..."
                ;;
            3)
                show_status
                read -p "Press Enter to continue..."
                ;;
            4)
                read -p "Number of error lines to show [50]: " lines
                lines=${lines:-50}
                show_errors "$lines"
                read -p "Press Enter to continue..."
                ;;
            5)
                echo ""
                echo "Examples: '1 hour ago', '30 minutes ago', '2 days ago', 'today'"
                read -p "Enter time period [1 hour ago]: " period
                period=${period:-"1 hour ago"}
                show_since "$period"
                read -p "Press Enter to continue..."
                ;;
            6)
                read -p "Enter search pattern: " pattern
                if [ -n "$pattern" ]; then
                    read -p "Number of lines to search [100]: " lines
                    lines=${lines:-100}
                    show_filtered "$pattern" "$lines"
                    read -p "Press Enter to continue..."
                fi
                ;;
            7)
                read -p "Output filename [auto-generated]: " filename
                export_logs "$filename"
                read -p "Press Enter to continue..."
                ;;
            8)
                show_django_logs
                read -p "Press Enter to continue..."
                ;;
            9)
                print_success "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid option!"
                sleep 1
                ;;
        esac
    done
}

# Main script
check_service

# Parse command line arguments
case "${1:-follow}" in
    follow|stream|live)
        stream_logs
        ;;
    access)
        # Show only access logs (HTTP requests)
        if [ -f "$GUNICORN_ACCESS_LOG" ]; then
            print_header
            echo -e "${MAGENTA}=== Gunicorn Access Log (HTTP Requests) ===${NC}\n"
            print_info "Following: $GUNICORN_ACCESS_LOG"
            echo ""
            sudo tail -f "$GUNICORN_ACCESS_LOG" | sed \
                -e "s/\(GET\|POST\|PUT\|DELETE\|PATCH\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
                -e "s/\(\" 200\|\" 201\|\" 204\)/$(printf '\033[1;32m')\1$(printf '\033[0m')/g" \
                -e "s/\(\" 400\|\" 401\|\" 403\|\" 404\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
                -e "s/\(\" 500\|\" 502\|\" 503\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g"
        else
            print_error "Access log not found: $GUNICORN_ACCESS_LOG"
            exit 1
        fi
        ;;
    error)
        # Show only error logs
        if [ -f "$GUNICORN_ERROR_LOG" ]; then
            print_header
            echo -e "${MAGENTA}=== Gunicorn Error Log (Errors & Django Output) ===${NC}\n"
            print_info "Following: $GUNICORN_ERROR_LOG"
            echo ""
            sudo tail -f "$GUNICORN_ERROR_LOG" | sed \
                -e "s/\(ERROR\|CRITICAL\|Exception\|Traceback\)/$(printf '\033[1;31m')\1$(printf '\033[0m')/g" \
                -e "s/\(WARNING\|WARN\)/$(printf '\033[1;33m')\1$(printf '\033[0m')/g" \
                -e "s/\(INFO\)/$(printf '\033[1;36m')\1$(printf '\033[0m')/g"
        else
            print_error "Error log not found: $GUNICORN_ERROR_LOG"
            exit 1
        fi
        ;;
    tail|recent)
        show_recent "${2:-100}"
        ;;
    status)
        show_status
        read -p "Press Enter to continue..."
        ;;
    errors)
        show_errors "${2:-50}"
        ;;
    since)
        show_since "${2:-1 hour ago}"
        ;;
    grep|search|filter)
        if [ -z "$2" ]; then
            print_error "Usage: $0 grep <pattern> [lines]"
            exit 1
        fi
        show_filtered "$2" "${3:-100}"
        ;;
    export)
        export_logs "$2"
        ;;
    django)
        show_django_logs
        ;;
    menu)
        show_menu
        ;;
    help|--help|-h)
        print_header
        echo -e "${YELLOW}Usage:${NC}"
        echo "  $0                      - Stream live Gunicorn logs (default)"
        echo "  $0 follow               - Stream both access & error logs"
        echo "  $0 access               - Stream only access logs (HTTP requests)"
        echo "  $0 error                - Stream only error logs (errors & Django output)"
        echo "  $0 tail [lines]         - Show recent systemd logs (default: 100 lines)"
        echo "  $0 status               - Show service status"
        echo "  $0 errors [lines]       - Show error logs only (default: 50 lines)"
        echo "  $0 since <period>       - Show logs since time period"
        echo "  $0 grep <pattern> [lines] - Search logs for pattern"
        echo "  $0 export [filename]    - Export logs to file"
        echo "  $0 menu                 - Interactive menu"
        echo ""
        echo -e "${YELLOW}Examples:${NC}"
        echo "  $0                      # Stream all Gunicorn logs (default)"
        echo "  $0 follow               # Same as above"
        echo "  $0 access               # Only HTTP requests"
        echo "  $0 error                # Only errors and Django output"
        echo "  $0 grep 'ERROR' 500     # Search for errors"
        echo "  $0 since '1 hour ago'   # Logs from last hour"
        echo ""
        echo -e "${YELLOW}Gunicorn Log Files:${NC}"
        echo "  Access: $GUNICORN_ACCESS_LOG"
        echo "  Error:  $GUNICORN_ERROR_LOG"
        echo ""
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac