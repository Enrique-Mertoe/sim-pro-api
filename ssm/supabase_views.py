"""
Supabase-compatible API views to work with the SDK
These views provide the exact API interface that the solobase-js SDK expects
"""
import json
import uuid
import os
import secrets
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.forms import model_to_dict
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone


from .email_service import EmailService
from .select_parser import build_response_with_select
from django.contrib.auth import get_user_model

from .utilities import supabase_response, get_user_from_token, serialize_user, MODEL_MAP

SSMAuthUser = get_user_model()
from .authentication import create_user_with_supabase_password, verify_password_format
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token
import logging

from .models import (
    User, PasswordResetRequest, AdminOnboarding
)

logger = logging.getLogger(__name__)


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def auth_signup(request):
    """POST /api/auth/signup"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        # get data not options.data
        user_metadata = data.get('data', {})

        if not email or not password:
            return supabase_response(
                error={'message': 'Email and password are required'},
                status=400
            )

        # Check if user already exists
        if SSMAuthUser.objects.filter(email=email).exists():
            return supabase_response(
                error={'message': 'User already exists'},
                status=400
            )

        with transaction.atomic():
            # Generate confirmation token
            confirmation_token = secrets.token_urlsafe(32)

            # Create Django auth user
            auth_user = SSMAuthUser.objects.create_user(
                username=email,
                email=email,
                password=password
            )

            # Set email verification fields
            auth_user.email_confirmed = False
            auth_user.confirmation_token = confirmation_token
            auth_user.confirmation_sent_at = timezone.now()
            auth_user.save()

            # Create token
            token, created = Token.objects.get_or_create(user=auth_user)

            # Create SSM user profile
            User.objects.create(
                id=str(auth_user.id),
                email=email,
                full_name=user_metadata.get('full_name', ''),
                id_number=user_metadata.get('id_number', ''),
                id_front_url=user_metadata.get('id_front_url', ''),
                id_back_url=user_metadata.get('id_back_url', ''),
                phone_number=user_metadata.get('phone_number', ''),
                role="admin",
                status='ACTIVE',
                auth_user=auth_user,
                is_active=True
            )

            # Build verification link
            frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:4200')
            verification_link = f"{frontend_url}/auth/confirm-email?token={confirmation_token}"

            # Send email verification
            try:
                EmailService.send_email_verification(
                    email=email,
                    verification_token=confirmation_token,
                    verification_link=verification_link,
                    user_name=user_metadata.get('full_name', email)
                )
                logger.info(f"Verification email sent to {email}")
            except Exception as email_error:
                logger.error(f"Failed to send verification email to {email}: {email_error}")
                # Don't fail signup if email fails

        return supabase_response(data={
            'user': serialize_user(auth_user),
            'session': {
                'access_token': token.key,
                'token_type': 'bearer'
            }
        })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth signup error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_login(request):
    """POST /api/auth/login"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return supabase_response(
                error={'message': 'Email and password are required'},
                status=400
            )

        # Authenticate user
        auth_user = authenticate(username=email, password=password)
        if not auth_user:
            return supabase_response(
                error={'message': 'Invalid credentials'},
                status=401
            )

        # Get or create token
        token, created = Token.objects.get_or_create(user=auth_user)

        # Get SSM user profile
        try:
            ssm_user = User.objects.get(auth_user=auth_user)
        except User.DoesNotExist:
            return supabase_response(
                error={'message': 'User profile not found'},
                status=404
            )
        user = serialize_user(auth_user)
        return supabase_response(data={
            'user': user,
            'session': {
                'access_token': token.key,
                'token_type': 'bearer',
                'user': user
            }
        })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth login error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_logout(request):
    """POST /api/auth/logout"""
    try:
        user = get_user_from_token(request)
        if user:
            # Get token from either source
            token = None
            auth_header = request.META.get('HTTP_AUTHORIZATION')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
            else:
                token = request.COOKIES.get('sb-access-token')

            # Delete the token
            if token:
                Token.objects.filter(key=token).delete()

        response = supabase_response(error={'message': 'Logged out successfully'})

        # Clear cookies if they exist
        if request.COOKIES.get('sb-access-token'):
            response.delete_cookie('sb-access-token')
        if request.COOKIES.get('sb-refresh-token'):
            response.delete_cookie('sb-refresh-token')

        return response

    except Exception as e:
        logger.error(f"Auth logout error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def auth_me(request):
    """GET/PUT /auth/me"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Not authenticated'},
                status=401
            )

        if request.method == 'GET':
            return supabase_response(data=serialize_user(user.auth_user))

        elif request.method == 'PUT':
            # Handle user updates
            data = json.loads(request.body)
            auth_user = user.auth_user

            # Update password if provided
            if 'password' in data:
                auth_user.set_password(data['password'])
                auth_user.save()

            # Update email if provided
            if 'email' in data:
                new_email = data['email']
                # Check if email already exists
                if SSMAuthUser.objects.filter(email=new_email).exclude(id=auth_user.id).exists():
                    return supabase_response(
                        error={'message': 'Email already in use'},
                        status=400
                    )
                auth_user.email = new_email
                auth_user.username = new_email  # Keep username in sync
                user.email = new_email  # Update User model email too
                auth_user.save()
                user.save()

            # Update user metadata if provided
            if 'data' in data:
                metadata = data['data']

                # Update User model fields from metadata
                if 'full_name' in metadata:
                    user.full_name = metadata['full_name']
                if 'phone_number' in metadata:
                    user.phone_number = metadata['phone_number']
                if 'role' in metadata:
                    user.role = metadata['role']

                # Update auth user metadata
                auth_user.raw_user_meta_data.update(metadata)
                auth_user.save()
                user.save()

            return supabase_response(data=serialize_user(auth_user))
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=404
        )

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth me error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_reset_password(request):
    """POST /api/auth/reset-password"""
    try:
        data = json.loads(request.body)
        email = data.get('email')

        if not email:
            return supabase_response(
                error={'message': 'Email is required'},
                status=400
            )

        try:
            auth_user = SSMAuthUser.objects.get(email=email)
            ssm_user = User.objects.get(auth_user=auth_user)

            # Generate reset token
            import secrets
            reset_token = secrets.token_urlsafe(32)

            # Create password reset request
            from django.utils import timezone
            from datetime import timedelta

            PasswordResetRequest.objects.create(
                user=ssm_user,
                token=reset_token,
                expires_at=timezone.now() + timedelta(hours=24),
                used=False
            )

            # In a real application, you would send an email here
            # For now, we'll return the token (in production, don't do this!)

            return supabase_response(data={
                'message': 'Password reset email sent',
                'reset_token': reset_token  # Remove this in production!
            })

        except (SSMAuthUser.DoesNotExist, User.DoesNotExist):
            # Don't reveal if email exists or not for security
            return supabase_response(data={
                'message': 'Password reset email sent'
            })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth reset password error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_update_password(request):
    """POST /api/auth/update-password"""
    try:
        data = json.loads(request.body)

        # Check if this is a reset password request or authenticated update
        reset_token = data.get('reset_token')
        new_password = data.get('password')

        if not new_password:
            return supabase_response(
                error={'message': 'Password is required'},
                status=400
            )

        if reset_token:
            # Password reset flow
            try:
                from django.utils import timezone
                reset_request = PasswordResetRequest.objects.get(
                    token=reset_token,
                    used=False,
                    expires_at__gt=timezone.now()
                )

                # Update password
                auth_user = reset_request.user.auth_user
                auth_user.set_password(new_password)
                auth_user.save()

                # Mark reset request as used
                reset_request.used = True
                reset_request.save()

                # Create new token
                token, created = Token.objects.get_or_create(user=auth_user)

                return supabase_response(data={
                    'message': 'Password updated successfully',
                    'session': {
                        'access_token': token.key,
                        'token_type': 'bearer'
                    }
                })

            except PasswordResetRequest.DoesNotExist:
                return supabase_response(
                    error={'message': 'Invalid or expired reset token'},
                    status=400
                )
        else:
            # Authenticated password update
            user = get_user_from_token(request)
            if not user:
                return supabase_response(
                    error={'message': 'Authentication required'},
                    status=401
                )

            # Update password
            auth_user = user.auth_user
            auth_user.set_password(new_password)
            auth_user.save()

            return supabase_response(data={
                'message': 'Password updated successfully'
            })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth update password error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_refresh(request):
    """POST /api/auth/refresh"""
    try:
        data = json.loads(request.body)
        refresh_token = data.get('refresh_token')

        if not refresh_token:
            return supabase_response(
                error={'message': 'Refresh token is required'},
                status=400
            )

        # For now, return the same token (implement proper refresh logic later)
        try:
            # Validate the token exists and is valid
            token = Token.objects.get(key=refresh_token)
            user = token.user
            custom_user = get_object_or_404(User, auth_user=user)

            # Create new session data
            session_data = {
                'access_token': token.key,
                'refresh_token': token.key,
                'expires_in': 3600,
                'expires_at': int((timezone.now() + timezone.timedelta(hours=1)).timestamp()),
                'token_type': 'bearer',
                'user': serialize_user(custom_user)
            }

            return supabase_response(data=session_data)

        except Token.DoesNotExist:
            return supabase_response(
                error={'message': 'Invalid refresh token'},
                status=401
            )

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth refresh error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_recover(request):
    """POST /api/auth/recover"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        redirect_to = data.get("redirect_to", "")

        if not email:
            return supabase_response(
                error={'message': 'Email is required'},
                status=400
            )

        # Same logic as auth_reset_password but with different response format
        try:
            auth_user = SSMAuthUser.objects.get(email=email)

            # Generate reset token
            reset_request = PasswordResetRequest.objects.create(
                user=auth_user,
                token=secrets.token_urlsafe(32),
                expires_at=timezone.now() + timezone.timedelta(hours=1)
            )

            # Send password reset email
            from ssm.email_service import EmailService
            reset_link = f"{redirect_to}?token={reset_request.token}"
            EmailService.send_password_reset_email(email, reset_request.token, reset_link)
            logger.info(f"Password recovery requested for {email}. Token: {reset_request.token}")

            return supabase_response(data={})

        except (SSMAuthUser.DoesNotExist, User.DoesNotExist):
            # Don't reveal if user exists or not for security
            return supabase_response(data={})

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth recover error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


# =============================================================================
# STORAGE ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def storage_upload(request):
    """POST /api/storage/upload"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                {'message': 'Authentication required'},
                status=401
            )

        if 'file' not in request.FILES:
            return supabase_response(
                {'message': 'No file provided'},
                status=400
            )

        file = request.FILES['file']

        # Generate unique filename
        file_extension = file.name.split('.')[-1] if '.' in file.name else ''
        filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())

        # Save file
        file_path = default_storage.save(filename, ContentFile(file.read()))

        return supabase_response({
            'path': file_path,
            'fullPath': file_path,
            'id': filename
        })

    except Exception as e:
        logger.error(f"Storage upload error: {e}")
        return supabase_response(
            {'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["GET"])
def storage_download(request, filename):
    """GET /api/storage/{filename}"""
    try:
        if default_storage.exists(filename):
            file_path = default_storage.path(filename)
            return FileResponse(open(file_path, 'rb'))
        else:
            return JsonResponse({'error': 'File not found'}, status=404)

    except Exception as e:
        logger.error(f"Storage download error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# SUPABASE STORAGE API COMPATIBLE ENDPOINTS
# =============================================================================

@csrf_exempt
def storage_upload_to_bucket(request, bucket_name):
    """POST /storage/v1/object/{bucket_name} - Upload file to bucket"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        user = get_user_from_token(request)
        if not user:
            return JsonResponse({'error': {'message': 'Authentication required'}}, status=401)

        if 'file' not in request.FILES:
            return JsonResponse({'error': {'message': 'No file provided'}}, status=400)

        file = request.FILES['file']

        # Get file path from request body or use filename
        file_path = request.POST.get('path', file.name)

        # Generate unique filename if not provided
        if not file_path:
            file_extension = file.name.split('.')[-1] if '.' in file.name else ''
            file_path = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())

        # Save file to bucket directory
        bucket_dir = f"storage/{bucket_name}"
        os.makedirs(bucket_dir, exist_ok=True)

        full_path = os.path.join(bucket_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        return JsonResponse({
            'Key': file_path,
            'Id': str(uuid.uuid4()),
            'fullPath': file_path
        }, status=200)

    except Exception as e:
        logger.error(f"Storage upload error: {e}")
        return JsonResponse({'error': {'message': str(e)}}, status=500)


@csrf_exempt
def storage_file_operations(request, bucket_name, file_path):
    """Handle file operations: GET (download), PUT (upload), DELETE"""
    try:
        user = get_user_from_token(request)
        if not user:
            return JsonResponse({'error': {'message': 'Authentication required'}}, status=401)

        full_path = os.path.join(f"storage/{bucket_name}", file_path)

        if request.method == 'GET':
            # Download file
            if os.path.exists(full_path):
                return FileResponse(open(full_path, 'rb'))
            else:
                return JsonResponse({'error': {'message': 'File not found'}}, status=404)

        elif request.method == 'PUT':
            # Upload/update file
            if 'file' not in request.FILES and not request.body:
                return JsonResponse({'error': {'message': 'No file data provided'}}, status=400)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            if 'file' in request.FILES:
                file = request.FILES['file']
                with open(full_path, 'wb+') as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
            else:
                # Handle raw body upload
                with open(full_path, 'wb+') as destination:
                    destination.write(request.body)

            return JsonResponse({
                'Key': file_path,
                'Id': str(uuid.uuid4()),
                'fullPath': file_path
            }, status=200)

        elif request.method == 'DELETE':
            # Delete file
            if os.path.exists(full_path):
                os.remove(full_path)
                return JsonResponse({'message': 'File deleted successfully'}, status=200)
            else:
                return JsonResponse({'error': {'message': 'File not found'}}, status=404)

        else:
            return JsonResponse({'error': {'message': 'Method not allowed'}}, status=405)

    except Exception as e:
        logger.error(f"Storage file operation error: {e}")
        return JsonResponse({'error': {'message': str(e)}}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def storage_list_files(request, bucket_name):
    """GET /storage/v1/object/list/{bucket_name} - List files in bucket"""
    print("listddd")
    try:
        user = get_user_from_token(request)
        if not user:
            return JsonResponse({'error': {'message': 'Authentication required'}}, status=401)

        # Get parameters from query string for GET request
        prefix = request.GET.get('path', '')
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))

        bucket_dir = f"storage/{bucket_name}"
        if not os.path.exists(bucket_dir):
            return JsonResponse([], safe=False)

        files = []
        search_path = os.path.join(bucket_dir, prefix) if prefix else bucket_dir

        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, bucket_dir)

                stat = os.stat(file_path)
                files.append({
                    'name': relative_path,
                    'id': str(uuid.uuid4()),
                    'updated_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'last_accessed_at': datetime.fromtimestamp(stat.st_atime).isoformat(),
                    'metadata': {
                        'size': stat.st_size,
                        'mimetype': 'application/octet-stream'  # Default MIME type
                    }
                })

        # Apply pagination
        total_files = len(files)
        paginated_files = files[offset:offset + limit]

        return JsonResponse(paginated_files, safe=False)

    except Exception as e:
        logger.error(f"Storage list error: {e}")
        return JsonResponse({'error': {'message': str(e)}}, status=500)


@csrf_exempt
def storage_get_public_url(request, bucket_name, file_path):
    """GET /storage/v1/object/public/{bucket_name}/{file_path} - Get public URL"""
    try:
        # For this implementation, return the direct URL to the file
        # In production, you might want to check if the bucket is actually public
        base_url = request.build_absolute_uri('/').rstrip('/')
        public_url = f"{base_url}/api/storage/v1/object/{bucket_name}/{file_path}"

        return JsonResponse({
            'signedURL': public_url,
            'path': file_path,
            'token': None
        })

    except Exception as e:
        logger.error(f"Storage public URL error: {e}")
        return JsonResponse({'error': {'message': str(e)}}, status=500)


@csrf_exempt
def postgrest_handler(request, table_name):
    """
    Handle PostgREST-style requests from the SDK
    Converts PostgREST query parameters to Django ORM operations
    """
    try:
        # Check if table exists in our model map
        if table_name not in MODEL_MAP:
            return supabase_response(
                error={'message': f'Table {table_name} not found'},
                status=404
            )

        model = MODEL_MAP[table_name]

        if request.method == 'GET':
            return handle_postgrest_select(request, model, table_name)
        elif request.method == 'POST':
            return handle_postgrest_insert(request, model, table_name)
        elif request.method == 'PATCH':
            return handle_postgrest_update(request, model, table_name)
        elif request.method == 'DELETE':
            return handle_postgrest_delete(request, model, table_name)
        else:
            return supabase_response(
                error={'message': 'Method not allowed'},
                status=405
            )

    except Exception as e:
        logger.error(f"PostgREST handler error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


def apply_postgrest_filters(request, model, queryset=None):
    """
    Apply PostgREST filters to a queryset
    This centralizes the filtering logic used by SELECT, UPDATE, and DELETE operations
    """
    if queryset is None:
        queryset = model.objects.all()

    filtered_queryset = queryset

    # Apply filters (PostgREST format: column=operator.value)
    for key, value in request.GET.items():
        # Skip non-filter parameters
        if key in ['select', 'order', 'limit', 'offset']:
            continue

        # Check if the field exists on the model
        if not hasattr(model, key):
            print(f"Warning: Field '{key}' does not exist on model {model.__name__}")
            continue

        # Parse PostgREST filter format: column=operator.value
        if '.' in value:
            operator, filter_value = value.split('.', 1)
        else:
            # Default to equality if no operator specified
            operator, filter_value = 'eq', value

        # Skip null/undefined values for eq operator
        if operator == 'eq' and filter_value in ['undefined', 'null']:
            continue

        # Apply the appropriate filter based on operator
        try:
            if operator == 'eq':
                filtered_queryset = filtered_queryset.filter(**{key: filter_value})
            elif operator == 'neq':
                filtered_queryset = filtered_queryset.exclude(**{key: filter_value})
            elif operator == 'gt':
                filtered_queryset = filtered_queryset.filter(**{f'{key}__gt': filter_value})
            elif operator == 'gte':
                filtered_queryset = filtered_queryset.filter(**{f'{key}__gte': filter_value})
            elif operator == 'lt':
                filtered_queryset = filtered_queryset.filter(**{f'{key}__lt': filter_value})
            elif operator == 'lte':
                filtered_queryset = filtered_queryset.filter(**{f'{key}__lte': filter_value})
            elif operator == 'like':
                # PostgREST like with % wildcards
                filter_value = filter_value.replace('%', '')
                filtered_queryset = filtered_queryset.filter(**{f'{key}__icontains': filter_value})
            elif operator == 'ilike':
                # Case-insensitive like
                filter_value = filter_value.replace('%', '')
                filtered_queryset = filtered_queryset.filter(**{f'{key}__icontains': filter_value})
            elif operator == 'in':
                # PostgREST in format: column=in.(value1,value2,value3)
                values = filter_value.strip('()').split(',')
                values = [v.strip() for v in values]  # Clean whitespace
                filtered_queryset = filtered_queryset.filter(**{f'{key}__in': values})
            elif operator == 'is':
                # Handle null checks: column=is.null or column=is.true/false
                if filter_value.lower() == 'null':
                    filtered_queryset = filtered_queryset.filter(**{f'{key}__isnull': True})
                elif filter_value.lower() == 'true':
                    filtered_queryset = filtered_queryset.filter(**{key: True})
                elif filter_value.lower() == 'false':
                    filtered_queryset = filtered_queryset.filter(**{key: False})
            elif operator == 'not':
                # Handle .not() operator - negate various conditions
                if '.' in filter_value:
                    not_operator, not_value = filter_value.split('.', 1)

                    if not_operator == 'eq':
                        filtered_queryset = filtered_queryset.exclude(**{key: not_value})
                    elif not_operator == 'in':
                        # not.in.(value1,value2,value3)
                        values = not_value.strip('()').split(',')
                        values = [v.strip() for v in values]
                        filtered_queryset = filtered_queryset.exclude(**{f'{key}__in': values})
                    elif not_operator == 'like':
                        # not.like.%pattern%
                        not_value = not_value.replace('%', '')
                        filtered_queryset = filtered_queryset.exclude(**{f'{key}__icontains': not_value})
                    elif not_operator == 'ilike':
                        # not.ilike.%pattern%
                        not_value = not_value.replace('%', '')
                        filtered_queryset = filtered_queryset.exclude(**{f'{key}__icontains': not_value})
                    elif not_operator == 'is':
                        # not.is.null or not.is.true/false
                        if not_value.lower() == 'null':
                            filtered_queryset = filtered_queryset.filter(**{f'{key}__isnull': False})
                        elif not_value.lower() == 'true':
                            filtered_queryset = filtered_queryset.exclude(**{key: True})
                        elif not_value.lower() == 'false':
                            filtered_queryset = filtered_queryset.exclude(**{key: False})
                    elif not_operator == 'gt':
                        # not.gt.value becomes lte
                        filtered_queryset = filtered_queryset.filter(**{f'{key}__lte': not_value})
                    elif not_operator == 'gte':
                        # not.gte.value becomes lt
                        filtered_queryset = filtered_queryset.filter(**{f'{key}__lt': not_value})
                    elif not_operator == 'lt':
                        # not.lt.value becomes gte
                        filtered_queryset = filtered_queryset.filter(**{f'{key}__gte': not_value})
                    elif not_operator == 'lte':
                        # not.lte.value becomes gt
                        filtered_queryset = filtered_queryset.filter(**{f'{key}__gt': not_value})
                    else:
                        print(f"Warning: Unsupported not operator 'not.{not_operator}' for field '{key}'")
                else:
                    # Simple not.value (equivalent to not.eq.value)
                    filtered_queryset = filtered_queryset.exclude(**{key: filter_value})
            else:
                print(f"Warning: Unsupported operator '{operator}' for field '{key}'")
        except ValidationError as filter_error:
            print(f"Error applying filter {key}={value}: {filter_error}")
            return None, supabase_response(
                error={'message': filter_error.messages[0]},
                status=400
            )
        except Exception as filter_error:
            print(f"Error applying filter {key}={value}: {filter_error}")
            return None, supabase_response(error={
                'message': str(filter_error)
            }, status=400)

    return filtered_queryset, None


def handle_postgrest_select(request, model, table_name):
    """Handle PostgREST SELECT operations"""
    try:
        # Parse PostgREST query parameters
        select_columns = request.GET.get('select', '*')
        prefer_header = request.META.get('HTTP_PREFER', '')
        is_head_request = 'head' in prefer_header

        # Step 1: Apply filters using centralized filter logic
        filtered_queryset, filter_error = apply_postgrest_filters(request, model)
        if filter_error:
            return filter_error

        # Step 2: Calculate count BEFORE pagination (if requested)
        count_info = None
        if 'count=' in prefer_header:
            count_type = None
            if 'count=exact' in prefer_header:
                count_type = 'exact'
            elif 'count=planned' in prefer_header:
                count_type = 'planned'
            elif 'count=estimated' in prefer_header:
                count_type = 'estimated'

            if count_type:
                # Use the filtered queryset for count (before pagination)
                total_count = filtered_queryset.count()
                count_info = {
                    'count': total_count,
                    'type': count_type
                }

        # Step 3: Apply ordering and pagination to filtered queryset
        queryset = filtered_queryset

        # Handle ordering
        order_by = request.GET.get('order')
        if order_by:
            # PostgREST format: column.asc or column.desc
            if '.desc' in order_by:
                column = order_by.replace('.desc', '')
                if hasattr(model, column):
                    queryset = queryset.order_by(f'-{column}')
            elif '.asc' in order_by:
                column = order_by.replace('.asc', '')
                if hasattr(model, column):
                    queryset = queryset.order_by(column)
            else:
                # Default ascending order
                if hasattr(model, order_by):
                    queryset = queryset.order_by(order_by)

        # Handle limit and offset (pagination)
        limit = request.GET.get('limit')
        offset = request.GET.get('offset', 0)

        try:
            offset = int(offset) if offset else 0
            limit = int(limit) if limit else None

            if limit:
                queryset = queryset[offset:offset + limit]
            elif offset > 0:
                queryset = queryset[offset:]

        except ValueError:
            print(f"Warning: Invalid limit/offset values: limit={limit}, offset={offset}")

        # Step 4: Convert to list of dicts using advanced select parser
        data = []
        if not is_head_request:
            # Use advanced select parser for relationship support
            data = build_response_with_select(queryset, select_columns)

        # Handle head request (return only headers, no body)
        if is_head_request:
            response = JsonResponse({"data": None, "error": None}, safe=False)
            if count_info:
                response['Content-Range'] = f"*/{count_info['count']}"
            return response

        # Regular response
        response = supabase_response(data=data)

        if count_info:
            # Add count to Content-Range header (PostgREST standard)
            start = offset
            end = offset + len(data) - 1 if data else offset
            response['Content-Range'] = f"{start}-{end}/{count_info['count']}"

        return response

    except Exception as e:
        logger.error(f"PostgREST select error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


def handle_postgrest_insert(request, model, table_name):
    """Handle PostgREST INSERT operations"""
    try:
        data = json.loads(request.body)

        if isinstance(data, list):
            # Bulk insert
            created_items = []
            for item_data in data:
                item = model.objects.create(**item_data)
                created_items.append(serialize_model_instance(item))
            return supabase_response(data=created_items, status=201)
        else:
            # Single insert
            item = model.objects.create(**data)
            return supabase_response(data=[serialize_model_instance(item)], status=201)

    except Exception as e:
        logger.error(f"PostgREST insert error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


def handle_postgrest_update(request, model, table_name):
    """Handle PostgREST UPDATE operations"""
    try:
        data = json.loads(request.body)

        # Step 1: Apply filters using centralized filter logic
        filtered_queryset, filter_error = apply_postgrest_filters(request, model)
        if filter_error:
            return filter_error

        # Step 2: Store the items before update for returning them
        items_to_update = list(filtered_queryset.values('id'))

        # Validate that we have items to update
        if not items_to_update:
            return supabase_response(data=[])

        # Step 3: Update matching records
        updated_count = filtered_queryset.update(**data)

        # Step 4: Return updated records by fetching them again
        updated_queryset = model.objects.filter(id__in=[item['id'] for item in items_to_update])
        updated_items = []
        for item in updated_queryset:
            updated_items.append(serialize_model_instance(item))

        return supabase_response(data=updated_items)

    except json.JSONDecodeError as e:
        logger.error(f"PostgREST update JSON decode error: {e}")
        return supabase_response(
            error={'message': 'Invalid JSON in request body'},
            status=400
        )
    except Exception as e:
        logger.error(f"PostgREST update error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


def handle_postgrest_delete(request, model, table_name):
    """Handle PostgREST DELETE operations"""
    try:
        # Apply filters using centralized function
        queryset, error = apply_postgrest_filters(request, model)
        if error:
            return supabase_response(error=error, status=400)

        # Get items before deletion for response
        deleted_items = []
        for item in queryset:
            deleted_items.append(serialize_model_instance(item))

        # Delete matching records
        deleted_count, _ = queryset.delete()

        return supabase_response(data=deleted_items)

    except Exception as e:
        logger.error(f"PostgREST delete error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_verify_otp(request):
    """POST /api/auth/verify - Verify OTP token"""
    try:
        data = json.loads(request.body)
        token_hash = data.get('token_hash')
        verify_type = data.get('type')
        email = data.get('email')

        if not token_hash or not verify_type:
            return supabase_response(
                error={'message': 'token_hash and type are required'},
                status=400
            )

        if verify_type == 'recovery':
            # Handle password reset verification
            try:
                reset_request = PasswordResetRequest.objects.get(
                    token=token_hash,
                    used=False,
                    expires_at__gt=timezone.now()
                )

                user = reset_request.user
                auth_user = user.auth_user if hasattr(user, 'auth_user') else user

                # Generate new session for password update
                token, created = Token.objects.get_or_create(user=auth_user)

                session = {
                    'access_token': token.key,
                    'refresh_token': secrets.token_urlsafe(32),
                    'expires_in': 3600,  # 1 hour
                    'expires_at': int(timezone.now().timestamp()) + 3600,
                    'token_type': 'bearer',
                    'user': serialize_user(auth_user)
                }

                return supabase_response(data={
                    'user': serialize_user(auth_user),
                    'session': session
                })

            except PasswordResetRequest.DoesNotExist:
                return supabase_response(
                    error={'message': 'Invalid or expired reset token'},
                    status=400
                )

        else:
            return supabase_response(
                error={'message': f'Verification type {verify_type} not implemented'},
                status=400
            )

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Auth verify OTP error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST", "GET"])
def auth_verify_email(request):
    """POST/GET /api/auth/verify-email - Verify email address"""
    try:
        # Support both POST and GET for verification
        if request.method == 'POST':
            data = json.loads(request.body)
            token = data.get('token')
        else:  # GET
            token = request.GET.get('token')

        if not token:
            return supabase_response(
                error={'message': 'Verification token is required'},
                status=400
            )

        try:
            from django.db.models import Q
            # Find user with this confirmation token
            auth_user = SSMAuthUser.objects.filter(
                confirmation_token=token
            ).filter(
                Q(email_confirmed=False) | Q(email_confirmed_at=None)
            ).first()

            # Check if token is expired (24 hours)
            if auth_user and auth_user.confirmation_sent_at:
                expiry_time = auth_user.confirmation_sent_at + timedelta(hours=24)
                if timezone.now() > expiry_time:
                    return supabase_response(
                        error={'message': 'Verification token has expired. Please request a new one.'},
                        status=400
                    )

            # Mark email as confirmed
            auth_user.email_confirmed = True
            auth_user.email_confirmed_at = timezone.now()
            auth_user.confirmed_at = timezone.now()
            auth_user.confirmation_token = None  # Clear token after use
            auth_user.save()

            # Update onboarding status if user exists and is admin
            try:
                ssm_user = User.objects.get(auth_user=auth_user)
                # Check if user is admin (no admin or admin points to self)
                is_admin = ssm_user.admin is None or ssm_user.admin_id == ssm_user.id
                if is_admin:
                    onboarding, _ = AdminOnboarding.objects.get_or_create(admin=ssm_user)
                    onboarding.email_verified = True
                    onboarding.email_verified_at = timezone.now()
                    onboarding.save()
                    logger.info(f"Onboarding email_verified updated for {auth_user.email}")
            except User.DoesNotExist:
                logger.warning(f"User profile not found for {auth_user.email}")

            # Generate session token
            token_obj, created = Token.objects.get_or_create(user=auth_user)

            logger.info(f"Email verified successfully for {auth_user.email}")

            return supabase_response(data={
                'message': 'Email verified successfully',
                'user': serialize_user(auth_user),
                'session': {
                    'access_token': token_obj.key,
                    'token_type': 'bearer'
                }
            })

        except SSMAuthUser.DoesNotExist:
            return supabase_response(
                error={'message': 'Invalid or already used verification token'},
                status=400
            )

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def auth_resend_verification(request):
    """POST /api/auth/resend-verification - Resend email verification"""
    try:
        data = json.loads(request.body)
        email = data.get('email')

        if not email:
            return supabase_response(
                error={'message': 'Email is required'},
                status=400
            )

        try:
            auth_user = SSMAuthUser.objects.get(email=email)

            # Check if already verified
            if auth_user.email_confirmed and auth_user.email_confirmed_at:
                return supabase_response(
                    error={'message': 'Email is already verified'},
                    status=400
                )

            # Generate new confirmation token
            confirmation_token = secrets.token_urlsafe(32)
            auth_user.confirmation_token = confirmation_token
            auth_user.confirmation_sent_at = timezone.now()
            auth_user.save()

            # Build verification link
            from ssm_backend_api.settings import FRONTEND_URL as frontend_url
            verification_link = f"{frontend_url}/auth/confirm-email?token={confirmation_token}"

            # Get user's full name from User model
            try:
                ssm_user = User.objects.get(auth_user=auth_user)
                user_name = ssm_user.full_name
            except User.DoesNotExist:
                user_name = email

            # Send verification email
            try:
                EmailService.send_email_verification(
                    email=email,
                    verification_token=confirmation_token,
                    verification_link=verification_link,
                    user_name=user_name
                )
                logger.info(f"Verification email resent to {email}")

                return supabase_response(data={
                    'message': 'Verification email sent successfully'
                })

            except Exception as email_error:
                logger.error(f"Failed to resend verification email to {email}: {email_error}")
                return supabase_response(
                    error={'message': 'Failed to send verification email'},
                    status=500
                )

        except SSMAuthUser.DoesNotExist:
            # Don't reveal if email exists for security
            return supabase_response(data={
                'message': 'If the email exists, a verification email will be sent'
            })

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"Resend verification error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


def serialize_model_instance(instance):
    """Convert model instance to dictionary"""
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        if hasattr(value, 'isoformat'):
            value = value.isoformat()
        elif hasattr(value, '__str__'):
            value = str(value)
        data[field.name] = value
    return data
