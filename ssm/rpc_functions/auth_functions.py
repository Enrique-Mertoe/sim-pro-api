"""
Authentication-related RPC functions
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from ..models import User, OnboardingRequest, PasswordResetRequest

User = get_user_model()


def get_user_profile(user):
    """Get complete user profile with SSM-specific data"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        return {
            'auth_user': {
                'id': str(user.id),
                'email': user.email,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone,
                'email_confirmed': user.email_confirmed,
                'phone_confirmed': user.phone_confirmed,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None,
            },
            'ssm_profile': {
                'id': str(ssm_user.id),
                'role': ssm_user.role,
                'team_id': str(ssm_user.team.id) if ssm_user.team else None,
                'team_name': ssm_user.team.name if ssm_user.team else None,
                'is_active': ssm_user.is_active,
                'subscription_id': str(ssm_user.subscription.id) if ssm_user.subscription else None,
            }
        }
    except User.DoesNotExist:
        return {
            'auth_user': {
                'id': str(user.id),
                'email': user.email,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone,
                'email_confirmed': user.email_confirmed,
                'phone_confirmed': user.phone_confirmed,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None,
            },
            'ssm_profile': None
        }


def check_user_role(user, required_role):
    """Check if user has required role"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        return {
            'has_role': ssm_user.role == required_role,
            'current_role': ssm_user.role,
            'required_role': required_role
        }
    except User.DoesNotExist:
        return {
            'has_role': False,
            'current_role': None,
            'required_role': required_role
        }


def get_pending_onboarding_requests(user):
    """Get pending onboarding requests (admin only)"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role != 'admin':
            raise PermissionError("Only admins can view onboarding requests")

        requests = OnboardingRequest.objects.filter(status='pending').select_related('auth_user')
        return [
            {
                'id': str(req.id),
                'email': req.auth_user.email,
                'phone': req.phone,
                'requested_role': req.requested_role,
                'created_at': req.created_at.isoformat(),
            }
            for req in requests
        ]
    except User.DoesNotExist:
        raise PermissionError("User profile not found")


# Register functions
functions = {
    'get_user_profile': get_user_profile,
    'check_user_role': check_user_role,
    'get_pending_onboarding_requests': get_pending_onboarding_requests,
}