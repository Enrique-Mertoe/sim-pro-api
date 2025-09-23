# SSM Backend API

A Django REST API backend for the SSM (SIM Card Management) system, providing comprehensive CRUD operations and API endpoints based on the existing PostgreSQL database schema.

## Features

- **Dual API Interface**: 
  - **Supabase-Compatible API** (`/api/*`) - Works seamlessly with your existing SDK
  - **Django REST Framework API** (`/api/v1/*`) - Advanced operations and admin interface
- **Complete Django Models**: All tables from the original SQL schema converted to Django models
- **SDK Integration**: Your `solobase-js` SDK works unchanged with Django backend
- **Trigger Logic**: Original SQL trigger functionality replicated in Django views
- **Role-Based Access**: User management with different roles (admin, team_leader, staff)
- **Security Logging**: Request logging and security monitoring
- **Forum System**: Built-in forum with topics, posts, and likes
- **Activity Tracking**: Comprehensive activity logging system
- **File Storage**: Complete file upload/download system
- **Admin Interface**: Full Django admin interface for all models

## Models Included

- **Users & Teams**: User management with team hierarchies
- **SIM Cards**: SIM card lifecycle management with batch processing  
- **Onboarding**: User onboarding request workflow
- **Transfers**: SIM card transfer between teams
- **Payments & Subscriptions**: Payment processing and subscription management
- **Forum**: Discussion forum with topics and posts
- **Security**: Security request logging and monitoring
- **Notifications**: User notification system
- **Configuration**: System configuration management

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Database

Update `ssm_backend_api/settings.py` with your PostgreSQL credentials:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'your_database_name',
        'USER': 'your_username',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 3. Run Migrations

Since you already have an existing database with the schema, you have two options:

**Option A: Use existing data (recommended)**
```bash
# Mark migrations as applied without running them
python manage.py migrate --fake-initial
```

**Option B: Fresh database**
```bash
# Run migrations to create tables
python manage.py migrate
```

### 4. Create Superuser

```bash
python manage.py createsuperuser
```

### 5. Run Development Server

```bash
python manage.py runserver
```

The API will be available at: `http://localhost:8000/api/v1/`

## API Documentation

- **[SDK_INTEGRATION.md](SDK_INTEGRATION.md)** - Complete guide for using your SDK with Django backend
- **[API_ENDPOINTS.md](API_ENDPOINTS.md)** - Django REST Framework endpoints documentation

### Quick SDK Setup

```javascript
// Your existing SDK works unchanged!
const { createClient } = require('./sdk/index.js');
const solobase = createClient('http://localhost:8000', 'your-api-key');

// Use exactly like Supabase
const { data, error } = await solobase.auth.signUp({ email, password });
const { data, error } = await solobase.from('sim_cards').select();
```

## Key Features Implemented

### 1. SQL Trigger Logic Replicated

The original SQL triggers have been replicated in Django views:

- **SIM Card Registration**: Auto-updates `registered_on` when status changes to 'REGISTERED'
- **Onboarding Approval**: Auto-creates User when onboarding request is approved
- **Team Leadership**: Auto-updates user's team when team leader changes
- **SIM Transfers**: Auto-moves SIM cards when transfer is approved
- **Activity Logging**: All actions are automatically logged

### 2. Comprehensive API Endpoints

- Full CRUD operations for all models
- Custom actions (approve, reject, transfer, etc.)
- Filtering and search capabilities
- Bulk operations where appropriate
- Proper HTTP status codes and error handling

### 3. Django Admin Integration

- All models registered with admin interface
- Custom admin configurations with list displays, filters, and search
- Proper field relationships displayed
- Read-only fields for audit trails

### 4. Authentication & Permissions

- Token-based authentication
- Permission classes for secure access
- User role-based filtering where appropriate

## Project Structure

```
ssm-backend-api/
├── ssm/                          # Main Django app
│   ├── models.py                 # All Django models
│   ├── serializers.py            # DRF serializers
│   ├── views.py                  # API views with trigger logic
│   ├── admin.py                  # Django admin configuration
│   └── urls.py                   # API URL routing
├── ssm_backend_api/              # Django project settings
│   ├── settings.py               # Database and app configuration
│   └── urls.py                   # Main URL configuration
├── requirements.txt              # Python dependencies
├── API_ENDPOINTS.md             # Complete API documentation
└── README.md                    # This file
```

## Testing

Run the setup verification script:

```bash
python test_setup.py
```

This will verify:
- Model definitions and relationships
- API endpoint registration
- Django system configuration

## Usage Examples

### Create a new SIM card:
```bash
curl -X POST http://localhost:8000/api/v1/sim-cards/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "serial_number": "SIM123456",
    "status": "PENDING",
    "team": "team-uuid",
    "registered_by_user": "user-uuid",
    "batch_id": "BATCH001"
  }'
```

### Approve an onboarding request:
```bash
curl -X POST http://localhost:8000/api/v1/onboarding-requests/{id}/approve/ \
  -H "Authorization: Token YOUR_TOKEN"
```

### Get team performance metrics:
```bash
curl -X GET http://localhost:8000/api/v1/teams/{id}/performance/ \
  -H "Authorization: Token YOUR_TOKEN"
```

## Notes

- The SDK folder is not modified as per requirements
- All original SQL schema functionality is preserved
- Database constraints and relationships are maintained
- Existing trigger logic is replicated in Django views
- The API follows RESTful conventions and DRF best practices

## Support

This Django backend provides a complete REST API replacement for direct database access while maintaining all original functionality and adding the benefits of Django's ORM, admin interface, and REST framework.