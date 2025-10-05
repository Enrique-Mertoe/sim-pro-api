#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install dnsutils
install_dnsutils() {
    echo -e "${YELLOW}Checking for dnsutils...${NC}"

    if ! command_exists dig; then
        echo -e "${YELLOW}dnsutils is not installed. Installing...${NC}"

        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y dnsutils
        elif command_exists yum; then
            sudo yum install -y bind-utils
        else
            echo -e "${RED}Could not determine package manager. Please install dnsutils manually.${NC}"
            echo -e "${YELLOW}For Ubuntu/Debian: sudo apt-get install dnsutils${NC}"
            echo -e "${YELLOW}For CentOS/RHEL: sudo yum install bind-utils${NC}"
            exit 1
        fi

        if ! command_exists dig; then
            echo -e "${RED}Failed to install dnsutils. Please install it manually.${NC}"
            exit 1
        fi

        echo -e "${GREEN}dnsutils installed successfully${NC}"
    else
        echo -e "${GREEN}dnsutils is already installed${NC}"
    fi
}

# Function to check and install Nginx
check_nginx() {
    echo -e "${YELLOW}Checking Nginx installation...${NC}"

    if ! command_exists nginx; then
        echo -e "${YELLOW}Nginx is not installed. Installing Nginx...${NC}"

        # Check package manager and install Nginx
        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y nginx
        elif command_exists yum; then
            sudo yum install -y nginx
        else
            echo -e "${RED}Could not determine package manager. Please install Nginx manually.${NC}"
            exit 1
        fi

        # Create necessary directories if they don't exist
        sudo mkdir -p /etc/nginx/sites-available
        sudo mkdir -p /etc/nginx/sites-enabled

        # Configure Nginx to include sites-enabled
        if [ ! -f "/etc/nginx/nginx.conf" ]; then
            echo -e "${RED}Nginx configuration file not found.${NC}"
            exit 1
        fi

        # Check if sites-enabled is already included
        if ! grep -q "include /etc/nginx/sites-enabled/\*;" /etc/nginx/nginx.conf; then
            echo -e "${YELLOW}Configuring Nginx to include sites-enabled...${NC}"
            sudo sed -i '/http {/a \    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
        fi

        # Start Nginx if not running
        if ! systemctl is-active --quiet nginx; then
            echo -e "${YELLOW}Starting Nginx service...${NC}"
            sudo systemctl start nginx
            sudo systemctl enable nginx
        fi

        echo -e "${GREEN}Nginx installation and configuration completed${NC}"
    else
        echo -e "${GREEN}Nginx is already installed${NC}"

        # Ensure directories exist
        sudo mkdir -p /etc/nginx/sites-available
        sudo mkdir -p /etc/nginx/sites-enabled

        # Check if sites-enabled is included
        if ! grep -q "include /etc/nginx/sites-enabled/\*;" /etc/nginx/nginx.conf; then
            echo -e "${YELLOW}Configuring Nginx to include sites-enabled...${NC}"
            sudo sed -i '/http {/a \    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
            sudo systemctl restart nginx
        fi
    fi

    # Test Nginx configuration
    echo -e "${YELLOW}Testing Nginx configuration...${NC}"
    if ! sudo nginx -t; then
        echo -e "${RED}Nginx configuration test failed${NC}"
        exit 1
    fi
}

# Function to check if Certbot is installed
check_certbot() {
    echo -e "${YELLOW}Checking Certbot installation...${NC}"

    if ! command_exists certbot; then
        echo -e "${YELLOW}Certbot is not installed. Installing Certbot...${NC}"

        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y certbot python3-certbot-nginx
        elif command_exists yum; then
            sudo yum install -y certbot python3-certbot-nginx
        else
            echo -e "${RED}Could not determine package manager. Please install Certbot manually.${NC}"
            exit 1
        fi

        echo -e "${GREEN}Certbot installation completed${NC}"
    else
        echo -e "${GREEN}Certbot is already installed${NC}"
    fi
}

# Function to check if a domain is valid
is_valid_domain() {
    local domain=$1
    # Basic domain validation
    if [[ $domain =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](\.[a-zA-Z]{2,})+$ ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if a domain is already configured
is_domain_configured() {
    local domain=$1
    if [ -f "/etc/nginx/sites-enabled/$domain" ]; then
        return 0
    else
        return 1
    fi
}

# Function to configure domain
configure_domain() {
    local domain=$1
    local subdomain=$2

    echo -e "${YELLOW}Configuring Nginx for $domain...${NC}"

    # Ask for port number
    read -p "Enter the local port your app is running on (e.g., 8000): " port
    if [[ -z "$port" ]]; then
        echo -e "${RED}Port number is required.${NC}"
        return 1
    fi

    # Create Nginx configuration dynamically
    cat << EOF | sudo tee /etc/nginx/sites-available/$domain > /dev/null
server {
    listen 80;
    server_name $domain;

    location / {
        proxy_pass http://localhost:$port;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Optional: serve static files if path exists
    location /static/ {
        alias /var/www/$domain/static/;
    }

    location /media/ {
        alias /var/www/$domain/media/;
    }
}
EOF

    # Enable site by creating a symlink
    sudo ln -sf /etc/nginx/sites-available/$domain /etc/nginx/sites-enabled/

    # Test and reload Nginx
    if sudo nginx -t; then
        sudo systemctl reload nginx
        echo -e "${GREEN}Nginx configured successfully for $domain (port $port)${NC}"
    else
        echo -e "${RED}Nginx configuration test failed${NC}"
    fi
}


# Function to check DNS records
check_dns_records() {
    local domain=$1
    local server_ip=$(curl -s ifconfig.me)

    echo -e "${YELLOW}Checking DNS records for $domain...${NC}"
    echo -e "${BLUE}Your server's public IP address is: $server_ip${NC}"
    echo -e "\n${YELLOW}Please ensure the following DNS records are set up:${NC}"
    echo -e "1. A Record: $domain -> $server_ip"
    echo -e "2. AAAA Record (if IPv6 is available): $domain -> [Your IPv6 address]"
    echo -e "\n${YELLOW}Instructions for common DNS providers:${NC}"
    echo -e "${BLUE}Cloudflare:${NC}"
    echo "1. Log in to your Cloudflare account"
    echo "2. Select your domain"
    echo "3. Go to DNS settings"
    echo "4. Add A record: Type=A, Name=$domain, Content=$server_ip, Proxy status=DNS only"
    echo -e "\n${BLUE}GoDaddy:${NC}"
    echo "1. Log in to your GoDaddy account"
    echo "2. Go to Domain Settings"
    echo "3. Select DNS Management"
    echo "4. Add A record: Type=A, Host=@, Points to=$server_ip"
    echo -e "\n${BLUE}Namecheap:${NC}"
    echo "1. Log in to your Namecheap account"
    echo "2. Go to Domain List"
    echo "3. Click Manage next to your domain"
    echo "4. Go to Advanced DNS"
    echo "5. Add A record: Type=A Record, Host=@, Value=$server_ip"

    read -p "Have you set up the DNS records? (y/N) " response
    case "$response" in
        [yY][eE][sS]|[yY])
            # Wait for DNS propagation
            echo -e "${YELLOW}Waiting for DNS propagation (this may take up to 24 hours, but usually 5-10 minutes)...${NC}"
            return 0
            ;;
        *)
            echo -e "${RED}Please set up the DNS records first and then run this script again.${NC}"
            exit 1
            ;;
    esac
}

# Function to verify DNS propagation
verify_dns_propagation() {
    local domain=$1
    local server_ip=$(curl -s ifconfig.me)
    local max_attempts=12
    local attempt=1
    local wait_time=60  # 1 minute

    echo -e "${YELLOW}Verifying DNS propagation...${NC}"

    # Install dnsutils if not present
    install_dnsutils

    while [ $attempt -le $max_attempts ]; do
        echo -e "${BLUE}Attempt $attempt of $max_attempts${NC}"

        # Try multiple DNS resolvers
        local dns_ip=""
        for resolver in "8.8.8.8" "1.1.1.1" "208.67.222.222"; do
            echo -e "${YELLOW}Checking with resolver $resolver...${NC}"
            dns_ip=$(dig @$resolver +short A $domain)
            if [ ! -z "$dns_ip" ]; then
                break
            fi
        done

        if [ ! -z "$dns_ip" ]; then
            if [ "$dns_ip" = "$server_ip" ]; then
                echo -e "${GREEN}DNS A record is properly configured!${NC}"
                return 0
            else
                echo -e "${YELLOW}DNS A record not yet propagated (got $dns_ip, expected $server_ip)${NC}"
            fi
        else
            echo -e "${YELLOW}No DNS A record found yet${NC}"
        fi

        if [ $attempt -lt $max_attempts ]; then
            echo -e "${YELLOW}Waiting $wait_time seconds before next attempt...${NC}"
            sleep $wait_time
        fi

        attempt=$((attempt + 1))
    done

    echo -e "${RED}DNS propagation check timed out after $((max_attempts * wait_time / 60)) minutes${NC}"
    echo -e "${YELLOW}You can:${NC}"
    echo "1. Wait longer and run this script again"
    echo "2. Check your DNS settings"
    echo "3. Contact your DNS provider"
    echo -e "\n${YELLOW}To verify DNS manually, you can run:${NC}"
    echo "dig A $domain"
    echo "or"
    echo "nslookup $domain"
    return 1
}

# Function to obtain SSL certificate with retry
obtain_ssl() {
    local domain=$1
    local max_attempts=3
    local attempt=1

    echo -e "${YELLOW}Obtaining SSL certificate for $domain...${NC}"

    while [ $attempt -le $max_attempts ]; do
        echo -e "${BLUE}Attempt $attempt of $max_attempts${NC}"

        if sudo certbot --nginx -d $domain --non-interactive --agree-tos --email admin@$domain; then
            echo -e "${GREEN}SSL certificate obtained successfully${NC}"
            return 0
        else
            echo -e "${RED}Attempt $attempt failed${NC}"

            if [ $attempt -lt $max_attempts ]; then
                echo -e "${YELLOW}Waiting 5 minutes before retry...${NC}"
                sleep 300
            fi

            attempt=$((attempt + 1))
        fi
    done

    echo -e "${RED}Failed to obtain SSL certificate after $max_attempts attempts${NC}"
    echo -e "${YELLOW}Please check:${NC}"
    echo "1. DNS records are properly configured"
    echo "2. Your server is accessible from the internet"
    echo "3. Port 80 is open and not blocked by firewall"
    echo "4. Your domain is not blacklisted"
    return 1
}

# Function to remove domain
remove_domain() {
    local domain=$1

    echo -e "${YELLOW}Removing domain $domain...${NC}"

    # Remove SSL certificate
    sudo certbot delete --cert-name $domain

    # Remove Nginx configuration
    sudo rm -f /etc/nginx/sites-enabled/$domain
    sudo rm -f /etc/nginx/sites-available/$domain

    # Reload Nginx
    sudo systemctl reload nginx

    echo -e "${GREEN}Domain removed successfully${NC}"
}

# Function to list configured domains
list_domains() {
    echo -e "${YELLOW}Configured domains:${NC}"
    ls -1 /etc/nginx/sites-enabled/
}

# Function to renew SSL certificates
renew_ssl() {
    echo -e "${YELLOW}Renewing SSL certificates...${NC}"

    if sudo certbot renew; then
        echo -e "${GREEN}SSL certificates renewed successfully${NC}"
    else
        echo -e "${RED}Failed to renew SSL certificates${NC}"
        exit 1
    fi
}

# Main script
echo -e "${YELLOW}Domain Management Script${NC}"

# Check prerequisites
check_nginx
check_certbot

# Show menu
while true; do
    echo -e "\n${YELLOW}Choose an option:${NC}"
    echo "1) Add new domain"
    echo "2) Remove domain"
    echo "3) List configured domains"
    echo "4) Renew SSL certificates"
    echo "5) Exit"
    read -p "Enter your choice (1-5): " choice

    case $choice in
        1)
            read -p "Enter domain name: " domain
            read -p "Enter subdomain (optional, press Enter to skip): " subdomain

            if [ -z "$domain" ]; then
                echo -e "${RED}Domain name is required${NC}"
                continue
            fi

            if ! is_valid_domain "$domain"; then
                echo -e "${RED}Invalid domain name${NC}"
                continue
            fi

            if is_domain_configured "$domain"; then
                echo -e "${RED}Domain is already configured${NC}"
                continue
            fi

            # Check and verify DNS records
            check_dns_records "$domain"
            verify_dns_propagation "$domain"

            # Configure domain and obtain SSL
            configure_domain "$domain" "$subdomain"
            obtain_ssl "$domain"
            ;;
        2)
            read -p "Enter domain name to remove: " domain

            if [ -z "$domain" ]; then
                echo -e "${RED}Domain name is required${NC}"
                continue
            fi

            if ! is_domain_configured "$domain"; then
                echo -e "${RED}Domain is not configured${NC}"
                continue
            fi

            remove_domain "$domain"
            ;;
        3)
            list_domains
            ;;
        4)
            renew_ssl
            ;;
        5)
            echo -e "${YELLOW}Exiting...${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            ;;
    esac
done