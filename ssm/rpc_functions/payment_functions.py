"""
Payment and subscription RPC functions
"""
import uuid
import requests
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from ..models import PaymentRequest, Subscription

# Define plans on backend to prevent tampering
PLANS = {
    'starter': {
        'name': 'Starter',
        'price': {'monthly': 2500, 'yearly': 2000}
    },
    'business': {
        'name': 'Business',
        'price': {'monthly': 5000, 'yearly': 4200}
    },
    'professional': {
        'name': 'Professional',
        'price': {'monthly': 8500, 'yearly': 7000}
    },
    'enterprise': {
        'name': 'Enterprise',
        'price': {'monthly': 15000, 'yearly': 12000}
    }
}


def calculate_amount(plan_id, billing_cycle):
    """Calculate correct amount with tax"""
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError('Invalid plan ID')

    base_price = plan['price'].get(billing_cycle)
    if not base_price:
        raise ValueError('Invalid billing cycle')

    months = 12 if billing_cycle == 'yearly' else 1
    subtotal = base_price * months
    tax = subtotal * 0.16  # 16% VAT in Kenya

    return round(subtotal + tax)


def create_payment_order(user, **order_data):
    """Create a new payment order with external payment gateway"""
    plan_id = order_data.get('plan_id')
    billing_cycle = order_data.get('billing_cycle', 'monthly')
    customer_email = order_data.get('customer_email')
    customer_phone = order_data.get('customer_phone')
    customer_name = order_data.get('customer_name')

    # Validate required fields
    if not all([plan_id, customer_email, customer_phone]):
        return {'success': False, 'error': 'Please provide all required information'}

    # Validate plan and billing cycle
    if plan_id not in PLANS:
        return {'success': False, 'error': 'Selected plan is not available'}

    if billing_cycle not in ['monthly', 'yearly']:
        return {'success': False, 'error': 'Please select a valid billing cycle'}

    try:
        # Calculate correct amount
        amount = calculate_amount(plan_id, billing_cycle)
        plan = PLANS[plan_id]
        reference = f"ORDER-{uuid.uuid4().hex[:8].upper()}"

        # Create payment order with external gateway (Nagele Pay)
        gateway_payload = {
            "amount": amount,
            "currency": "KES",
            "description": f"SSM Platform - {plan['name']} ({billing_cycle})",
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "success_url": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')}/checkout/success",
            "cancel_url": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')}/checkout/cancel",
            "returnUrl": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')}/checkout/success",
            "webhook_url": f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/api/payment/webhook"
        }

        headers = {
            "X-API-Key": getattr(settings, 'NAGELE_PAY_API_KEY', ''),
            "X-API-Secret": getattr(settings, 'NAGELE_PAY_API_SECRET', ''),
            "Content-Type": "application/json"
        }

        response = requests.post(
            # 'https://nagele-pay.nagelecommunication.com/api/v1/orders/register',
            'http://localhost:8085/api/v1/orders/register',
            json=gateway_payload,
            headers=headers,
            timeout=30
        )

        if not response.ok:
            return {'success': False, 'error': 'Payment service is temporarily unavailable. Please try again later.'}

        gateway_data = response.json()
        
        # Create local payment request after successful gateway response
        order = PaymentRequest.objects.create(
            user=user,
            plan_id=plan_id,
            amount=amount,
            phone_number=customer_phone,
            reference=reference,
            provider_id=gateway_data.get('orderId'),
            checkout_url=gateway_data.get('formUrl'),
            status='pending'
        )

        return {
            'success': True,
            'order_id': str(order.id),
            'provider_order_id': gateway_data.get('orderId'),
            'checkout_url': gateway_data.get('formUrl'),
            'expires_at': gateway_data.get('expiresAt'),
            'amount': amount,
            'plan_name': plan['name'],
            'billing_cycle': billing_cycle
        }

    except requests.RequestException:
        return {'success': False, 'error': 'Unable to connect to payment service. Please check your internet connection and try again.'}
    except Exception:
        return {'success': False, 'error': 'Something went wrong. Please try again or contact support if the problem persists.'}


def complete_payment_order(user, order_id, payment_data):
    """Complete a payment order and create subscription"""
    try:
        order = PaymentRequest.objects.get(id=order_id, user=user)

        if order.status != 'pending':
            return {'success': False, 'error': 'Order already processed'}

        # Update order status
        order.status = 'completed'
        order.transaction_id = payment_data.get('transaction_id')
        order.payment_method = payment_data.get('payment_method')
        order.payment_details = payment_data.get('payment_details', {})
        order.save()

        # Calculate subscription dates based on plan
        start_date = timezone.now()
        # Default to monthly, can be extended based on plan_id logic
        end_date = start_date + timedelta(days=30)

        # Create subscription
        subscription = Subscription.objects.create(
            user=user,
            plan_id=uuid.UUID(order.plan_id) if order.plan_id else uuid.uuid4(),
            status='active',
            starts_at=start_date,
            expires_at=end_date,
            payment_reference=order.transaction_id,
            auto_renew=True
        )

        return {
            'success': True,
            'subscription_id': str(subscription.id),
            'plan_id': order.plan_id,
            'expires_at': end_date.isoformat()
        }

    except PaymentRequest.DoesNotExist:
        return {'success': False, 'error': 'Payment order not found'}
    except Exception:
        return {'success': False, 'error': 'Unable to complete payment. Please contact support.'}


def get_user_orders(user):
    """Get user's payment orders"""
    orders = PaymentRequest.objects.filter(user=user).order_by('-created_at')

    result = []
    for order in orders:
        result.append({
            'id': str(order.id),
            'reference': order.reference,
            'plan_id': order.plan_id,
            'plan_name': PLANS.get(order.plan_id, {}).get('name', 'Unknown'),
            'amount': float(order.amount),
            'status': order.status,
            'phone_number': order.phone_number,
            'transaction_id': order.transaction_id,
            'payment_method': order.payment_method,
            'created_at': order.created_at.isoformat()
        })

    return result


def get_available_plans(user):
    """Get all available subscription plans"""
    return PLANS


functions = {
    'get_available_plans': get_available_plans,
    'create_payment_order': create_payment_order,
    'complete_payment_order': complete_payment_order,
    'get_user_orders': get_user_orders
}
