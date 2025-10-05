#!/bin/bash

# =============================================================================
# Advanced Network & Firewall Manager
# Comprehensive IP and firewall management with GCP-like features
# Features: Port management, IP configuration, network diagnostics, NAT/forwarding
# =============================================================================

set -e

# Colors for output (matching your setup.sh style)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
DEFAULT_PORT="8080"
DEFAULT_PROTOCOL="tcp"
DEFAULT_SOURCE="any"
DEFAULT_ACTION="allow"

# IP Management defaults
CONFIG_DIR="/etc/network-manager"
BACKUP_DIR="$CONFIG_DIR/backups"
IP_CONFIG_FILE="$CONFIG_DIR/ip-config.conf"
STATIC_IP_FILE="/etc/netplan/99-static-ip.yaml"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${CYAN}=== $1 ===${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_ufw() {
    if ! command -v ufw &> /dev/null; then
        print_error "UFW is not installed. Please install it first:"
        echo "sudo apt install ufw"
        exit 1
    fi
}

check_dependencies() {
    local missing=()
    
    command -v curl &> /dev/null || missing+=("curl")
    command -v dig &> /dev/null || missing+=("dnsutils")
    command -v nmap &> /dev/null || missing+=("nmap")
    command -v netstat &> /dev/null || missing+=("net-tools")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        print_warning "Missing optional dependencies: ${missing[*]}"
        print_status "Install with: sudo apt install ${missing[*]}"
    fi
}

init_config_dirs() {
    mkdir -p "$CONFIG_DIR" "$BACKUP_DIR"
    chmod 700 "$CONFIG_DIR" "$BACKUP_DIR"
}

show_current_rules() {
    print_header "Current UFW Rules"
    echo ""
    ufw status numbered
    echo ""
}

show_help() {
    cat << EOF
${CYAN}UFW Port Manager${NC}

${YELLOW}USAGE:${NC}
    $0 [OPTIONS]

${YELLOW}OPTIONS:${NC}
    ${GREEN}-h, --help${NC}         Show this help message
    ${GREEN}-s, --status${NC}       Show current UFW status and rules
    ${GREEN}-a, --add${NC}          Add a new rule (interactive)
    ${GREEN}-r, --remove${NC}       Remove a rule (interactive)
    ${GREEN}-q, --quick${NC}        Quick mode with defaults

${YELLOW}EXAMPLES:${NC}
    # Interactive mode (default)
    sudo $0

    # Show status only
    sudo $0 --status

    # Quick mode with prompts
    sudo $0 --quick

${YELLOW}COMMON PORTS:${NC}
    ${GREEN}22${NC}      SSH
    ${GREEN}80${NC}      HTTP
    ${GREEN}443${NC}     HTTPS
    ${GREEN}3306${NC}    MySQL
    ${GREEN}5432${NC}    PostgreSQL
    ${GREEN}6379${NC}    Redis
    ${GREEN}8080${NC}    Alternative HTTP
    ${GREEN}1194${NC}    OpenVPN
    ${GREEN}1812/1813${NC} RADIUS

EOF
}

get_user_input() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    
    if [[ -n "$default" ]]; then
        echo -n -e "${BLUE}$prompt${NC} [${GREEN}$default${NC}]: "
    else
        echo -n -e "${BLUE}$prompt${NC}: "
    fi
    
    read -r input
    if [[ -z "$input" && -n "$default" ]]; then
        input="$default"
    fi
    
    eval "$var_name='$input'"
}

validate_port() {
    local port="$1"
    if [[ ! "$port" =~ ^[0-9]+$ ]] || [[ "$port" -lt 1 ]] || [[ "$port" -gt 65535 ]]; then
        return 1
    fi
    return 0
}

validate_protocol() {
    local protocol="$1"
    if [[ "$protocol" != "tcp" && "$protocol" != "udp" && "$protocol" != "any" ]]; then
        return 1
    fi
    return 0
}

add_firewall_rule() {
    print_header "Add Firewall Rule"
    
    # Get port
    while true; do
        get_user_input "Enter port number" "$DEFAULT_PORT" "port"
        if validate_port "$port"; then
            break
        else
            print_error "Invalid port number. Please enter a number between 1-65535."
        fi
    done
    
    # Get protocol
    while true; do
        get_user_input "Enter protocol (tcp/udp/any)" "$DEFAULT_PROTOCOL" "protocol"
        if validate_protocol "$protocol"; then
            break
        else
            print_error "Invalid protocol. Please enter 'tcp', 'udp', or 'any'."
        fi
    done
    
    # Get source
    echo ""
    echo "Source options:"
    echo "  any           - Allow from anywhere"
    echo "  192.168.1.0/24 - Allow from specific subnet"
    echo "  192.168.1.10  - Allow from specific IP"
    echo ""
    get_user_input "Enter source IP/subnet" "$DEFAULT_SOURCE" "source"
    
    # Get action
    echo ""
    echo "Action options:"
    echo "  allow  - Allow traffic"
    echo "  deny   - Deny traffic"
    echo ""
    get_user_input "Enter action (allow/deny)" "$DEFAULT_ACTION" "action"
    
    # Construct UFW command
    if [[ "$source" == "any" ]]; then
        if [[ "$protocol" == "any" ]]; then
            ufw_cmd="ufw $action $port"
        else
            ufw_cmd="ufw $action $port/$protocol"
        fi
    else
        if [[ "$protocol" == "any" ]]; then
            ufw_cmd="ufw $action from $source to any port $port"
        else
            ufw_cmd="ufw $action from $source to any port $port proto $protocol"
        fi
    fi
    
    # Show summary and confirm
    echo ""
    print_header "Rule Summary"
    echo "Port: $port"
    echo "Protocol: $protocol"
    echo "Source: $source"
    echo "Action: $action"
    echo "Command: $ufw_cmd"
    echo ""
    
    read -p "Apply this rule? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Applying firewall rule..."
        if eval "$ufw_cmd"; then
            print_success "Rule added successfully!"
        else
            print_error "Failed to add rule"
            return 1
        fi
    else
        print_warning "Rule cancelled"
    fi
}

remove_firewall_rule() {
    print_header "Remove Firewall Rule"
    
    # Show current rules
    show_current_rules
    
    echo "Enter the rule number to delete, or 'q' to quit:"
    read -r rule_number
    
    if [[ "$rule_number" == "q" ]]; then
        print_warning "Cancelled"
        return 0
    fi
    
    if [[ "$rule_number" =~ ^[0-9]+$ ]]; then
        read -p "Delete rule #$rule_number? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_status "Removing rule #$rule_number..."
            if ufw --force delete "$rule_number"; then
                print_success "Rule removed successfully!"
            else
                print_error "Failed to remove rule"
                return 1
            fi
        else
            print_warning "Cancelled"
        fi
    else
        print_error "Invalid rule number"
        return 1
    fi
}

quick_mode() {
    print_header "Quick Port Configuration"
    
    # Common service shortcuts
    echo "Quick setup options:"
    echo "1) Web Server (80/tcp, 443/tcp)"
    echo "2) SSH (22/tcp)"
    echo "3) Database (3306/tcp MySQL, 5432/tcp PostgreSQL)"
    echo "4) OpenVPN (1194/udp)"
    echo "5) Custom port"
    echo "6) Cancel"
    echo ""
    
    get_user_input "Select option" "5" "choice"
    
    case "$choice" in
        1)
            print_status "Opening web server ports..."
            ufw allow 80/tcp
            ufw allow 443/tcp
            print_success "Web server ports opened (80/tcp, 443/tcp)"
            ;;
        2)
            print_status "Opening SSH port..."
            ufw allow 22/tcp
            print_success "SSH port opened (22/tcp)"
            ;;
        3)
            echo "Database options:"
            echo "a) MySQL (3306/tcp)"
            echo "b) PostgreSQL (5432/tcp)"
            echo "c) Both"
            get_user_input "Choose database" "c" "db_choice"
            
            case "$db_choice" in
                a) ufw allow 3306/tcp; print_success "MySQL port opened (3306/tcp)" ;;
                b) ufw allow 5432/tcp; print_success "PostgreSQL port opened (5432/tcp)" ;;
                c) ufw allow 3306/tcp; ufw allow 5432/tcp; print_success "Database ports opened (3306/tcp, 5432/tcp)" ;;
                *) print_error "Invalid choice" ;;
            esac
            ;;
        4)
            print_status "Opening OpenVPN port..."
            ufw allow 1194/udp
            print_success "OpenVPN port opened (1194/udp)"
            ;;
        5)
            add_firewall_rule
            ;;
        6)
            print_warning "Cancelled"
            ;;
        *)
            print_error "Invalid choice"
            ;;
    esac
}

# =============================================================================
# IP MANAGEMENT FUNCTIONS
# =============================================================================

get_public_ip() {
    local ip_services=(
        "https://ifconfig.me"
        "https://ipinfo.io/ip"
        "https://api.ipify.org"
        "https://checkip.amazonaws.com"
    )
    
    for service in "${ip_services[@]}"; do
        if command -v curl &> /dev/null; then
            if ip=$(curl -s --connect-timeout 5 "$service" 2>/dev/null); then
                if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                    echo "$ip"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

get_local_ip() {
    ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}'
}

get_network_interface() {
    ip route | awk '/default/ {print $5; exit}'
}

show_network_info() {
    print_header "Network Information"
    
    echo "Hostname: $(hostname)"
    echo "Local IP: $(get_local_ip)"
    
    print_status "Getting public IP..."
    if public_ip=$(get_public_ip); then
        echo "Public IP: $public_ip"
        
        # Check if we can ping our own public IP
        print_status "Testing public IP reachability..."
        if ping -c 1 -W 3 "$public_ip" &>/dev/null; then
            print_success "Public IP is reachable"
        else
            print_warning "Public IP not reachable (may be behind NAT/firewall)"
        fi
    else
        print_warning "Could not determine public IP"
    fi
    
    echo "Primary Interface: $(get_network_interface)"
    echo ""
    
    print_status "Network Interfaces:"
    ip addr show | awk '/^[0-9]+:/ {print $2} /inet / {print "  " $2}'
    echo ""
    
    print_status "Routing Table:"
    ip route | head -10
    echo ""
}

configure_static_ip() {
    print_header "Configure Static IP"
    
    local interface current_ip gateway dns static_ip subnet
    interface=$(get_network_interface)
    current_ip=$(get_local_ip)
    
    if [[ -z "$interface" ]]; then
        print_error "Could not detect network interface"
        return 1
    fi
    
    echo "Current configuration:"
    echo "Interface: $interface"
    echo "Current IP: $current_ip"
    echo ""
    
    get_user_input "Enter static IP address" "$current_ip" "static_ip"
    get_user_input "Enter subnet mask (CIDR)" "24" "subnet"
    get_user_input "Enter gateway IP" "$(ip route | awk '/default/ {print $3; exit}')" "gateway"
    get_user_input "Enter DNS servers (comma-separated)" "8.8.8.8,8.8.4.4" "dns"
    
    cat > "$STATIC_IP_FILE" << EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    $interface:
      dhcp4: false
      addresses:
        - $static_ip/$subnet
      gateway4: $gateway
      nameservers:
        addresses: [$(echo "$dns" | sed 's/,/, /g')]
EOF
    
    echo ""
    print_status "Configuration preview:"
    cat "$STATIC_IP_FILE"
    echo ""
    
    read -p "Apply this configuration? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ -f /etc/netplan/50-cloud-init.yaml ]]; then
            cp /etc/netplan/50-cloud-init.yaml "$BACKUP_DIR/netplan-$(date +%Y%m%d-%H%M%S).yaml"
        fi
        
        print_status "Applying network configuration..."
        if netplan apply; then
            print_success "Static IP configured successfully!"
            print_warning "You may need to reconnect to SSH if IP changed"
            
            echo "Static IP: $static_ip/$subnet" > "$IP_CONFIG_FILE"
            echo "Gateway: $gateway" >> "$IP_CONFIG_FILE"
            echo "DNS: $dns" >> "$IP_CONFIG_FILE"
            echo "Applied: $(date)" >> "$IP_CONFIG_FILE"
        else
            print_error "Failed to apply network configuration"
            rm -f "$STATIC_IP_FILE"
            return 1
        fi
    else
        print_warning "Configuration cancelled"
        rm -f "$STATIC_IP_FILE"
    fi
}

restore_dhcp() {
    print_header "Restore DHCP Configuration"
    
    print_warning "This will restore automatic IP configuration (DHCP)"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ -f "$STATIC_IP_FILE" ]]; then
            mv "$STATIC_IP_FILE" "$BACKUP_DIR/static-ip-removed-$(date +%Y%m%d-%H%M%S).yaml"
        fi
        
        print_status "Applying DHCP configuration..."
        if netplan apply; then
            print_success "DHCP restored successfully!"
            rm -f "$IP_CONFIG_FILE"
        else
            print_error "Failed to restore DHCP"
            return 1
        fi
    else
        print_warning "Operation cancelled"
    fi
}

network_diagnostics() {
    print_header "Network Diagnostics"
    
    echo "1) Ping test"
    echo "2) Port scan (local)"
    echo "3) DNS lookup"
    echo "4) Connection test"
    echo "5) Network speed test"
    echo "6) Full diagnostic report"
    echo "7) Back to main menu"
    echo ""
    
    get_user_input "Select diagnostic" "1" "diag_choice"
    
    case "$diag_choice" in
        1) ping_test ;;
        2) port_scan ;;
        3) dns_lookup ;;
        4) connection_test ;;
        5) speed_test ;;
        6) full_diagnostic ;;
        7) return 0 ;;
        *) print_error "Invalid choice" ;;
    esac
}

ping_test() {
    print_header "Ping Test"
    
    echo "Common targets:"
    echo "1) Google DNS (8.8.8.8)"
    echo "2) Cloudflare DNS (1.1.1.1)"
    echo "3) Your gateway"
    echo "4) Your public IP"
    echo "5) Custom target"
    echo ""
    
    get_user_input "Select target" "1" "ping_choice"
    
    local target
    case "$ping_choice" in
        1) target="8.8.8.8" ;;
        2) target="1.1.1.1" ;;
        3) target=$(ip route | awk '/default/ {print $3; exit}') ;;
        4) target=$(get_public_ip) ;;
        5) get_user_input "Enter IP or hostname" "google.com" "target" ;;
        *) print_error "Invalid choice"; return 1 ;;
    esac
    
    if [[ -z "$target" ]]; then
        print_error "Could not determine target"
        return 1
    fi
    
    print_status "Pinging $target (Ctrl+C to stop)..."
    ping -c 4 "$target"
}

port_scan() {
    print_header "Port Scanner"
    
    local scan_target port_range
    get_user_input "Enter target IP" "$(get_local_ip)" "scan_target"
    get_user_input "Enter port range (e.g., 1-1000, 80,443,22)" "1-1000" "port_range"
    
    if command -v nmap &> /dev/null; then
        print_status "Scanning $scan_target ports $port_range..."
        nmap -p "$port_range" "$scan_target"
    else
        print_error "nmap not found. Install with: apt install nmap"
        print_status "Using basic connectivity test instead..."
        
        # Basic port test for common ports
        if [[ "$port_range" == "1-1000" ]]; then
            local common_ports=(22 23 25 53 80 110 443 993 995 1194 3306 5432 8080)
            for port in "${common_ports[@]}"; do
                if timeout 1 bash -c "</dev/tcp/$scan_target/$port" 2>/dev/null; then
                    echo "Port $port: Open"
                fi
            done
        fi
    fi
}

dns_lookup() {
    print_header "DNS Lookup"
    
    local domain
    get_user_input "Enter domain name" "google.com" "domain"
    
    if command -v dig &> /dev/null; then
        print_status "DNS lookup for $domain:"
        dig +short "$domain"
        echo ""
        print_status "Detailed DNS info:"
        dig "$domain"
    else
        print_status "Using nslookup:"
        nslookup "$domain"
    fi
}

connection_test() {
    print_header "Connection Test"
    
    local conn_target host port
    get_user_input "Enter host:port to test" "google.com:80" "conn_target"
    
    host=${conn_target%:*}
    port=${conn_target#*:}
    
    print_status "Testing connection to $host:$port..."
    
    if timeout 5 bash -c "</dev/tcp/$host/$port" 2>/dev/null; then
        print_success "Connection successful!"
    else
        print_error "Connection failed"
    fi
}

speed_test() {
    print_header "Network Speed Test"
    
    if command -v speedtest-cli &> /dev/null; then
        print_status "Running speed test..."
        speedtest-cli
    else
        print_warning "speedtest-cli not found (pip install speedtest-cli)"
        print_status "Running basic download test..."
        curl -o /dev/null -s -w "Downloaded at %{speed_download} bytes/sec\n" \
            "http://speedtest.ftp.otenet.gr/files/test10Mb.db" || \
            print_error "Speed test failed"
    fi
}

full_diagnostic() {
    print_header "Full Network Diagnostic Report"
    
    echo "=== System Info ==="
    echo "Hostname: $(hostname)"
    echo "Date: $(date)"
    echo ""
    
    echo "=== Network Configuration ==="
    show_network_info
    
    echo "=== Connectivity Tests ==="
    print_status "Testing Google DNS..."
    ping -c 2 8.8.8.8 | tail -2
    
    echo ""
    echo "=== UFW Status ==="
    ufw status verbose
    
    echo ""
    echo "=== Open Ports ==="
    if command -v netstat &> /dev/null; then
        netstat -tlnp | head -20
    else
        ss -tlnp | head -20
    fi
    
    print_success "Diagnostic complete"
}

preserve_ip_settings() {
    print_header "Preserve IP Settings"
    
    local backup_name="ip-backup-$(date +%Y%m%d-%H%M%S)"
    local backup_file="$BACKUP_DIR/$backup_name.tar.gz"
    
    print_status "Creating IP settings backup..."
    
    # Create backup archive
    tar -czf "$backup_file" -C / \
        etc/netplan/ \
        etc/systemd/network/ \
        etc/network/interfaces 2>/dev/null || true
    
    # Save current network info
    {
        echo "# IP Settings Backup - $(date)"
        echo "# Hostname: $(hostname)"
        echo "# Local IP: $(get_local_ip)"
        echo "# Public IP: $(get_public_ip 2>/dev/null || echo 'N/A')"
        echo "# Interface: $(get_network_interface)"
        echo ""
        echo "# Network Configuration:"
        ip addr show
        echo ""
        echo "# Routing Table:"
        ip route
    } > "$BACKUP_DIR/$backup_name.info"
    
    print_success "IP settings preserved to:"
    echo "  Backup: $backup_file"
    echo "  Info: $BACKUP_DIR/$backup_name.info"
    
    echo ""
    print_status "Available backups:"
    ls -la "$BACKUP_DIR"/ip-backup-*.tar.gz 2>/dev/null | tail -5 || echo "No backups found"
}

# =============================================================================
# ADVANCED FIREWALL FEATURES
# =============================================================================

advanced_firewall_menu() {
    while true; do
        print_header "Advanced Firewall Features"
        echo ""
        echo "1) Rate limiting (DDoS protection)"
        echo "2) Application profiles"
        echo "3) Logging configuration"
        echo "4) Backup/Restore firewall rules"
        echo "5) NAT and Port Forwarding"
        echo "6) Back to main menu"
        echo ""
        
        get_user_input "Select option" "1" "adv_choice"
        
        case "$adv_choice" in
            1) configure_rate_limiting ;;
            2) manage_app_profiles ;;
            3) configure_logging ;;
            4) backup_restore_rules ;;
            5) nat_port_forwarding_menu ;;
            6) return 0 ;;
            *) print_error "Invalid choice" ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..." -r
        clear
    done
}

configure_rate_limiting() {
    print_header "Rate Limiting Configuration"
    
    echo "Rate limiting helps protect against DDoS attacks."
    echo "This will configure UFW to limit connections per IP."
    echo ""
    
    local port protocol rate
    get_user_input "Enter port to protect" "22" "port"
    get_user_input "Enter protocol (tcp/udp)" "tcp" "protocol"
    get_user_input "Enter rate limit (connections/time, e.g., 6/minute)" "6/minute" "rate"
    
    print_status "Configuring rate limiting for port $port/$protocol..."
    
    # Remove existing rule if present
    ufw --force delete allow $port/$protocol 2>/dev/null || true
    
    # Add rate limited rule
    if ufw limit $port/$protocol comment "Rate limited $rate"; then
        print_success "Rate limiting configured for port $port/$protocol ($rate)"
        echo "This will allow $rate per IP address."
    else
        print_error "Failed to configure rate limiting"
    fi
}

manage_app_profiles() {
    print_header "Application Profiles"
    
    echo "Available UFW application profiles:"
    ufw app list
    
    echo ""
    echo "1) Enable application profile"
    echo "2) Disable application profile"
    echo "3) Show profile info"
    echo "4) Back"
    echo ""
    
    get_user_input "Select option" "1" "app_choice"
    
    case "$app_choice" in
        1)
            get_user_input "Enter application name" "OpenSSH" "app_name"
            if ufw allow "$app_name"; then
                print_success "Enabled profile: $app_name"
            else
                print_error "Failed to enable profile: $app_name"
            fi
            ;;
        2)
            get_user_input "Enter application name" "OpenSSH" "app_name"
            if ufw delete allow "$app_name"; then
                print_success "Disabled profile: $app_name"
            else
                print_error "Failed to disable profile: $app_name"
            fi
            ;;
        3)
            get_user_input "Enter application name" "OpenSSH" "app_name"
            print_status "Profile information for $app_name:"
            ufw app info "$app_name" || print_error "Profile not found: $app_name"
            ;;
        4) return 0 ;;
        *) print_error "Invalid choice" ;;
    esac
}

configure_logging() {
    print_header "UFW Logging Configuration"
    
    echo "Current logging status:"
    ufw status verbose | grep -i logging
    echo ""
    
    echo "Logging levels:"
    echo "1) Off - No logging"
    echo "2) Low - Log blocked packets"
    echo "3) Medium - Log blocked packets and new connections"
    echo "4) High - Log all packets"
    echo "5) Full - Log everything with rate limiting"
    echo ""
    
    get_user_input "Select logging level" "2" "log_choice"
    
    case "$log_choice" in
        1) ufw logging off; print_success "Logging disabled" ;;
        2) ufw logging low; print_success "Logging set to low" ;;
        3) ufw logging medium; print_success "Logging set to medium" ;;
        4) ufw logging high; print_success "Logging set to high" ;;
        5) ufw logging full; print_success "Logging set to full" ;;
        *) print_error "Invalid choice" ;;
    esac
    
    echo ""
    print_status "UFW logs are typically found in /var/log/ufw.log"
}

backup_restore_rules() {
    print_header "Backup/Restore Firewall Rules"
    
    echo "1) Backup current rules"
    echo "2) Restore from backup"
    echo "3) List available backups"
    echo "4) Back"
    echo ""
    
    get_user_input "Select option" "1" "backup_choice"
    
    case "$backup_choice" in
        1) backup_firewall_rules ;;
        2) restore_firewall_rules ;;
        3) list_firewall_backups ;;
        4) return 0 ;;
        *) print_error "Invalid choice" ;;
    esac
}

backup_firewall_rules() {
    local backup_name="firewall-backup-$(date +%Y%m%d-%H%M%S)"
    local backup_file="$BACKUP_DIR/$backup_name.tar.gz"
    
    print_status "Creating firewall backup..."
    
    # Create backup directory structure
    mkdir -p "$BACKUP_DIR/tmp"
    
    # Export UFW rules
    ufw status numbered > "$BACKUP_DIR/tmp/ufw-rules.txt"
    ufw --dry-run status > "$BACKUP_DIR/tmp/ufw-status.txt"
    
    # Backup UFW configuration
    cp -r /etc/ufw "$BACKUP_DIR/tmp/" 2>/dev/null || true
    
    # Create archive
    tar -czf "$backup_file" -C "$BACKUP_DIR/tmp" .
    rm -rf "$BACKUP_DIR/tmp"
    
    print_success "Firewall backup created: $backup_file"
}

restore_firewall_rules() {
    print_header "Restore Firewall Rules"
    
    echo "Available backups:"
    ls -la "$BACKUP_DIR"/firewall-backup-*.tar.gz 2>/dev/null || {
        print_warning "No firewall backups found"
        return 1
    }
    
    echo ""
    get_user_input "Enter backup filename" "" "backup_file"
    
    if [[ ! -f "$BACKUP_DIR/$backup_file" ]]; then
        print_error "Backup file not found: $backup_file"
        return 1
    fi
    
    print_warning "This will replace current firewall configuration!"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Restoring firewall from backup..."
        
        # Extract backup
        mkdir -p "$BACKUP_DIR/restore"
        tar -xzf "$BACKUP_DIR/$backup_file" -C "$BACKUP_DIR/restore"
        
        # Reset UFW first
        ufw --force reset
        
        # Restore UFW configuration
        if [[ -d "$BACKUP_DIR/restore/ufw" ]]; then
            cp -r "$BACKUP_DIR/restore/ufw"/* /etc/ufw/ 2>/dev/null || true
        fi
        
        # Reload UFW
        ufw --force enable
        
        rm -rf "$BACKUP_DIR/restore"
        
        print_success "Firewall restored from backup"
        print_status "Current rules:"
        ufw status numbered
    else
        print_warning "Restore cancelled"
    fi
}

list_firewall_backups() {
    print_header "Available Firewall Backups"
    
    if ls "$BACKUP_DIR"/firewall-backup-*.tar.gz &>/dev/null; then
        ls -la "$BACKUP_DIR"/firewall-backup-*.tar.gz
    else
        print_warning "No firewall backups found"
    fi
}

# =============================================================================
# NAT AND PORT FORWARDING
# =============================================================================

nat_port_forwarding_menu() {
    while true; do
        print_header "NAT & Port Forwarding Management"
        echo ""
        echo "1) Configure port forwarding"
        echo "2) Configure NAT masquerading"
        echo "3) Show current NAT rules"
        echo "4) Remove NAT/forwarding rules"
        echo "5) Enable IP forwarding"
        echo "6) Back to main menu"
        echo ""
        
        get_user_input "Select option" "1" "nat_choice"
        
        case "$nat_choice" in
            1) configure_port_forwarding ;;
            2) configure_nat_masquerading ;;
            3) show_nat_rules ;;
            4) remove_nat_rules ;;
            5) enable_ip_forwarding ;;
            6) return 0 ;;
            *) print_error "Invalid choice" ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..." -r
        clear
    done
}

configure_port_forwarding() {
    print_header "Configure Port Forwarding"
    
    local external_port internal_ip internal_port protocol
    
    echo "Port forwarding redirects external traffic to internal hosts."
    echo "Example: Forward external port 8080 to internal 192.168.1.100:80"
    echo ""
    
    get_user_input "Enter external port" "8080" "external_port"
    get_user_input "Enter internal IP" "192.168.1.100" "internal_ip"
    get_user_input "Enter internal port" "80" "internal_port"
    get_user_input "Enter protocol (tcp/udp)" "tcp" "protocol"
    
    print_status "Configuring port forwarding..."
    print_status "External :$external_port -> $internal_ip:$internal_port ($protocol)"
    
    # Enable IP forwarding if not enabled
    if ! sysctl net.ipv4.ip_forward | grep -q "1"; then
        print_status "Enabling IP forwarding..."
        sysctl -w net.ipv4.ip_forward=1
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    
    # Add DNAT rule
    if iptables -t nat -A PREROUTING -p "$protocol" --dport "$external_port" -j DNAT --to-destination "$internal_ip:$internal_port"; then
        # Add FORWARD rule
        iptables -A FORWARD -p "$protocol" -d "$internal_ip" --dport "$internal_port" -j ACCEPT
        
        print_success "Port forwarding configured successfully!"
        print_warning "Rules are not persistent. Save with: iptables-persistent or netfilter-persistent"
        
        echo ""
        print_status "To make persistent, install iptables-persistent:"
        echo "sudo apt install iptables-persistent"
        echo "sudo netfilter-persistent save"
    else
        print_error "Failed to configure port forwarding"
    fi
}

configure_nat_masquerading() {
    print_header "Configure NAT Masquerading"
    
    local external_interface internal_network
    
    echo "NAT masquerading allows internal hosts to access internet."
    echo "This is commonly used for sharing internet connection."
    echo ""
    
    get_user_input "Enter external interface" "$(get_network_interface)" "external_interface"
    get_user_input "Enter internal network (CIDR)" "192.168.1.0/24" "internal_network"
    
    print_status "Configuring NAT masquerading..."
    print_status "Internal network: $internal_network via $external_interface"
    
    # Enable IP forwarding
    if ! sysctl net.ipv4.ip_forward | grep -q "1"; then
        print_status "Enabling IP forwarding..."
        sysctl -w net.ipv4.ip_forward=1
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    
    # Add masquerading rule
    if iptables -t nat -A POSTROUTING -s "$internal_network" -o "$external_interface" -j MASQUERADE; then
        # Allow forwarding
        iptables -A FORWARD -s "$internal_network" -j ACCEPT
        iptables -A FORWARD -d "$internal_network" -m state --state ESTABLISHED,RELATED -j ACCEPT
        
        print_success "NAT masquerading configured successfully!"
        print_warning "Rules are not persistent. Save with: iptables-persistent"
    else
        print_error "Failed to configure NAT masquerading"
    fi
}

show_nat_rules() {
    print_header "Current NAT Rules"
    
    echo "=== NAT Table (PREROUTING - Port Forwarding) ==="
    iptables -t nat -L PREROUTING -n -v --line-numbers
    
    echo ""
    echo "=== NAT Table (POSTROUTING - Masquerading) ==="
    iptables -t nat -L POSTROUTING -n -v --line-numbers
    
    echo ""
    echo "=== FORWARD Chain ==="
    iptables -L FORWARD -n -v --line-numbers
    
    echo ""
    print_status "IP Forwarding status:"
    sysctl net.ipv4.ip_forward
}

remove_nat_rules() {
    print_header "Remove NAT/Forwarding Rules"
    
    print_warning "This will remove ALL NAT and forwarding rules!"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Removing NAT rules..."
        
        # Flush NAT tables
        iptables -t nat -F PREROUTING
        iptables -t nat -F POSTROUTING
        iptables -F FORWARD
        
        print_success "NAT and forwarding rules removed"
        print_status "IP forwarding is still enabled. Disable with:"
        echo "sudo sysctl -w net.ipv4.ip_forward=0"
    else
        print_warning "Operation cancelled"
    fi
}

enable_ip_forwarding() {
    print_header "Enable IP Forwarding"
    
    if sysctl net.ipv4.ip_forward | grep -q "1"; then
        print_success "IP forwarding is already enabled"
    else
        print_status "Enabling IP forwarding..."
        
        # Enable temporarily
        sysctl -w net.ipv4.ip_forward=1
        
        # Make permanent
        if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
            echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
        fi
        
        print_success "IP forwarding enabled (persistent across reboots)"
    fi
    
    echo ""
    print_status "Current IP forwarding status:"
    sysctl net.ipv4.ip_forward
}

ip_management_menu() {
    while true; do
        print_header "IP Management & Network Tools"
        echo ""
        echo "1) Show network information"
        echo "2) Configure static IP"
        echo "3) Restore DHCP (automatic IP)"
        echo "4) Network diagnostics"
        echo "5) Preserve current IP settings"
        echo "6) Advanced firewall features"
        echo "7) Back to main menu"
        echo ""
        
        get_user_input "Select option" "1" "ip_choice"
        
        case "$ip_choice" in
            1)
                show_network_info
                read -p "Press Enter to continue..." -r
                ;;
            2)
                configure_static_ip
                ;;
            3)
                restore_dhcp
                ;;
            4)
                network_diagnostics
                ;;
            5)
                preserve_ip_settings
                ;;
            6)
                advanced_firewall_menu
                ;;
            7)
                return 0
                ;;
            *)
                print_error "Invalid choice"
                ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..." -r
        clear
    done
}

main_menu() {
    while true; do
        print_header "Advanced Network & Firewall Manager"
        echo ""
        echo "1) Add firewall rule"
        echo "2) Remove firewall rule"
        echo "3) Show current rules"
        echo "4) Quick setup"
        echo "5) IP Management & Network Tools"
        echo "6) Enable/Disable UFW"
        echo "7) Reset UFW (WARNING: removes all rules)"
        echo "8) Exit"
        echo ""
        
        get_user_input "Select option" "1" "choice"
        
        case "$choice" in
            1)
                add_firewall_rule
                ;;
            2)
                remove_firewall_rule
                ;;
            3)
                show_current_rules
                read -p "Press Enter to continue..." -r
                ;;
            4)
                quick_mode
                ;;
            5)
                ip_management_menu
                ;;
            6)
                echo "UFW options:"
                echo "a) Enable UFW"
                echo "b) Disable UFW"
                get_user_input "Choose action" "a" "ufw_action"
                
                case "$ufw_action" in
                    a) ufw --force enable; print_success "UFW enabled" ;;
                    b) ufw disable; print_success "UFW disabled" ;;
                    *) print_error "Invalid choice" ;;
                esac
                ;;
            7)
                print_warning "This will remove ALL firewall rules!"
                read -p "Are you sure? Type 'YES' to confirm: " -r confirm
                if [[ "$confirm" == "YES" ]]; then
                    ufw --force reset
                    print_success "UFW reset completed"
                else
                    print_warning "Reset cancelled"
                fi
                ;;
            8)
                print_success "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid choice"
                ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..." -r
        clear
    done
}

# Main execution
main() {
    clear
    check_root
    check_ufw
    check_dependencies
    init_config_dirs
    
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--status)
            show_current_rules
            exit 0
            ;;
        -a|--add)
            add_firewall_rule
            exit 0
            ;;
        -r|--remove)
            remove_firewall_rule
            exit 0
            ;;
        -q|--quick)
            quick_mode
            exit 0
            ;;
        "")
            main_menu
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi