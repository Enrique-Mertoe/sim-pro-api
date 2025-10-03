from ssm.models.base_models import SSMAuthUser, User
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.db import transaction
import csv
import io
import logging

logger = logging.getLogger(__name__)


def get_all_users(user, **kwargs):
    """Get all SSMAuthUser records"""
    users = SSMAuthUser.objects.all().values(
        'id', 'username', 'email', 'first_name', 'last_name',
        'is_active', 'is_staff', 'date_joined', 'last_login',
        'email_confirmed', 'phone', 'phone_confirmed'
    )
    return list(users)


def get_user(user, **kwargs):
    """Get a single SSMAuthUser by ID"""
    user_id = kwargs.get('user_id')
    if not user_id:
        raise ValueError("user_id is required")

    auth_user = SSMAuthUser.objects.filter(id=user_id).values(
        'id', 'username', 'email', 'first_name', 'last_name',
        'is_active', 'is_staff', 'date_joined', 'last_login',
        'email_confirmed', 'phone', 'phone_confirmed',
        'email_confirmed_at', 'phone_confirmed_at', 'confirmed_at',
        'raw_app_meta_data', 'raw_user_meta_data'
    ).first()

    if not auth_user:
        raise ValueError(f"User with id {user_id} not found")

    return auth_user


def create_user(user, **kwargs):
    """Create a new SSMAuthUser"""
    pass


def update_user(user, **kwargs):
    """Update an existing SSMAuthUser"""
    pass


def toggle_user_status(user, **kwargs):
    """Toggle a user's active status"""
    user_id = kwargs.get('user_id')
    if not user_id:
        raise ValueError("user_id is required")

    auth_user = SSMAuthUser.objects.filter(id=user_id).first()
    if not auth_user:
        raise ValueError(f"User with id {user_id} not found")

    # Toggle the is_active status
    auth_user.is_active = not auth_user.is_active
    auth_user.save()

    return {
        'id': str(auth_user.id),
        'username': auth_user.username,
        'email': auth_user.email,
        'is_active': auth_user.is_active
    }


def delete_user(user, **kwargs):
    """Delete an SSMAuthUser"""
    user_id = kwargs.get('user_id')
    if not user_id:
        raise ValueError("user_id is required")

    auth_user = SSMAuthUser.objects.filter(id=user_id).first()
    if not auth_user:
        raise ValueError(f"User with id {user_id} not found")

    auth_user.delete()

    return {
        'id': str(user_id),
        'deleted': True
    }


def confirm_user_email(user, **kwargs):
    """Confirm a user's email"""
    user_id = kwargs.get('user_id')
    if not user_id:
        raise ValueError("user_id is required")

    auth_user = SSMAuthUser.objects.filter(id=user_id).first()
    if not auth_user:
        raise ValueError(f"User with id {user_id} not found")

    # Update email confirmation fields
    now = timezone.now()
    auth_user.email_confirmed = True
    auth_user.email_confirmed_at = now
    auth_user.confirmed_at = now
    auth_user.save()

    return {
        'id': str(auth_user.id),
        'username': auth_user.username,
        'email': auth_user.email,
        'email_confirmed': auth_user.email_confirmed,
        'email_confirmed_at': auth_user.email_confirmed_at.isoformat() if auth_user.email_confirmed_at else None,
        'confirmed_at': auth_user.confirmed_at.isoformat() if auth_user.confirmed_at else None
    }


def unconfirm_user_email(user, **kwargs):
    """Unconfirm a user's email"""
    user_id = kwargs.get('user_id')
    if not user_id:
        raise ValueError("user_id is required")

    auth_user = SSMAuthUser.objects.filter(id=user_id).first()
    if not auth_user:
        raise ValueError(f"User with id {user_id} not found")

    # Update email confirmation fields
    auth_user.email_confirmed = False
    auth_user.email_confirmed_at = None
    auth_user.confirmed_at = None
    auth_user.save()

    return {
        'id': str(auth_user.id),
        'username': auth_user.username,
        'email': auth_user.email,
        'email_confirmed': auth_user.email_confirmed,
        'email_confirmed_at': None,
        'confirmed_at': None
    }


def bulk_import_users(user, **kwargs):
    """Bulk import users from CSV, filtering by admin_id and replacing with new admin"""
    csv_data = kwargs.get('csv_data')
    new_admin_id = kwargs.get('new_admin_id')
    filter_admin_id = kwargs.get('filter_admin_id')

    if not csv_data or not new_admin_id or not filter_admin_id:
        raise ValueError("csv_data, new_admin_id, and filter_admin_id are required")

    # Parse CSV
    csv_file = io.StringIO(csv_data)
    reader = csv.DictReader(csv_file)

    auth_users_to_create = []
    users_to_create = []

    for row in reader:
        # Filter by admin_id
        if row.get('admin_id') == filter_admin_id:
            user_id = row.get('id') or row.get('auth_user_id')
            email = row.get('email', '').strip()
            username = row.get('username', '').strip() or row.get('phone_number', '').strip()
            full_name = row.get('full_name', '').strip()

            # Parse created_at from CSV or use current time
            created_at_str = row.get('created_at', '').strip()
            if created_at_str:
                from dateutil import parser
                created_at = parser.parse(created_at_str)
            else:
                created_at = timezone.now()

            # Determine password (email > username > full_name)
            if email:
                password = email
            elif username:
                password = username
            elif full_name:
                password = full_name
            else:
                password = 'defaultpassword123'

            # Create SSMAuthUser data
            auth_user_data = {
                'id': user_id,
                'email': email or username or None,
                'username': username or email,
                'password': make_password(password),
                'is_active': row.get('is_active', 'true').lower() == 'true',
                'is_staff': False,
                'is_superuser': False,
                'date_joined': created_at,
                'phone': row.get('phone_number'),
                'email_confirmed': False,
                'phone_confirmed': False,
            }
            auth_users_to_create.append(auth_user_data)

            # Create User (staff) data
            user_data = {
                'id': user_id,
                'email': email or None,
                'full_name': full_name,
                'id_number': row.get('id_number', ''),
                'id_front_url': row.get('id_front_url', ''),
                'id_back_url': row.get('id_back_url', ''),
                'phone_number': row.get('phone_number', ''),
                'mobigo_number': row.get('mobigo_number', ''),
                'role': row.get('role', 'staff'),
                'team_id': row.get('team_id') or None,
                'staff_type': row.get('staff_type', ''),
                'is_active': row.get('is_active', 'true').lower() == 'true',
                'auth_user_id': user_id,
                'status': row.get('status', 'ACTIVE'),
                'admin_id': new_admin_id,  # Replace with new admin_id
                'username': username or email.split('@')[0] if email else full_name.replace(' ', '').lower(),
                'is_first_login': row.get('is_first_login', 'true').lower() == 'true',
                'created_at': created_at,
                'updated_at': timezone.now()
            }
            users_to_create.append(user_data)

    # Bulk create/update with transaction and logging
    try:
        with transaction.atomic():
            logger.info(f"Starting bulk import of {len(auth_users_to_create)} users")

            auth_created_count = 0
            auth_updated_count = 0
            user_created_count = 0
            user_updated_count = 0

            # Create/Update SSMAuthUsers
            if auth_users_to_create:
                logger.info(f"Processing {len(auth_users_to_create)} SSMAuthUser records")
                for auth_data in auth_users_to_create:
                    auth_user_id = auth_data.pop('id')

                    auth_user, created = SSMAuthUser.objects.update_or_create(
                        id=auth_user_id,
                        defaults=auth_data
                    )

                    if created:
                        auth_created_count += 1
                    else:
                        auth_updated_count += 1

                logger.info(f"SSMAuthUser: {auth_created_count} created, {auth_updated_count} updated")

            # Create/Update Users
            if users_to_create:
                logger.info(f"Processing {len(users_to_create)} User records")
                for user_data in users_to_create:
                    user_id = user_data.pop('id')

                    user_obj, created = User.objects.update_or_create(
                        id=user_id,
                        defaults=user_data
                    )

                    if created:
                        user_created_count += 1
                    else:
                        user_updated_count += 1

                logger.info(f"User: {user_created_count} created, {user_updated_count} updated")

            logger.info(f"Bulk import completed successfully")

            return {
                'imported_count': len(users_to_create),
                'auth_users_created': auth_created_count,
                'auth_users_updated': auth_updated_count,
                'users_created': user_created_count,
                'users_updated': user_updated_count,
                'message': f'Successfully imported {len(users_to_create)} users ({user_created_count} created, {user_updated_count} updated)'
            }
    except Exception as e:
        logger.error(f"Error during bulk import: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to import users: {str(e)}")


functions = {
    "admin_get_all_users": get_all_users,
    "admin_get_user": get_user,
    "admin_create_user": create_user,
    "admin_update_user": update_user,
    "admin_delete_user": delete_user,
    "admin_confirm_user_email": confirm_user_email,
    "admin_unconfirm_user_email": unconfirm_user_email,
    "admin_toggle_user_status": toggle_user_status,
    "admin_bulk_import_users": bulk_import_users
}
