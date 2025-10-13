"""
Subscription management RPC functions
Handles subscription plans, user subscriptions, and subscription-based rules/limits
"""
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import uuid

from ..models import Subscription, SubscriptionPlan, User


# ==================== SUBSCRIPTION PLAN RULES ====================
# Static configuration for subscription plan limits and features
SUBSCRIPTION_RULES = {
    'free': {
        'max_users': 5,
        'max_teams': 1,
        'max_sim_cards': 100,
        'max_upload_size_mb': 5,
        'max_allowable_serials': 100,
        'max_shops': 1,
        'max_products': 50,
        'features': {
            'basic_reporting': True,
            'advanced_analytics': False,
            'api_access': False,
            'priority_support': False,
            'custom_branding': False,
            'bulk_operations': False,
            'export_data': False,
            'multi_team': False,
            'shop_management': False,
        },
        'rate_limits': {
            'api_calls_per_hour': 100,
            'bulk_upload_per_day': 1,
        }
    },
    'basic': {
        'max_users': 25,
        'max_teams': 3,
        'max_sim_cards': 1000,
        'max_upload_size_mb': 20,
        'max_allowable_serials': 1000,
        'max_shops': 5,
        'max_products': 500,
        'features': {
            'basic_reporting': True,
            'advanced_analytics': True,
            'api_access': False,
            'priority_support': False,
            'custom_branding': False,
            'bulk_operations': True,
            'export_data': True,
            'multi_team': True,
            'shop_management': True,
        },
        'rate_limits': {
            'api_calls_per_hour': 500,
            'bulk_upload_per_day': 5,
        }
    },
    'professional': {
        'max_users': 100,
        'max_teams': 10,
        'max_sim_cards': 10000,
        'max_upload_size_mb': 50,
        'max_allowable_serials': 10000,
        'max_shops': 20,
        'max_products': 5000,
        'features': {
            'basic_reporting': True,
            'advanced_analytics': True,
            'api_access': True,
            'priority_support': True,
            'custom_branding': False,
            'bulk_operations': True,
            'export_data': True,
            'multi_team': True,
            'shop_management': True,
        },
        'rate_limits': {
            'api_calls_per_hour': 2000,
            'bulk_upload_per_day': 20,
        }
    },
    'enterprise': {
        'max_users': -1,  # Unlimited
        'max_teams': -1,  # Unlimited
        'max_sim_cards': -1,  # Unlimited
        'max_upload_size_mb': 200,
        'max_allowable_serials': -1,  # Unlimited
        'max_shops': -1,  # Unlimited
        'max_products': -1,  # Unlimited
        'features': {
            'basic_reporting': True,
            'advanced_analytics': True,
            'api_access': True,
            'priority_support': True,
            'custom_branding': True,
            'bulk_operations': True,
            'export_data': True,
            'multi_team': True,
            'shop_management': True,
        },
        'rate_limits': {
            'api_calls_per_hour': -1,  # Unlimited
            'bulk_upload_per_day': -1,  # Unlimited
        }
    }
}


# ==================== SUBSCRIPTION PLANS ====================

def get_all_subscription_plans(user):
    """
    Get all available subscription plans
    """
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')

    result = []
    for plan in plans:
        plan_name = plan.name.lower()
        rules = SUBSCRIPTION_RULES.get(plan_name, SUBSCRIPTION_RULES['free'])

        result.append({
            'id': str(plan.id),
            'name': plan.name,
            'description': plan.description,
            'price_monthly': plan.price_monthly,
            'price_annual': plan.price_annual,
            'features': plan.features,
            'is_recommended': plan.is_recommended,
            'rules': rules,
            'created_at': plan.created_at.isoformat()
        })

    return result


def get_subscription_plan(user, plan_id):
    """
    Get specific subscription plan details with rules
    """
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        plan_name = plan.name.lower()
        rules = SUBSCRIPTION_RULES.get(plan_name, SUBSCRIPTION_RULES['free'])

        return {
            'id': str(plan.id),
            'name': plan.name,
            'description': plan.description,
            'price_monthly': plan.price_monthly,
            'price_annual': plan.price_annual,
            'features': plan.features,
            'is_recommended': plan.is_recommended,
            'rules': rules,
            'created_at': plan.created_at.isoformat()
        }
    except SubscriptionPlan.DoesNotExist:
        raise ValueError(f"Subscription plan with ID {plan_id} not found")


# ==================== USER SUBSCRIPTIONS ====================

def get_user_subscription(user):
    """
    Get current user's active subscription with rules
    """
    # Get admin user (tenant)
    admin_user = user if user.role == 'admin' and not user.admin else user.admin

    # Get active subscription
    subscription = Subscription.objects.filter(
        user=admin_user,
        status='active',
        starts_at__lte=timezone.now(),
        expires_at__gt=timezone.now()
    ).select_related('user').first()

    if not subscription:
        # Return free plan as default
        return {
            'has_subscription': False,
            'subscription': None,
            'plan': None,
            'rules': SUBSCRIPTION_RULES['free'],
            'status': 'no_active_subscription'
        }

    # Get plan details
    try:
        plan = SubscriptionPlan.objects.get(id=subscription.plan_id)
        plan_name = plan.name.lower()
        rules = SUBSCRIPTION_RULES.get(plan_name, SUBSCRIPTION_RULES['free'])

        # Calculate days remaining
        days_remaining = (subscription.expires_at - timezone.now()).days

        return {
            'has_subscription': True,
            'subscription': {
                'id': str(subscription.id),
                'status': subscription.status,
                'starts_at': subscription.starts_at.isoformat(),
                'expires_at': subscription.expires_at.isoformat(),
                'days_remaining': days_remaining,
                'auto_renew': subscription.auto_renew,
                'is_trial': subscription.is_trial,
                'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            },
            'plan': {
                'id': str(plan.id),
                'name': plan.name,
                'description': plan.description,
                'features': plan.features,
            },
            'rules': rules,
            'status': 'active'
        }
    except SubscriptionPlan.DoesNotExist:
        # Plan was deleted, return free plan
        return {
            'has_subscription': False,
            'subscription': None,
            'plan': None,
            'rules': SUBSCRIPTION_RULES['free'],
            'status': 'plan_not_found'
        }


def get_subscription_status(user):
    """
    Get subscription status with usage statistics
    """
    result = get_user_subscription(user)

    if not result['has_subscription']:
        return result

    # Get admin user for counting resources
    admin_user = user if user.role == 'admin' and not user.admin else user.admin

    # Get current usage
    from ..models import Team, SimCard
    from ..models.shop_management_models import Shop, Product

    total_users = User.objects.filter(admin=admin_user).count()
    total_teams = Team.objects.filter(admin=admin_user).count()
    total_sim_cards = SimCard.objects.filter(admin=admin_user).count()
    total_shops = Shop.objects.filter(admin=admin_user).count()
    total_products = Product.objects.filter(admin=admin_user).count()

    rules = result['rules']

    # Calculate usage percentages
    def calc_usage(current, max_allowed):
        if max_allowed == -1:  # Unlimited
            return {'current': current, 'max': 'unlimited', 'percentage': 0, 'is_limit_reached': False}
        percentage = (current / max_allowed * 100) if max_allowed > 0 else 0
        return {
            'current': current,
            'max': max_allowed,
            'percentage': round(percentage, 2),
            'is_limit_reached': current >= max_allowed
        }

    result['usage'] = {
        'users': calc_usage(total_users, rules['max_users']),
        'teams': calc_usage(total_teams, rules['max_teams']),
        'sim_cards': calc_usage(total_sim_cards, rules['max_sim_cards']),
        'shops': calc_usage(total_shops, rules['max_shops']),
        'products': calc_usage(total_products, rules['max_products']),
    }

    return result


# ==================== SUBSCRIPTION RULES HELPERS ====================

def get_subscription_rules(user):
    """
    Get subscription rules for current user
    """
    subscription_data = get_user_subscription(user)
    return subscription_data['rules']


def check_limit(user, resource_type):
    """
    Check if user has reached limit for a specific resource
    resource_type: 'users', 'teams', 'sim_cards', 'shops', 'products', 'upload_size'
    """
    rules = get_subscription_rules(user)
    admin_user = user if user.role == 'admin' and not user.admin else user.admin

    # Map resource types to rule keys
    resource_map = {
        'users': ('max_users', lambda: User.objects.filter(admin=admin_user).count()),
        'teams': ('max_teams', lambda: __import__('ssm.models', fromlist=['Team']).Team.objects.filter(admin=admin_user).count()),
        'sim_cards': ('max_sim_cards', lambda: __import__('ssm.models', fromlist=['SimCard']).SimCard.objects.filter(admin=admin_user).count()),
        'shops': ('max_shops', lambda: __import__('ssm.models.shop_management_models', fromlist=['Shop']).Shop.objects.filter(admin=admin_user).count()),
        'products': ('max_products', lambda: __import__('ssm.models.shop_management_models', fromlist=['Product']).Product.objects.filter(admin=admin_user).count()),
    }

    if resource_type not in resource_map:
        return {'error': f'Invalid resource type: {resource_type}'}

    rule_key, count_func = resource_map[resource_type]
    max_allowed = rules.get(rule_key, 0)

    # -1 means unlimited
    if max_allowed == -1:
        return {
            'resource': resource_type,
            'can_add': True,
            'current': count_func(),
            'max': 'unlimited',
            'reason': None
        }

    current_count = count_func()
    can_add = current_count < max_allowed

    return {
        'resource': resource_type,
        'can_add': can_add,
        'current': current_count,
        'max': max_allowed,
        'reason': None if can_add else f'You have reached the maximum limit of {max_allowed} {resource_type} for your subscription plan'
    }


def check_feature(user, feature_name):
    """
    Check if user's subscription includes a specific feature
    """
    rules = get_subscription_rules(user)
    features = rules.get('features', {})

    return {
        'feature': feature_name,
        'enabled': features.get(feature_name, False)
    }


def get_max_upload_size(user):
    """
    Get maximum upload size in MB for user's subscription
    """
    rules = get_subscription_rules(user)
    return {
        'max_upload_size_mb': rules.get('max_upload_size_mb', 5),
        'max_upload_size_bytes': rules.get('max_upload_size_mb', 5) * 1024 * 1024
    }


def get_max_allowable_serials(user):
    """
    Get maximum allowable serial numbers per upload for user's subscription
    """
    rules = get_subscription_rules(user)
    max_serials = rules.get('max_allowable_serials', 100)

    return {
        'max_allowable_serials': max_serials,
        'is_unlimited': max_serials == -1
    }


def get_max_allowable_users(user):
    """
    Get maximum allowable users for user's subscription
    """
    rules = get_subscription_rules(user)
    max_users = rules.get('max_users', 5)
    admin_user = user if user.role == 'admin' and not user.admin else user.admin
    current_users = User.objects.filter(admin=admin_user).count()

    return {
        'max_users': max_users,
        'current_users': current_users,
        'can_add_more': max_users == -1 or current_users < max_users,
        'is_unlimited': max_users == -1
    }


# ==================== SUBSCRIPTION HISTORY ====================

def get_subscription_history(user):
    """
    Get subscription history for user
    """
    admin_user = user if user.role == 'admin' and not user.admin else user.admin

    subscriptions = Subscription.objects.filter(
        user=admin_user
    ).order_by('-created_at')

    result = []
    for sub in subscriptions:
        try:
            plan = SubscriptionPlan.objects.get(id=sub.plan_id)
            plan_name = plan.name
        except SubscriptionPlan.DoesNotExist:
            plan_name = 'Unknown Plan'

        result.append({
            'id': str(sub.id),
            'plan_name': plan_name,
            'plan_id': str(sub.plan_id),
            'status': sub.status,
            'starts_at': sub.starts_at.isoformat(),
            'expires_at': sub.expires_at.isoformat(),
            'payment_reference': sub.payment_reference,
            'is_trial': sub.is_trial,
            'created_at': sub.created_at.isoformat()
        })

    return result


# ==================== SUBSCRIPTION CREATION ====================

def create_subscription(user, subscription_data):
    """
    Create a new subscription for user
    Expected data: {
        'plan_id': str,
        'payment_reference': str,
        'duration_months': int (default: 1),
        'is_trial': bool (default: False),
        'trial_days': int (optional)
    }
    """
    # Only admins can create subscriptions for their account
    if user.role != 'admin' or user.admin:
        raise PermissionError("Only admin users can create subscriptions")

    # Validate plan exists
    try:
        plan = SubscriptionPlan.objects.get(id=subscription_data['plan_id'], is_active=True)
    except SubscriptionPlan.DoesNotExist:
        raise ValueError(f"Subscription plan with ID {subscription_data['plan_id']} not found")

    # Calculate dates
    now = timezone.now()
    duration_months = subscription_data.get('duration_months', 1)
    expires_at = now + timedelta(days=30 * duration_months)

    is_trial = subscription_data.get('is_trial', False)
    trial_days = subscription_data.get('trial_days', 0)
    trial_ends_at = now + timedelta(days=trial_days) if is_trial and trial_days > 0 else None

    # Create subscription
    subscription = Subscription.objects.create(
        user=user,
        plan_id=subscription_data['plan_id'],
        status='active',
        starts_at=now,
        expires_at=expires_at,
        payment_reference=subscription_data.get('payment_reference'),
        auto_renew=subscription_data.get('auto_renew', False),
        is_trial=is_trial,
        trial_ends_at=trial_ends_at,
        trial_days=trial_days if is_trial else None
    )

    return {
        'success': True,
        'subscription_id': str(subscription.id),
        'plan_name': plan.name,
        'starts_at': subscription.starts_at.isoformat(),
        'expires_at': subscription.expires_at.isoformat()
    }


# Export all functions for RPC registration
functions = {
    # Subscription plans
    'sb_get_all_plans': get_all_subscription_plans,
    'sb_get_plan': get_subscription_plan,

    # User subscriptions
    'sb_get_subscription': get_user_subscription,
    'sb_get_status': get_subscription_status,
    'sb_get_history': get_subscription_history,
    'sb_create_subscription': create_subscription,

    # Subscription rules and limits
    'sb_get_rules': get_subscription_rules,
    'sb_check_limit': check_limit,
    'sb_check_feature': check_feature,
    'sb_get_max_upload_size': get_max_upload_size,
    'sb_get_max_allowable_serials': get_max_allowable_serials,
    'sb_get_max_allowable_users': get_max_allowable_users,
}