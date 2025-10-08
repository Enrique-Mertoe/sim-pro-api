from functools import wraps

from django.http import JsonResponse
from rest_framework.authtoken.models import Token

from .models import (
    User, Team, SimCard, BatchMetadata, ActivityLog, OnboardingRequest,
    SimCardTransfer, PaymentRequest, Subscription, SubscriptionPlan,
    ForumTopic, ForumPost, ForumLike, SecurityRequestLog, TaskStatus,
    Config, Notification, PasswordResetRequest, LotMetadata, TeamGroup, TeamGroupMembership
)
from .models.product_instance_model import ProductInstance
from .models.shop_management_models import Product

# Model mapping for dynamic table access
MODEL_MAP = {
    'users': User,
    'teams': Team,
    'team_groups': TeamGroup,
    'team_group_memberships': TeamGroupMembership,
    'sim_cards': SimCard,
    'batch_metadata': BatchMetadata,
    'lot_metadata': LotMetadata,
    'activity_logs': ActivityLog,
    'onboarding_requests': OnboardingRequest,
    'sim_card_transfers': SimCardTransfer,
    'payment_requests': PaymentRequest,
    'subscriptions': Subscription,
    'subscription_plans': SubscriptionPlan,
    'forum_topics': ForumTopic,
    'forum_posts': ForumPost,
    'forum_likes': ForumLike,
    'security_request_logs': SecurityRequestLog,
    'task_status': TaskStatus,
    'config': Config,
    'notifications': Notification,
    'password_reset_requests': PasswordResetRequest,
    'products': Product,
    'product_instances': ProductInstance,
}


def serialize_user(user):
    """Serialize a User instance to a dictionary format compatible with Supabase

    Args:
        user: Can be either a User instance or SSMAuthUser instance
    """
    auth_user = user
    # if hasattr(user, 'raw_user_meta_data'):
    #     # This is an SSMAuthUser, get the profile data
    #
    #     print("auth_user")
    #     profile = User.objects.get(auth_user=auth_user)
    # else:
    #     # This is a User instance, get the auth user
    #     auth_user = user.auth_user
    #     profile = user

    # Base auth user data (Supabase format)
    user_data = {
        'id': str(auth_user.id),
        'aud': 'authenticated',
        'role': 'authenticated',
        'email': auth_user.email,
        'email_confirmed_at': auth_user.email_confirmed_at.isoformat() if auth_user.email_confirmed_at else None,
        'phone': auth_user.phone,
        'phone_confirmed_at': auth_user.phone_confirmed_at.isoformat() if auth_user.phone_confirmed_at else None,
        'confirmed_at': auth_user.confirmed_at.isoformat() if auth_user.confirmed_at else None,
        'last_sign_in_at': auth_user.last_login.isoformat() if auth_user.last_login else None,
        'app_metadata': auth_user.raw_app_meta_data or {},
        'user_metadata': auth_user.raw_user_meta_data or {},
        'identities': [],
        'created_at': auth_user.created_at.isoformat() if auth_user.created_at else None,
        'updated_at': auth_user.updated_at.isoformat() if auth_user.updated_at else None,
        'invited_at': auth_user.invited_at.isoformat() if auth_user.invited_at else None,
        'email_confirmed': auth_user.email_confirmed,
        'phone_confirmed': auth_user.phone_confirmed,
        'confirmation_sent_at': auth_user.confirmation_sent_at.isoformat() if auth_user.confirmation_sent_at else None,
        'recovery_sent_at': auth_user.recovery_sent_at.isoformat() if auth_user.recovery_sent_at else None,
        'email_change_sent_at': auth_user.email_change_sent_at.isoformat() if auth_user.email_change_sent_at else None,
        'new_email': auth_user.new_email,
        'new_phone': auth_user.new_phone,
        'banned_until': auth_user.banned_until.isoformat() if auth_user.banned_until else None,
    }

    # Add profile metadata if available
    # if profile:
    #     user_data['user_metadata'].update({
    #         'full_name': profile.full_name,
    #         'phone_number': profile.phone_number,
    #         'role': profile.role,
    #         'status': profile.status,
    #         'username': profile.username,
    #         'team': {
    #             'id': str(profile.team.id),
    #             'name': profile.team.name
    #         } if profile.team else None,
    #         'is_first_login': profile.is_first_login,
    #     })

    return user_data


def get_user_from_token(request) -> User | None:
    """Get user from Authorization header or cookies"""
    token = None

    # Try to get token from Authorization header first
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]

    # Fallback to cookie-based authentication
    if not token:
        token = request.COOKIES.get('sb-access-token')

    if not token:
        return None

    try:
        token_obj = Token.objects.get(key=token)
        return User.objects.get(auth_user=token_obj.user)
    except (Token.DoesNotExist, User.DoesNotExist):
        return None


def supabase_response(*, data=None, error=None, status=200):
    """Format response in Supabase style"""
    if error is None:
        error = {}
    if data is None:
        data = {}
    return JsonResponse({"data": data, "error": error}, status=status, safe=False)


def require_ssm_api_key(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        api_key = request.headers.get("apikey") or request.GET.get("api_key")
        VALID_API_KEY = "my-secret-key"

        if api_key != VALID_API_KEY:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view
