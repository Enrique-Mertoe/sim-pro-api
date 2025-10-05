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

# MySQL root credentials for database creation
MYSQL_ROOT_USER="root"
MYSQL_ROOT_PASSWORD=""

# Environment variables from .env
ENV_FILE="$APP_DIR/.env"

# Django settings module
DJANGO_SETTINGS_MODULE=""

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
}

load_env_credentials() {
    print_header "Loading Database Credentials"

    # Parse .env file manually to avoid variable collision
    local env_db_host=$(grep "^DB_HOST=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'")
    local env_db_name=$(grep "^DB_NAME=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'")
    local env_db_user=$(grep "^DB_USER=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'")
    local env_db_password=$(grep "^DB_PASSWORD=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'")
    local env_db_port=$(grep "^DB_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'")

    # Check if credentials exist in .env
    if [[ -n "$env_db_host" && -n "$env_db_name" && -n "$env_db_user" && -n "$env_db_password" ]]; then
        print_success "Database credentials found in .env file"
        echo ""
        echo "Current credentials in .env:"
        echo "  Host: $env_db_host"
        echo "  Database: $env_db_name"
        echo "  User: $env_db_user"
        echo "  Port: ${env_db_port:-3306}"
        echo ""

        read -p "Use these credentials? (Y/n): " use_env
        if [[ ! "$use_env" =~ ^[Nn]$ ]]; then
            # Use .env credentials
            DB_HOST="$env_db_host"
            DB_NAME="$env_db_name"
            DB_USER="$env_db_user"
            DB_PASSWORD="$env_db_password"
            DB_PORT="${env_db_port:-3306}"
            print_success "Using credentials from .env file"
            return 0
        else
            print_status "You chose to enter new credentials"
            get_database_credentials
            update_env_credentials
        fi
    else
        print_warning "No complete database credentials in .env file"
        print_status "Please enter database credentials"
        get_database_credentials
        update_env_credentials
    fi
}

get_database_credentials() {
    echo ""
    echo "Enter MySQL database credentials:"
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

get_mysql_root_credentials() {
    print_header "MySQL Root Credentials"

    echo "Enter MySQL root credentials to create database and user:"
    echo "(Press Enter to skip if database and user already exist)"
    echo ""

    read -p "MySQL Root User [root]: " input_root_user
    MYSQL_ROOT_USER=${input_root_user:-root}

    read -s -p "MySQL Root Password (leave empty if no password): " MYSQL_ROOT_PASSWORD
    echo ""
}

verify_database_connection() {
    print_header "Verifying database connection"

    if command -v mysql &> /dev/null; then
        if mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" &>/dev/null 2>&1; then
            print_success "Database connection successful with app user"
            return 0
        else
            print_warning "Cannot connect with app user credentials"
            print_status "Database and user may need to be created"
            return 1
        fi
    else
        print_warning "MySQL client not found, skipping connection test"
        return 0
    fi
}

update_env_credentials() {
    print_status "Updating .env file with new credentials"

    # Backup original .env
    local backup_file="$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$ENV_FILE" "$backup_file"
    print_status "Backup created: $backup_file"

    # Update or add database credentials
    sed -i "/^DB_HOST=/d" "$ENV_FILE"
    sed -i "/^DB_NAME=/d" "$ENV_FILE"
    sed -i "/^DB_USER=/d" "$ENV_FILE"
    sed -i "/^DB_PASSWORD=/d" "$ENV_FILE"
    sed -i "/^DB_PORT=/d" "$ENV_FILE"
    # Also remove old database configuration comment if exists
    sed -i "/^# Database Configuration (Updated by setup script)/d" "$ENV_FILE"

    # Remove trailing empty lines
    sed -i -e :a -e '/^\s*$/d;N;ba' "$ENV_FILE"

    # Add database credentials
    echo "" >> "$ENV_FILE"
    echo "# Database Configuration (Updated by setup script on $(date))" >> "$ENV_FILE"
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
        # Create system user without login
        useradd --system --shell /bin/bash --no-create-home "$APP_USER"
        usermod -a -G www-data "$APP_USER" 2>/dev/null || true
        print_success "User $APP_USER created"
    else
        print_warning "User $APP_USER already exists"
    fi

    # Ensure user has access to app directory
    if [[ -d "$APP_DIR" ]]; then
        chown -R "$APP_USER:$APP_USER" "$APP_DIR" 2>/dev/null || true
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

    # Check if we can connect with app user first
    if mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" &>/dev/null 2>&1; then
        print_success "Database user already exists and can connect"

        # Check if database exists
        if mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "USE \`$DB_NAME\`;" &>/dev/null 2>&1; then
            print_success "Database '$DB_NAME' already exists"
        else
            print_warning "Database '$DB_NAME' does not exist, will create it"
            # Try to create with app user
            mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || {
                print_warning "App user cannot create database, need root credentials"
                get_mysql_root_credentials
                create_database_and_user
            }
        fi
    else
        print_warning "Cannot connect with app user, database and user need to be created"
        get_mysql_root_credentials
        create_database_and_user
    fi

    print_success "MySQL database configured"
}

create_database_and_user() {
    print_status "Creating database and user with root credentials..."

    # Build mysql command with or without password
    local mysql_root_cmd="mysql -h$DB_HOST -P$DB_PORT -u$MYSQL_ROOT_USER"
    if [[ -n "$MYSQL_ROOT_PASSWORD" ]]; then
        mysql_root_cmd="$mysql_root_cmd -p$MYSQL_ROOT_PASSWORD"
    fi

    # Create database
    print_status "Creating database '$DB_NAME'..."
    $mysql_root_cmd -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || {
        print_error "Failed to create database"
        print_error "Please check MySQL root credentials and try again"
        exit 1
    }

    # Create user and grant privileges
    print_status "Creating user '$DB_USER' and granting privileges..."
    $mysql_root_cmd << EOF
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
CREATE USER IF NOT EXISTS '$DB_USER'@'%' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'%';
FLUSH PRIVILEGES;
EOF

    if [[ $? -eq 0 ]]; then
        print_success "Database and user created successfully"
    else
        print_error "Failed to create user or grant privileges"
        exit 1
    fi
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

detect_django_settings() {
    print_header "Detecting Django settings module"

    # Try to find Django project name
    local project_name=""
    if [[ -f "$APP_DIR/manage.py" ]]; then
        # Extract project name from manage.py
        project_name=$(grep "DJANGO_SETTINGS_MODULE" "$APP_DIR/manage.py" 2>/dev/null | sed -n "s/.*['\"]\\([^'\"]*\\)\\.settings['\"].*/\\1/p" | head -n1)
    fi

    if [[ -z "$project_name" ]]; then
        # Try to find by looking for wsgi.py
        project_name=$(find "$APP_DIR" -maxdepth 2 -name "wsgi.py" -type f 2>/dev/null | head -n1 | xargs dirname | xargs basename)
    fi

    if [[ -n "$project_name" ]]; then
        # Check for production_settings.py
        if [[ -f "$APP_DIR/$project_name/production_settings.py" ]]; then
            DJANGO_SETTINGS_MODULE="$project_name.production_settings"
            print_success "Found production settings: $DJANGO_SETTINGS_MODULE"
        elif [[ -f "$APP_DIR/$project_name/settings.py" ]]; then
            DJANGO_SETTINGS_MODULE="$project_name.settings"
            print_success "Found settings: $DJANGO_SETTINGS_MODULE"
        else
            DJANGO_SETTINGS_MODULE="$project_name.settings"
            print_warning "Settings file not found, using default: $DJANGO_SETTINGS_MODULE"
        fi
    else
        DJANGO_SETTINGS_MODULE="ssm_backend_api.settings"
        print_warning "Could not detect Django project, using default: $DJANGO_SETTINGS_MODULE"
    fi
}

verify_django_environment() {
    print_header "Verifying Django environment"

    local issues=()
    local project_name=$(echo "$DJANGO_SETTINGS_MODULE" | cut -d'.' -f1)
    local settings_file="$APP_DIR/$project_name/settings.py"

    # Check if Django project exists
    if [[ ! -f "$APP_DIR/manage.py" ]]; then
        issues+=("manage.py not found - not a Django project")
    fi

    if [[ ! -f "$settings_file" ]]; then
        # Try production_settings
        settings_file="$APP_DIR/$project_name/production_settings.py"
        if [[ ! -f "$settings_file" ]]; then
            issues+=("Django settings.py not found at $settings_file")
        fi
    fi

    if [[ -f "$settings_file" ]]; then
        # Check database configuration
        if ! grep -q "django.db.backends.mysql" "$settings_file" 2>/dev/null; then
            issues+=("MySQL database backend not configured in $settings_file")
        fi

        # Check if python-dotenv is used
        if ! grep -q "load_dotenv\\|python-dotenv" "$settings_file" 2>/dev/null; then
            issues+=("python-dotenv not configured for .env file loading")
        fi
    fi

    # Check requirements.txt
    if [[ -f "$APP_DIR/requirements.txt" ]]; then
        if ! grep -q "mysqlclient\\|PyMySQL" "$APP_DIR/requirements.txt" 2>/dev/null; then
            issues+=("MySQL client not in requirements.txt")
        fi
        if ! grep -q "python-dotenv" "$APP_DIR/requirements.txt" 2>/dev/null; then
            issues+=("python-dotenv not in requirements.txt")
        fi
    fi

    if [[ ${#issues[@]} -eq 0 ]]; then
        print_success "Django environment verification passed"
    else
        print_warning "Django environment issues found:"
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
        echo ""
        read -p "Continue setup anyway? (y/N): " continue_setup
        if [[ ! "$continue_setup" =~ ^[Yy]$ ]]; then
            print_status "Setup terminated. Please fix Django configuration manually."
            print_status "Required changes:"
            echo "  1. Configure MySQL in DATABASES setting"
            echo "  2. Add python-dotenv and load .env file"
            echo "  3. Add mysqlclient to requirements.txt"
            exit 1
        fi
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

    # Detect wsgi module
    local wsgi_module=$(echo "$DJANGO_SETTINGS_MODULE" | cut -d'.' -f1).wsgi:application

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
Environment=DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE
ExecStart=$VENV_DIR/bin/gunicorn --bind 127.0.0.1:8000 --workers 4 --timeout 60 --keep-alive 5 --access-logfile $LOG_DIR/gunicorn/access.log --error-logfile $LOG_DIR/gunicorn/error.log $wsgi_module
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable ssm-api

    print_success "Systemd service configured with $DJANGO_SETTINGS_MODULE"
}

initialize_database() {
    print_header "Initializing Django database"

    sudo -u "$APP_USER" bash << EOF
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
export DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE

# Run Django migrations
if [ -f manage.py ]; then
    echo "Creating migrations..."
    python manage.py makemigrations --noinput || echo "No new migrations to create"

    echo "Applying migrations..."
    python manage.py migrate --noinput

    echo "Collecting static files..."
    python manage.py collectstatic --noinput --clear || echo "Static files collection skipped"

    echo "Django database initialization completed"
else
    echo "manage.py not found. Please check your project structure."
    exit 1
fi
EOF

    print_success "Django database initialized with $DJANGO_SETTINGS_MODULE"
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
    load_env_credentials

    if [[ "$run_all" == true ]]; then
        print_status "Running complete setup..."
        install_system_packages
        create_user
        create_directories
        setup_database
        install_python_app
        detect_django_settings
        verify_django_environment
        setup_nginx
        setup_systemd_services
        initialize_database
        start_services
    else
        print_status "Running selected components: ${components[*]}"

        # Detect Django settings if needed for any component
        if [[ " ${components[*]} " =~ " systemd " ]] || [[ " ${components[*]} " =~ " init-db " ]]; then
            detect_django_settings
        fi

        for component in "${components[@]}"; do
            case $component in
                packages) install_system_packages ;;
                user) create_user ;;
                directories) create_directories ;;
                database) setup_database ;;
                python-app) install_python_app ;;
                environment)
                    detect_django_settings
                    verify_django_environment
                    ;;
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