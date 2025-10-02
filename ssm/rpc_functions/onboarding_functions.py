"""
Onboarding-related RPC functions
"""
from django.utils import timezone
from django.db import transaction
from ..models import User, AdminOnboarding, BusinessInfo


def get_onboarding_status(user, user_id):
    """
    Get onboarding status for a user (admin only)
    Returns onboarding progress and completion status
    """
    try:
        # Check if user is admin (has no admin field or admin points to self)
        is_admin = user.admin is None or user.admin_id == user.id

        if not is_admin:
            return {
                'is_admin': False,
                'requires_onboarding': False,
                'message': 'Only admins require onboarding'
            }

        # Get or create onboarding record
        onboarding, created = AdminOnboarding.objects.get_or_create(
            admin=user,
            defaults={
                'email_verified': False,
                'profile_completed': False,
                'business_info_completed': False,
                'system_tour_completed': False,
                'onboarding_completed': False,
                'billing_active': False
            }
        )

        return {
            'is_admin': True,
            'requires_onboarding': True,
            'onboarding_completed': onboarding.onboarding_completed,
            'billing_active': onboarding.billing_active,
            'steps': {
                'email_verified': {
                    'completed': onboarding.email_verified,
                    'completed_at': onboarding.email_verified_at.isoformat() if onboarding.email_verified_at else None
                },
                'profile_completed': {
                    'completed': onboarding.profile_completed,
                    'completed_at': onboarding.profile_completed_at.isoformat() if onboarding.profile_completed_at else None
                },
                'business_info_completed': {
                    'completed': onboarding.business_info_completed,
                    'completed_at': onboarding.business_info_completed_at.isoformat() if onboarding.business_info_completed_at else None
                },
                'system_tour_completed': {
                    'completed': onboarding.system_tour_completed,
                    'completed_at': onboarding.system_tour_completed_at.isoformat() if onboarding.system_tour_completed_at else None
                }
            },
            'billing_start_date': onboarding.billing_start_date.isoformat() if onboarding.billing_start_date else None,
            'created_at': onboarding.created_at.isoformat(),
            'updated_at': onboarding.updated_at.isoformat()
        }
    except User.DoesNotExist:
        raise ValueError(f"User with id {user_id} not found")


def update_onboarding_step(user,user_id, step_name):
    """
    Mark a specific onboarding step as completed
    Valid steps: email_verified, profile_completed, business_info_completed, system_tour_completed
    """
    valid_steps = ['email_verified', 'profile_completed', 'business_info_completed', 'system_tour_completed']

    if step_name not in valid_steps:
        raise ValueError(f"Invalid step name. Must be one of: {', '.join(valid_steps)}")

    try:
        # Check if user is admin
        is_admin = user.admin is None or user.admin_id == user.id
        if not is_admin:
            raise PermissionError("Only admins can update onboarding status")

        onboarding, created = AdminOnboarding.objects.get_or_create(admin=user)

        # Update the specific step
        setattr(onboarding, step_name, True)
        setattr(onboarding, f"{step_name}_at", timezone.now())
        onboarding.save()

        return {
            'success': True,
            'step': step_name,
            'completed_at': timezone.now().isoformat(),
            'message': f"Step '{step_name}' marked as completed"
        }
    except User.DoesNotExist:
        raise ValueError(f"User with id {user_id} not found")


def save_business_info(user, user_id, business_data):
    """
    Save or update business information for admin user
    Expected business_data fields:
    - business_name (required)
    - business_type
    - registration_number
    - kra_pin
    - physical_address
    - county
    - town
    - contact_person
    - contact_phone
    - contact_email
    - notes
    """
    try:
        # Check if user is admin
        is_admin = user.admin is None or user.admin_id == user.id
        if not is_admin:
            raise PermissionError("Only admins can save business information")

        if not business_data.get('dealer_code'):
            raise ValueError("business_name is required")

        with transaction.atomic():
            # Create or update business info
            business_info, created = BusinessInfo.objects.update_or_create(
                admin=user,
                defaults={
                    'dealer_code': business_data.get('dealer_code'),
                    'contact_phone': business_data.get('contact_phone'),
                    'notes': business_data.get('notes')
                }
            )

            # Mark business_info_completed step as done
            onboarding, _ = AdminOnboarding.objects.get_or_create(admin=user)
            onboarding.business_info_completed = True
            onboarding.business_info_completed_at = timezone.now()
            onboarding.save()

        return {
            'success': True,
            'business_info_id': str(business_info.id),
            'created': created,
            'message': 'Business information saved successfully'
        }
    except User.DoesNotExist:
        raise ValueError(f"User with id {user_id} not found")


def get_business_info(user,user_id):
    """Get business information for admin user"""
    try:
        user = User.objects.get(id=user_id)

        # Check if user is admin
        is_admin = user.admin is None or user.admin_id == user.id
        if not is_admin:
            raise PermissionError("Only admins have business information")

        try:
            business_info = BusinessInfo.objects.get(admin=user)
            return {
                'id': str(business_info.id),
                'dealer_code': business_info.dealer_code,
                'contact_phone': business_info.contact_phone,
                'notes': business_info.notes,
                'created_at': business_info.created_at.isoformat(),
                'updated_at': business_info.updated_at.isoformat()
            }
        except BusinessInfo.DoesNotExist:
            return None
    except User.DoesNotExist:
        raise ValueError(f"User with id {user_id} not found")


def complete_onboarding(user,user_id):
    """
    Complete onboarding process and activate billing
    Marks all steps as complete and starts billing from current date
    """
    try:
        # Check if user is admin
        is_admin = user.admin is None or user.admin_id == user.id
        if not is_admin:
            raise PermissionError("Only admins can complete onboarding")

        with transaction.atomic():
            onboarding, _ = AdminOnboarding.objects.get_or_create(admin=user)

            # Mark all steps as completed if not already
            now = timezone.now()
            if not onboarding.email_verified:
                onboarding.email_verified = True
                onboarding.email_verified_at = now
            if not onboarding.profile_completed:
                onboarding.profile_completed = True
                onboarding.profile_completed_at = now
            if not onboarding.business_info_completed:
                onboarding.business_info_completed = True
                onboarding.business_info_completed_at = now
            if not onboarding.system_tour_completed:
                onboarding.system_tour_completed = True
                onboarding.system_tour_completed_at = now

            # Mark onboarding as complete and activate billing
            onboarding.onboarding_completed = True
            onboarding.onboarding_completed_at = now
            onboarding.billing_active = True
            onboarding.billing_start_date = now
            onboarding.save()

        return {
            'success': True,
            'onboarding_completed': True,
            'billing_active': True,
            'billing_start_date': now.isoformat(),
            'message': 'Onboarding completed successfully. Billing is now active.'
        }
    except User.DoesNotExist:
        raise ValueError(f"User with id {user_id} not found")


# Register functions
functions = {
    'get_onboarding_status': get_onboarding_status,
    'update_onboarding_step': update_onboarding_step,
    'save_business_info': save_business_info,
    'get_business_info': get_business_info,
    'complete_onboarding': complete_onboarding,
}
