from django.contrib.auth import authenticate
from django.contrib.auth.models import User as AuthUser
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import json
from .models import User
import uuid

@csrf_exempt
@require_http_methods(["POST"])
def login_api(request):
    """API login endpoint"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return JsonResponse({
                'error': 'Email and password are required'
            }, status=400)

        # Try to find SSM user by email
        try:
            ssm_user = User.objects.get(email=email)
        except User.DoesNotExist:

            return JsonResponse({
                'error': 'Invalid credentials'
            }, status=401)

        # Check if user is active
        if not ssm_user.is_active:
            return JsonResponse({
                'error': 'Account is disabled'
            }, status=401)

        # Use Django's recommended password verification
        from django.contrib.auth.hashers import check_password

        # Verify password using Django's secure hash verification
        if not check_password(password, ssm_user.password):
            print(90)
            return JsonResponse({
                'error': 'Invalid credentials'
            }, status=401)

        # Create or get Django auth user for token generation
        auth_user, created = AuthUser.objects.get_or_create(
            username=email,
            defaults={
                'email': email,
                'first_name': ssm_user.full_name.split(' ')[0] if ' ' in ssm_user.full_name else ssm_user.full_name,
                'last_name': ' '.join(ssm_user.full_name.split(' ')[1:]) if ' ' in ssm_user.full_name else '',
            }
        )

        user = auth_user

        if user is not None:
            # Get or create token
            token, created = Token.objects.get_or_create(user=user)

            # Use SSM user data directly
            user_data = {
                'id': str(ssm_user.id),
                'email': ssm_user.email,
                'full_name': ssm_user.full_name,
                'role': ssm_user.role,
                'is_active': ssm_user.is_active,
                'team': {
                    'id': str(ssm_user.team.id),
                    'name': ssm_user.team.name
                } if ssm_user.team else None
            }

            return JsonResponse({
                'token': token.key,
                'user': user_data
            })
        else:
            return JsonResponse({
                'error': 'Invalid credentials'
            }, status=401)

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Login failed'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def register_api(request):
    """API registration endpoint"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        phone_number = data.get('phone_number')
        id_number = data.get('id_number')

        if not email or not password or not full_name or not id_number:
            return JsonResponse({
                'error': 'Email, password, full name, and ID number are required'
            }, status=400)

        # Check if user already exists
        if AuthUser.objects.filter(email=email).exists():
            return JsonResponse({
                'error': 'User with this email already exists'
            }, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({
                'error': 'User with this email already exists'
            }, status=400)

        # Create auth user
        auth_user = AuthUser.objects.create_user(
            username=email,  # Use email as username
            email=email,
            password=password,
            first_name=full_name.split(' ')[0] if ' ' in full_name else full_name,
            last_name=' '.join(full_name.split(' ')[1:]) if ' ' in full_name else ''
        )

        # Create SSM user
        ssm_user = User.objects.create(
            auth_user=auth_user,
            email=email,
            full_name=full_name,
            id_number=id_number,
            phone_number=phone_number,
            role='staff',  # Default role
            status='ACTIVE',
            is_active=True,
            is_first_login=True
        )

        # Create token
        token, created = Token.objects.get_or_create(user=auth_user)

        user_data = {
            'id': str(ssm_user.id),
            'email': ssm_user.email,
            'full_name': ssm_user.full_name,
            'role': ssm_user.role,
            'is_active': ssm_user.is_active,
            'team': None
        }

        return JsonResponse({
            'token': token.key,
            'user': user_data
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': f'Registration failed: {str(e)}'
        }, status=500)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def verify_token(request):
    """Verify token and return user data"""
    try:
        auth_user = request.user

        # Get SSM user data by email (since we use email as username)
        try:
            ssm_user = User.objects.get(email=auth_user.email)
            user_data = {
                'id': str(ssm_user.id),
                'email': ssm_user.email,
                'full_name': ssm_user.full_name,
                'role': ssm_user.role,
                'is_active': ssm_user.is_active,
                'team': {
                    'id': str(ssm_user.team.id),
                    'name': ssm_user.team.name
                } if ssm_user.team else None
            }
        except User.DoesNotExist:
            # Fallback to auth user data
            user_data = {
                'id': str(auth_user.id),
                'email': auth_user.email,
                'full_name': auth_user.get_full_name() or auth_user.username,
                'role': 'user',
                'is_active': auth_user.is_active,
                'team': None
            }

        return Response({
            'user': user_data
        })

    except Exception:
        return Response({
            'error': 'Token verification failed'
        }, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def logout_api(request):
    """API logout endpoint"""
    try:
        # Delete the token
        request.user.auth_token.delete()
        return Response({
            'message': 'Successfully logged out'
        })
    except Exception as e:
        return Response({
            'error': 'Logout failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)