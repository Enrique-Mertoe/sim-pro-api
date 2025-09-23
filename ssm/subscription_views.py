"""
Supabase-compatible API views to work with the SDK
These views provide the exact API interface that the solobase-js SDK expects
"""
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib.auth import get_user_model

from .utilities import get_user_from_token, supabase_response

SSMAuthUser = get_user_model()
import logging

from .models import Subscription

logger = logging.getLogger(__name__)


# =============================================================================
# SUBSCRIPTION ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def check_user_subscription(request):
    """GET /api/subscriptions/check - Check user's subscription status"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        # Get user's active subscriptions
        subscriptions = Subscription.objects.filter(
            user=user,
            status='active',
            starts_at__lte=timezone.now(),
            expires_at__gt=timezone.now()
        ).select_related('user').order_by('-created_at')

        # Serialize subscriptions
        subscription_data = []
        for subscription in subscriptions:
            subscription_data.append({
                'id': str(subscription.id),
                'user_id': str(subscription.user.id),
                'plan_id': str(subscription.plan_id),
                'status': subscription.status,
                'starts_at': subscription.starts_at.isoformat(),
                'expires_at': subscription.expires_at.isoformat(),
                'payment_reference': subscription.payment_reference,
                'auto_renew': subscription.auto_renew,
                'cancellation_date': subscription.cancellation_date.isoformat() if subscription.cancellation_date else None,
                'cancellation_reason': subscription.cancellation_reason,
                'is_trial': subscription.is_trial,
                'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
                'trial_days': subscription.trial_days,
                'created_at': subscription.created_at.isoformat(),
                'updated_at': subscription.updated_at.isoformat(),
            })

        return supabase_response(data={
            'subscriptions': subscription_data,
            'has_active_subscription': len(subscription_data) > 0,
            'user_id': str(user.id)
        })

    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def create_subscription(request):
    """POST /api/subscriptions/create - Create a new subscription"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        data = json.loads(request.body)
        plan_id = data.get('plan_id')
        starts_at = data.get('starts_at')
        expires_at = data.get('expires_at')
        payment_reference = data.get('payment_reference')
        auto_renew = data.get('auto_renew', False)
        is_trial = data.get('is_trial', False)
        trial_ends_at = data.get('trial_ends_at')
        trial_days = data.get('trial_days')

        if not all([plan_id, starts_at, expires_at]):
            return supabase_response(
                error={'message': 'plan_id, starts_at, and expires_at are required'},
                status=400
            )

        # Parse datetime strings
        try:
            starts_at = timezone.datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
            expires_at = timezone.datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if trial_ends_at:
                trial_ends_at = timezone.datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))
        except ValueError as e:
            return supabase_response(
                error={'message': f'Invalid datetime format: {str(e)}'},
                status=400
            )

        # Create subscription
        subscription = Subscription.objects.create(
            user=user,
            plan_id=plan_id,
            status='active',
            starts_at=starts_at,
            expires_at=expires_at,
            payment_reference=payment_reference,
            auto_renew=auto_renew,
            is_trial=is_trial,
            trial_ends_at=trial_ends_at,
            trial_days=trial_days
        )

        return supabase_response(data={
            'id': str(subscription.id),
            'user_id': str(subscription.user.id),
            'plan_id': str(subscription.plan_id),
            'status': subscription.status,
            'starts_at': subscription.starts_at.isoformat(),
            'expires_at': subscription.expires_at.isoformat(),
            'payment_reference': subscription.payment_reference,
            'auto_renew': subscription.auto_renew,
            'is_trial': subscription.is_trial,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'trial_days': subscription.trial_days,
            'created_at': subscription.created_at.isoformat(),
            'updated_at': subscription.updated_at.isoformat(),
        }, status=201)

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Create subscription error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def cancel_subscription(request, subscription_id):
    """POST /api/subscriptions/{subscription_id}/cancel - Cancel a subscription"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        try:
            subscription = Subscription.objects.get(id=subscription_id, user=user)
        except Subscription.DoesNotExist:
            return supabase_response(
                error={'message': 'Subscription not found'},
                status=404
            )

        data = json.loads(request.body)
        cancellation_reason = data.get('cancellation_reason', '')

        # Update subscription
        subscription.status = 'cancelled'
        subscription.cancellation_date = timezone.now()
        subscription.cancellation_reason = cancellation_reason
        subscription.auto_renew = False
        subscription.save()

        return supabase_response(data={
            'id': str(subscription.id),
            'user_id': str(subscription.user.id),
            'plan_id': str(subscription.plan_id),
            'status': subscription.status,
            'starts_at': subscription.starts_at.isoformat(),
            'expires_at': subscription.expires_at.isoformat(),
            'payment_reference': subscription.payment_reference,
            'auto_renew': subscription.auto_renew,
            'cancellation_date': subscription.cancellation_date.isoformat(),
            'cancellation_reason': subscription.cancellation_reason,
            'is_trial': subscription.is_trial,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'trial_days': subscription.trial_days,
            'created_at': subscription.created_at.isoformat(),
            'updated_at': subscription.updated_at.isoformat(),
        })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Cancel subscription error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )
