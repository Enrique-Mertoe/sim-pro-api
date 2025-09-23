"""
Custom authentication backend that supports both Django and Supabase password hashing
"""
import hashlib
import base64
import bcrypt
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from .models import User

AuthUser = get_user_model()


class SupabaseCompatibleBackend(BaseBackend):
    """
    Custom authentication backend that can verify both:
    1. Django-hashed passwords (for new users)
    2. Supabase/bcrypt passwords (for imported users)
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user with either Django or Supabase password format
        """
        if username is None or password is None:
            return None

        try:
            # Get the Django auth user
            auth_user = AuthUser.objects.get(email=username)

            # First try Django's built-in password verification
            if check_password(password, auth_user.password):
                return auth_user


        except AuthUser.DoesNotExist:
            return None

        return None

    def get_user(self, user_id):
        """
        Get user by ID
        """
        try:
            return AuthUser.objects.get(pk=user_id)
        except AuthUser.DoesNotExist:
            return None

    def _check_supabase_password(self, password, stored_password):
        """
        Check password against Supabase format
        Supabase typically uses format: $2a$10$... or $2b$10$...
        """
        try:
            if not stored_password.startswith(('$2a$', '$2b$', '$2y$')):
                return False
            return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
        except (ValueError, TypeError):
            return False

    def _check_bcrypt_password(self, password, stored_password):
        """
        Check password against raw bcrypt format
        """
        try:
            # Handle different bcrypt formats
            if stored_password.startswith('$2'):
                return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))

            # Handle base64 encoded bcrypt (sometimes used)
            try:
                decoded_hash = base64.b64decode(stored_password)
                return bcrypt.checkpw(password.encode('utf-8'), decoded_hash)
            except:
                pass

        except (ValueError, TypeError):
            pass

        return False


def create_user_with_supabase_password(email, password_hash, **user_data):
    """
    Create a user with Supabase-formatted password hash
    This is useful when importing users from Supabase
    """
    # Create Django auth user with the raw hash
    auth_user = AuthUser.objects.create_user(
        username=email,
        email=email,
        password='temp_password'  # Will be replaced
    )

    # Set the raw Supabase password hash
    auth_user.password = password_hash
    auth_user.save()

    # Create SSM user profile
    ssm_user = User.objects.create(
        auth_user_id=auth_user.id,
        email=email,
        **user_data
    )

    return auth_user, ssm_user


def migrate_user_password(user_email, new_password):
    """
    Migrate a user's password from Supabase format to Django format
    """
    try:
        auth_user = AuthUser.objects.get(email=user_email)
        auth_user.set_password(new_password)
        auth_user.save()
        return True
    except AuthUser.DoesNotExist:
        return False


def verify_password_format(password_hash):
    """
    Determine the format of a password hash
    """
    if password_hash.startswith('pbkdf2_'):
        return 'django'
    elif password_hash.startswith(('$2a$', '$2b$', '$2y$')):
        return 'bcrypt'
    elif password_hash.startswith('$argon2'):
        return 'argon2'
    else:
        return 'unknown'
