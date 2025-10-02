# =============================================================================
# ADMIN AUTHENTICATION ENDPOINTS
# =============================================================================
import json
import logging
import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ssm.models import User, PasswordResetRequest
from ssm.utilities import supabase_response, get_user_from_token, require_ssm_api_key, serialize_user
from ssm.email_service import EmailService

logger = logging.getLogger(__name__)

SSMAuthUser = get_user_model()


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_ssm_api_key
def auth_admin_users(request):
    """GET/POST /auth/admin/users"""

    if request.method == 'GET':
        # List users
        try:
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 50))

            users = User.objects.all()
            total_count = users.count()

            # Pagination
            start = (page - 1) * per_page
            end = start + per_page
            users_page = users[start:end]

            serialized_users = [serialize_user(u) for u in users_page]

            return supabase_response(data={
                'users': serialized_users,
                'count': total_count
            })

        except Exception as e:
            logger.error(f"Admin list users error: {e}")
            return supabase_response(
                error={'message': str(e)},
                status=500
            )

    elif request.method == 'POST':
        # Create user
        try:
            data = json.loads(request.body)
            email = data.get('email')
            password = data.get('password')
            email_confirm = data.get('email_confirm', True)
            user_metadata = data.get('user_metadata', {})
            app_metadata = data.get('app_metadata', {"login_with": "email"})

            if not email or not password:
                return supabase_response(
                    error={'message': 'Email and password are required'},
                    status=400
                )

            # Create Django user
            auth_user = SSMAuthUser.objects.create_user(
                username=email,
                email=email,
                password=password,
                email_confirmed=email_confirm,
                raw_user_meta_data=user_metadata,
                raw_app_meta_data=app_metadata,
            )

            return supabase_response(data=serialize_user(auth_user))

        except json.JSONDecodeError:
            return supabase_response(
                error={'message': 'Invalid JSON'},
                status=400
            )
        except Exception as e:
            logger.error(f"Admin create user error: {e}")
            return supabase_response(
                error={'message': str(e)},
                status=500
            )

    return supabase_response(error=404)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@require_ssm_api_key
def auth_admin_user_by_id(request, user_id):
    """GET/PUT/DELETE /auth/admin/users/{user_id}"""

    try:
        target_user = SSMAuthUser.objects.get(id=user_id)
    except SSMAuthUser.DoesNotExist:
        return supabase_response(
            error={'message': 'User not found'},
            status=404
        )

    if request.method == 'GET':
        return supabase_response(data=serialize_user(target_user))

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)

            # Update fields
            if 'email' in data:
                target_user.email = data['email']
                target_user.email = data['email']
                target_user.save()

            if 'password' in data:
                target_user.set_password(data['password'])
                target_user.save()

            if 'user_metadata' in data:
                metadata = data['user_metadata']
                if 'full_name' in metadata:
                    target_user.full_name = metadata['full_name']
                if 'phone' in metadata:
                    target_user.phone_number = metadata['phone']
                if 'username' in metadata:
                    target_user.username = metadata['username']
                if 'role' in metadata:
                    target_user.role = metadata['role']

            target_user.save()
            return supabase_response(data=serialize_user(target_user))

        except json.JSONDecodeError:
            return supabase_response(
                error={'message': 'Invalid JSON'},
                status=400
            )

    elif request.method == 'DELETE':
        try:
            # Delete the auth user (this will cascade to custom user)
            target_user.delete()
            return supabase_response(data=serialize_user(target_user))
        except Exception as e:
            logger.error(f"Admin delete user error: {e}")
            return supabase_response(
                error={'message': str(e)},
                status=500
            )
    return supabase_response(status=404)


@csrf_exempt
@require_http_methods(["POST"])
@require_ssm_api_key
def auth_admin_generate_link(request):
    """POST /auth/admin/generate_link"""

    try:
        data = json.loads(request.body)
        link_type = data.get('type')
        email = data.get('email')
        redirect_to = data.get('options').get("redirectTo", "")

        if link_type == 'recovery':
            # Generate password reset link
            try:
                auth_user = SSMAuthUser.objects.get(email=email)

                reset_request = PasswordResetRequest.objects.create(
                    user=auth_user,
                    token=secrets.token_urlsafe(32),
                    expires_at=timezone.now() + timezone.timedelta(hours=1)
                )

                # Build full reset link
                reset_link = f"{redirect_to}?token={reset_request.token}&type=recovery"

                # Send email via Resend
                email_sent = EmailService.send_password_reset_email(
                    email=email,
                    reset_token=reset_request.token,
                    reset_link=reset_link
                )

                if not email_sent:
                    logger.warning(f"Failed to send password reset email to {email}")

                return supabase_response(data={
                    'user': serialize_user(auth_user),
                    'properties': {
                        'action_link': f"/auth/reset-password?token={reset_request.token}",
                        'email_otp': reset_request.token,
                        'verification_type': 'recovery',
                        'email_sent': email_sent
                    }
                })

            except (SSMAuthUser.DoesNotExist, User.DoesNotExist):
                return supabase_response(
                    error={'message': 'User not found'},
                    status=404
                )

        return supabase_response(
            error={'message': f'Link type {link_type} not implemented'},
            status=400
        )

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Admin generate link error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
@require_ssm_api_key
def auth_admin_invite(request):
    """POST /auth/admin/invite"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        user_data = data.get('data', {})

        if not email:
            return supabase_response(
                error={'message': 'Email is required'},
                status=400
            )

        # Create invitation token (you might want a separate model for this)
        invitation_token = secrets.token_urlsafe(32)

        # For now, just return the invitation data
        # In a real app, you'd save this invitation and send an email

        return supabase_response(data={
            'user': {
                'email': email,
                'invitation_token': invitation_token
            }
        })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Admin invite error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )
