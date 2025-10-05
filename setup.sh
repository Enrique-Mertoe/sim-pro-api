#!/bin/bash

# =============================================================================
# SSM Django API - Setup Script
# This script sets up the Django SSM API environment with MySQL
# Usage: ./setup.sh [OPTIONS]
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="ssm_api_app"
APP_USER="ssm_api_user"
CURRENT_DIR="$(pwd)"
APP_DIR="$CURRENT_DIR"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/ssm_api_app"
CONFIG_DIR="/etc/ssm_api_app"
BACKUP_DIR="/var/backups/ssm_api_app"
SYSTEMD_DIR="/etc/systemd/system"

# Database variables (will be set interactively)
DB_HOST=""
DB_NAME=""
DB_USER=""
DB_PASSWORD=""
DB_PORT="3306"

# Environment variables from .env
ENV_FILE="$APP_DIR/.env"

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

show_help() {
    cat << EOF
${CYAN}SSM Django API Setup Script${NC}

${YELLOW}USAGE:${NC}
    $0 [OPTIONS]

${YELLOW}OPTIONS:${NC}
    ${GREEN}--help, -h${NC}              Show this help message
    ${GREEN}--all${NC}                   Run complete setup (default)
    ${GREEN}--packages${NC}              Install system packages only
    ${GREEN}--user${NC}                  Create application user only
    ${GREEN}--directories${NC}           Create directories only
    ${GREEN}--database${NC}              Setup MySQL database only
    ${GREEN}--python-app${NC}            Install Python application only
    ${GREEN}--environment${NC}           Setup environment configuration only
    ${GREEN}--nginx${NC}                 Setup Nginx only
    ${GREEN}--systemd${NC}               Setup systemd services only
    ${GREEN}--init-db${NC}               Initialize Django database only
    ${GREEN}--start-services${NC}        Start services only

${YELLOW}NOTES:${NC}
    - Script can be run multiple times safely
    - Requires .env file in project root
    - Interactive database credential input
    - Uses MySQL instead of PostgreSQL

EOF
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

check_env_file() {
    print_header "Checking .env file"
    
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error ".env file not found at $ENV_FILE"
        print_error "Setup cannot continue without .env file"
        print_status "Please create .env file with required environment variables"
        exit 1
    fi
    
    print_success ".env file found"
    
    # Source the .env file
    set -a
    source "$ENV_FILE"
    set +a
}

get_database_credentials() {
    print_header "Database Configuration"
    
    echo "Please enter MySQL database credentials:"
    echo ""
    
    read -p "Database Host [localhost]: " input_host
    DB_HOST=${input_host:-localhost}
    
    read -p "Database Name [ssm_api_app]: " input_name
    DB_NAME=${input_name:-ssm_api_app}
    
    read -p "Database User [ssm_user]: " input_user
    DB_USER=${input_user:-ssm_user}
    
    read -s -p "Database Password: " DB_PASSWORD
    echo ""
    while [[ -z "$DB_PASSWORD" ]]; do
        print_error "Database password cannot be empty"
        read -s -p "Database Password: " DB_PASSWORD
        echo ""
    done
    
    read -p "Database Port [3306]: " input_port
    DB_PORT=${input_port:-3306}
    
    print_success "Database credentials collected"
}

verify_database_connection() {
    print_header "Verifying database connection"
    
    if command -v mysql &> /dev/null; then
        if mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" &>/dev/null; then
            print_success "Database connection successful"
        else
            print_error "Database connection failed"
            print_error "Please check your credentials and try again"
            exit 1
        fi
    else
        print_warning "MySQL client not found, skipping connection test"
    fi
}

compare_credentials() {
    print_header "Checking environment credentials"
    
    # Check if database credentials exist in .env
    if [[ -n "${DATABASE_URL:-}" ]] || [[ -n "${DB_HOST:-}" && -n "${DB_NAME:-}" && -n "${DB_USER:-}" && -n "${DB_PASSWORD:-}" ]]; then
        print_status "Database credentials found in .env file"
        
        # Extract credentials from .env if they exist
        ENV_DB_HOST="${DB_HOST:-}"
        ENV_DB_NAME="${DB_NAME:-}"
        ENV_DB_USER="${DB_USER:-}"
        ENV_DB_PASSWORD="${DB_PASSWORD:-}"
        
        if [[ "$ENV_DB_HOST" != "$DB_HOST" ]] || [[ "$ENV_DB_NAME" != "$DB_NAME" ]] || [[ "$ENV_DB_USER" != "$DB_USER" ]]; then
            print_warning "Credentials mismatch detected!"
            echo ""
            echo "Environment file credentials:"
            echo "  Host: ${ENV_DB_HOST:-'not set'}"
            echo "  Database: ${ENV_DB_NAME:-'not set'}"
            echo "  User: ${ENV_DB_USER:-'not set'}"
            echo ""
            echo "Your input credentials:"
            echo "  Host: $DB_HOST"
            echo "  Database: $DB_NAME"
            echo "  User: $DB_USER"
            echo ""
            
            read -p "Use credentials from setup input? (y/N): " use_input
            if [[ "$use_input" =~ ^[Yy]$ ]]; then
                update_env_credentials
            else
                # Use .env credentials
                DB_HOST="$ENV_DB_HOST"
                DB_NAME="$ENV_DB_NAME"
                DB_USER="$ENV_DB_USER"
                DB_PASSWORD="$ENV_DB_PASSWORD"
                print_status "Using credentials from .env file"
            fi
        else
            print_success "Credentials match .env file"
        fi
    else
        print_status "No database credentials in .env file, using input credentials"
        update_env_credentials
    fi
}

update_env_credentials() {
    print_status "Updating .env file with new credentials"
    
    # Backup original .env
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Update or add database credentials
    sed -i "/^DB_HOST=/d" "$ENV_FILE"
    sed -i "/^DB_NAME=/d" "$ENV_FILE"
    sed -i "/^DB_USER=/d" "$ENV_FILE"
    sed -i "/^DB_PASSWORD=/d" "$ENV_FILE"
    sed -i "/^DB_PORT=/d" "$ENV_FILE"
    
    echo "" >> "$ENV_FILE"
    echo "# Database Configuration (Updated by setup script)" >> "$ENV_FILE"
    echo "DB_HOST=$DB_HOST" >> "$ENV_FILE"
    echo "DB_NAME=$DB_NAME" >> "$ENV_FILE"
    echo "DB_USER=$DB_USER" >> "$ENV_FILE"
    echo "DB_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
    echo "DB_PORT=$DB_PORT" >> "$ENV_FILE"
    
    print_success ".env file updated with new credentials"
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        print_error "Cannot detect operating system"
        exit 1
    fi
    
    print_status "Detected OS: $OS $VER"
}

install_system_packages() {
    print_header "Installing system packages"
    
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        apt update
        apt install -y \
            python3 \
            python3-pip \
            python3-venv \
            python3-dev \
            mysql-server \
            mysql-client \
            libmysqlclient-dev \
            pkg-config \
            nginx \
            git \
            curl \
            wget \
            build-essential \
            libssl-dev \
            libffi-dev \
            supervisor \
            logrotate \
            htop \
            tree \
            nano \
            vim
            
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Rocky"* ]]; then
        yum update -y
        yum groupinstall -y "Development Tools"
        yum install -y \
            python3 \
            python3-pip \
            python3-devel \
            mysql-server \
            mysql-devel \
            nginx \
            git \
            curl \
            wget \
            openssl-devel \
            libffi-devel \
            supervisor \
            logrotate \
            htop \
            tree \
            nano \
            vim
    else
        print_error "Unsupported operating system: $OS"
        exit 1
    fi
    
    print_success "System packages installed"
}

create_user() {
    print_header "Creating application user"
    
    if ! id "$APP_USER" &>/dev/null; then
        useradd --system --home "$APP_DIR" --shell /bin/bash "$APP_USER"
        usermod -a -G www-data "$APP_USER" 2>/dev/null || true
        print_success "User $APP_USER created"
    else
        print_warning "User $APP_USER already exists"
    fi
}

create_directories() {
    print_header "Creating application directories"
    
    # Create directories if they don't exist
    mkdir -p "$LOG_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$LOG_DIR/nginx"
    mkdir -p "$LOG_DIR/gunicorn"
    mkdir -p "$CONFIG_DIR/nginx"
    mkdir -p "$APP_DIR/static"
    mkdir -p "$APP_DIR/media"
    
    # Set permissions
    chown -R "$APP_USER:$APP_USER" "$LOG_DIR"
    chown -R "$APP_USER:$APP_USER" "$BACKUP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/static" 2>/dev/null || true
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/media" 2>/dev/null || true
    
    print_success "Directories created"
}

setup_database() {
    print_header "Setting up MySQL database"
    
    # Start MySQL service
    systemctl start mysql || systemctl start mysqld || true
    systemctl enable mysql || systemctl enable mysqld || true
    
    # Create database if it doesn't exist
    mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || print_warning "Database creation may have failed"
    
    print_success "MySQL database configured"
}

install_python_app() {
    print_header "Installing Python application"
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "$VENV_DIR" ]]; then
        sudo -u "$APP_USER" python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi
    
    # Install dependencies
    sudo -u "$APP_USER" bash << EOF
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Django and MySQL dependencies
pip install Django mysqlclient python-dotenv

# Install from requirements.txt if it exists
if [[ -f "requirements.txt" ]]; then
    pip install -r requirements.txt
    echo "Requirements installed from requirements.txt"
else
    echo "No requirements.txt found, installed basic packages"
fi

# Install production packages
pip install gunicorn whitenoise

echo "Python application installed successfully"
EOF
    
    print_success "Python application installed"
}

setup_environment() {
    print_header "Setting up Django environment"
    
    # Create Django settings for production if not exists
    if [[ ! -f "$APP_DIR/ssm_backend_api/production_settings.py" ]]; then
        sudo -u "$APP_USER" cat > "$APP_DIR/ssm_backend_api/production_settings.py" << EOF
from .settings import *
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Security
DEBUG = False
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# Static files
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Security settings
SECURE_SSL_REDIRECT = False  # Set to True when using HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '$LOG_DIR/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
EOF
        print_success "Production settings created"
    else
        print_warning "Production settings already exist"
    fi
}

setup_nginx() {
    print_header "Setting up Nginx"
    
    # Create Nginx configuration
    cat > "$CONFIG_DIR/nginx/ssm_api_app.conf" << EOF
upstream ssm_api_app {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;
    
    client_max_body_size 16M;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Static files
    location /static/ {
        alias $APP_DIR/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias $APP_DIR/media/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Django application
    location / {
        proxy_pass http://ssm_api_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Logging
    access_log $LOG_DIR/nginx/access.log;
    error_log $LOG_DIR/nginx/error.log;
}
EOF
    
    # Link configuration
    ln -sf "$CONFIG_DIR/nginx/ssm_api_app.conf" /etc/nginx/sites-available/ssm_api_app
    ln -sf /etc/nginx/sites-available/ssm_api_app /etc/nginx/sites-enabled/ssm_api_app
    
    # Remove default site if it exists
    rm -f /etc/nginx/sites-enabled/default
    
    # Test configuration
    nginx -t
    
    systemctl restart nginx
    systemctl enable nginx
    
    print_success "Nginx configured"
}

setup_systemd_services() {
    print_header "Setting up systemd services"
    
    # Django application service
    cat > "$SYSTEMD_DIR/ssm-api.service" << EOF
[Unit]
Description=SSM Django API Application
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=exec
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV_DIR/bin
Environment=DJANGO_SETTINGS_MODULE=ssm_backend_api.production_settings
ExecStart=$VENV_DIR/bin/gunicorn --bind 127.0.0.1:8000 --workers 4 --timeout 60 --keep-alive 5 --access-logfile $LOG_DIR/gunicorn/access.log --error-logfile $LOG_DIR/gunicorn/error.log ssm_backend_api.wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable ssm-api
    
    print_success "Systemd service configured"
}

initialize_database() {
    print_header "Initializing Django database"
    
    sudo -u "$APP_USER" bash << EOF
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
export DJANGO_SETTINGS_MODULE=ssm_backend_api.production_settings

# Run Django migrations
if [ -f manage.py ]; then
    echo "Creating migrations..."
    python manage.py makemigrations --noinput || echo "No new migrations to create"
    
    echo "Applying migrations..."
    python manage.py migrate --noinput
    
    echo "Collecting static files..."
    python manage.py collectstatic --noinput --clear
    
    echo "Django database initialization completed"
else
    echo "manage.py not found. Please check your project structure."
    exit 1
fi
EOF
    
    print_success "Django database initialized"
}

start_services() {
    print_header "Starting services"
    
    systemctl start ssm-api
    
    # Wait for service to start
    sleep 5
    
    # Check service status
    if systemctl is-active --quiet ssm-api; then
        print_success "SSM API service started"
    else
        print_warning "SSM API service may have issues - check logs with: journalctl -u ssm-api"
    fi
    
    # Check nginx
    if systemctl is-active --quiet nginx; then
        print_success "Nginx is running"
    else
        print_warning "Nginx may have issues - check logs with: journalctl -u nginx"
    fi
}

# Main execution function
execute_setup() {
    local run_all=true
    local components=()
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --all)
                run_all=true
                shift
                ;;
            --packages|--user|--directories|--database|--python-app|--environment|--nginx|--systemd|--init-db|--start-services)
                run_all=false
                components+=("${1#--}")
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Always run these checks first
    check_root
    detect_os
    check_env_file
    get_database_credentials
    verify_database_connection
    compare_credentials
    
    if [[ "$run_all" == true ]]; then
        print_status "Running complete setup..."
        install_system_packages
        create_user
        create_directories
        setup_database
        install_python_app
        setup_environment
        setup_nginx
        setup_systemd_services
        initialize_database
        start_services
    else
        print_status "Running selected components: ${components[*]}"
        for component in "${components[@]}"; do
            case $component in
                packages) install_system_packages ;;
                user) create_user ;;
                directories) create_directories ;;
                database) setup_database ;;
                python-app) install_python_app ;;
                environment) setup_environment ;;
                nginx) setup_nginx ;;
                systemd) setup_systemd_services ;;
                init-db) initialize_database ;;
                start-services) start_services ;;
            esac
        done
    fi
    
    print_header "Setup completed successfully!"
    print_status "Your SSM Django API is ready at: http://localhost"
    print_status "Check service status with: systemctl status ssm-api"
    print_status "View logs with: journalctl -u ssm-api -f"
}

# Run setup if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    execute_setup "$@"
fi