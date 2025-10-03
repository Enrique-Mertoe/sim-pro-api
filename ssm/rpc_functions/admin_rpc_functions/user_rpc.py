from ssm.models.base_models import SSMAuthUser
from django.utils import timezone


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


functions = {
    "admin_get_all_users": get_all_users,
    "admin_get_user": get_user,
    "admin_create_user": create_user,
    "admin_update_user": update_user,
    "admin_delete_user": delete_user,
    "admin_confirm_user_email": confirm_user_email,
    "admin_unconfirm_user_email": unconfirm_user_email,
    "admin_toggle_user_status": toggle_user_status
}
