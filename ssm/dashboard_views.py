from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json
import csv
import io
from django.utils.dateparse import parse_datetime
import uuid

from .models import (
    User, Team, SimCard, BatchMetadata, ActivityLog, OnboardingRequest,
    SimCardTransfer, PaymentRequest, Subscription, SubscriptionPlan,
    ForumTopic, ForumPost, ForumLike, SecurityRequestLog, TaskStatus,
    Config, Notification, PasswordResetRequest
)

def dashboard_login(request):
    """Dashboard login view"""
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard:home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please enter both username and password.')

    return render(request, 'dashboard/login.html')

def dashboard_logout(request):
    """Dashboard logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('dashboard:login')

@login_required
def dashboard_home(request):
    """Main dashboard home with statistics"""
    # Get key statistics
    stats = {
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'total_teams': Team.objects.count(),
        'total_sim_cards': SimCard.objects.count(),
        'active_sim_cards': SimCard.objects.filter(status='ACTIVE').count(),
        'pending_onboarding': OnboardingRequest.objects.filter(status='PENDING').count(),
        'recent_activities': ActivityLog.objects.order_by('-created_at')[:10],
        'recent_notifications': Notification.objects.order_by('-created_at')[:5],
    }

    # Get chart data
    user_registrations = User.objects.extra(
        select={'month': "STRFTIME('%%Y-%%m', created_at)"}
    ).values('month').annotate(count=Count('id')).order_by('month')

    sim_card_status_data = SimCard.objects.values('status').annotate(count=Count('id'))

    context = {
        'stats': stats,
        'user_registrations': list(user_registrations),
        'sim_card_status_data': list(sim_card_status_data),
    }

    return render(request, 'dashboard/home.html', context)

@login_required
def users_list(request):
    """Users management page"""
    search = request.GET.get('search', '')
    team_filter = request.GET.get('team', '')
    status_filter = request.GET.get('status', '')

    users = User.objects.all()

    if search:
        users = users.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(id_number__icontains=search)
        )

    if team_filter:
        users = users.filter(team_id=team_filter)

    if status_filter:
        users = users.filter(status=status_filter)

    users = users.select_related('team').order_by('-created_at')

    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    teams = Team.objects.all()
    status_choices = User._meta.get_field('status').choices

    context = {
        'page_obj': page_obj,
        'search': search,
        'teams': teams,
        'status_choices': status_choices,
        'team_filter': team_filter,
        'status_filter': status_filter,
    }

    return render(request, 'dashboard/users_list.html', context)

@login_required
def user_detail(request, user_id):
    """User detail page"""
    user = get_object_or_404(User, id=user_id)

    # Get related data
    sim_cards = SimCard.objects.filter(assigned_to_user=user)
    activities = ActivityLog.objects.filter(user=user).order_by('-created_at')[:20]

    context = {
        'user': user,
        'sim_cards': sim_cards,
        'activities': activities,
    }

    return render(request, 'dashboard/user_detail.html', context)

@login_required
def sim_cards_list(request):
    """SIM Cards management page"""
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    user_filter = request.GET.get('user', '')

    sim_cards = SimCard.objects.all()

    if search:
        sim_cards = sim_cards.filter(
            Q(iccid__icontains=search) |
            Q(msisdn__icontains=search) |
            Q(user__full_name__icontains=search)
        )

    if status_filter:
        sim_cards = sim_cards.filter(status=status_filter)

    if user_filter:
        sim_cards = sim_cards.filter(user_id=user_filter)

    sim_cards = sim_cards.select_related('user', 'batch').order_by('-created_at')

    paginator = Paginator(sim_cards, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    status_choices = SimCard._meta.get_field('status').choices

    context = {
        'page_obj': page_obj,
        'search': search,
        'status_choices': status_choices,
        'status_filter': status_filter,
        'user_filter': user_filter,
    }

    return render(request, 'dashboard/sim_cards_list.html', context)

@login_required
def teams_list(request):
    """Teams management page"""
    search = request.GET.get('search', '')

    teams = Team.objects.all()

    if search:
        teams = teams.filter(name__icontains=search)

    teams = teams.annotate(member_count=Count('user')).order_by('-created_at')

    paginator = Paginator(teams, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
    }

    return render(request, 'dashboard/teams_list.html', context)

@login_required
def onboarding_requests_list(request):
    """Onboarding requests management page"""
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    requests = OnboardingRequest.objects.all()

    if search:
        requests = requests.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(id_number__icontains=search)
        )

    if status_filter:
        requests = requests.filter(status=status_filter)

    requests = requests.order_by('-created_at')

    paginator = Paginator(requests, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    status_choices = OnboardingRequest._meta.get_field('status').choices

    context = {
        'page_obj': page_obj,
        'search': search,
        'status_choices': status_choices,
        'status_filter': status_filter,
    }

    return render(request, 'dashboard/onboarding_requests_list.html', context)

@login_required
@require_http_methods(["POST"])
def approve_onboarding_request(request, request_id):
    """Approve an onboarding request"""
    onboarding_request = get_object_or_404(OnboardingRequest, id=request_id)

    if onboarding_request.status == 'PENDING':
        onboarding_request.status = 'APPROVED'
        onboarding_request.save()

        # Create user account
        from django.contrib.auth.models import User as AuthUser
        from rest_framework.authtoken.models import Token
        import secrets

        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)

        # Create auth user
        auth_user = AuthUser.objects.create_user(
            username=onboarding_request.email,
            email=onboarding_request.email,
            password=temp_password
        )

        # Create SSM user
        user = User.objects.create(
            auth_user=auth_user,
            email=onboarding_request.email,
            full_name=onboarding_request.full_name,
            id_number=onboarding_request.id_number,
            id_front_url=onboarding_request.id_front_url,
            id_back_url=onboarding_request.id_back_url,
            phone_number=onboarding_request.phone_number,
            role='staff',
            status='ACTIVE',
            is_active=True
        )

        # Create token
        Token.objects.get_or_create(user=auth_user)

        messages.success(request, f'Onboarding request approved. User created with temporary password: {temp_password}')
    else:
        messages.error(request, 'Request is not in pending status')

    return redirect('dashboard:onboarding_requests')

@login_required
def subscriptions_list(request):
    """Subscriptions management page"""
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    subscriptions = Subscription.objects.all()

    if search:
        subscriptions = subscriptions.filter(
            Q(user__full_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(plan__name__icontains=search)
        )

    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)

    subscriptions = subscriptions.select_related('user', 'plan').order_by('-created_at')

    paginator = Paginator(subscriptions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    status_choices = Subscription._meta.get_field('status').choices

    context = {
        'page_obj': page_obj,
        'search': search,
        'status_choices': status_choices,
        'status_filter': status_filter,
    }

    return render(request, 'dashboard/subscriptions_list.html', context)

@login_required
def activities_list(request):
    """Activity logs page"""
    search = request.GET.get('search', '')
    user_filter = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')

    activities = ActivityLog.objects.all()

    if search:
        activities = activities.filter(
            Q(description__icontains=search) |
            Q(user__full_name__icontains=search)
        )

    if user_filter:
        activities = activities.filter(user_id=user_filter)

    if action_filter:
        activities = activities.filter(action=action_filter)

    activities = activities.select_related('user').order_by('-created_at')

    paginator = Paginator(activities, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    action_choices = ActivityLog._meta.get_field('action').choices

    context = {
        'page_obj': page_obj,
        'search': search,
        'action_choices': action_choices,
        'user_filter': user_filter,
        'action_filter': action_filter,
    }

    return render(request, 'dashboard/activities_list.html', context)

@login_required
def api_stats(request):
    """API endpoint for dashboard statistics (for AJAX updates)"""
    stats = {
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'total_sim_cards': SimCard.objects.count(),
        'active_sim_cards': SimCard.objects.filter(status='ACTIVE').count(),
        'pending_onboarding': OnboardingRequest.objects.filter(status='PENDING').count(),
    }

    return JsonResponse(stats)

@login_required
def import_users_csv(request):
    """Import users from CSV file"""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')

        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('dashboard:users')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('dashboard:users')

        try:
            # Read the uploaded file
            file_data = csv_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(file_data))

            created_count = 0
            updated_count = 0
            error_count = 0
            errors = []

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    user_id = row.get('id', '').strip()
                    if not user_id:
                        continue

                    # Try to parse UUID
                    try:
                        user_uuid = uuid.UUID(user_id)
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid UUID format for id: {user_id}")
                        error_count += 1
                        continue

                    # Parse dates
                    created_at = None
                    if row.get('created_at'):
                        try:
                            created_at = parse_datetime(row['created_at'])
                        except:
                            pass

                    updated_at = None
                    if row.get('updated_at'):
                        try:
                            updated_at = parse_datetime(row['updated_at'])
                        except:
                            pass

                    last_login_at = None
                    if row.get('last_login_at'):
                        try:
                            last_login_at = parse_datetime(row['last_login_at'])
                        except:
                            pass

                    # Handle team relationship
                    team = None
                    if row.get('team_id'):
                        try:
                            team = Team.objects.get(id=row['team_id'])
                        except Team.DoesNotExist:
                            pass

                    # Handle admin relationship
                    admin = None
                    if row.get('admin_id'):
                        try:
                            admin = User.objects.get(id=row['admin_id'])
                        except User.DoesNotExist:
                            pass

                    # Prepare user data
                    user_data = {
                        'created_at': created_at,
                        'email': row.get('email', '').strip() or None,
                        'full_name': row.get('full_name', '').strip(),
                        'id_number': row.get('id_number', '').strip(),
                        'id_front_url': row.get('id_front_url', '').strip(),
                        'id_back_url': row.get('id_back_url', '').strip(),
                        'phone_number': row.get('phone_number', '').strip() or None,
                        'mobigo_number': row.get('mobigo_number', '').strip() or None,
                        'role': row.get('role', '').strip(),
                        'team': team,
                        'staff_type': row.get('staff_type', '').strip() or None,
                        'is_active': row.get('is_active', '').lower() in ['true', '1', 'yes'],
                        'last_login_at': last_login_at,
                        # 'auth_user_id': user_uuid,  # This field is now a relationship, not imported from CSV
                        'status': row.get('status', 'ACTIVE').strip(),
                        'admin': admin,
                        'admin_id': admin,
                        'updated_at': updated_at,
                        'username': row.get('username', '').strip() or None,
                        'is_first_login': row.get('is_first_login', '').lower() in ['true', '1', 'yes'],
                        'password': row.get('password', '').strip() or None,
                        'soft_delete': row.get('soft_delete', '').lower() in ['true', '1', 'yes'],
                        'deleted': row.get('deleted', '').lower() in ['true', '1', 'yes'],
                    }

                    # Remove None values from user_data for update
                    user_data = {k: v for k, v in user_data.items() if v is not None}

                    # Try to get existing user or create new one
                    user, created = User.objects.update_or_create(
                        id=user_uuid,
                        defaults=user_data
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    error_count += 1
                    continue

            # Prepare success message
            success_parts = []
            if created_count > 0:
                success_parts.append(f"{created_count} users created")
            if updated_count > 0:
                success_parts.append(f"{updated_count} users updated")

            if success_parts:
                messages.success(request, f"CSV import completed: {', '.join(success_parts)}")

            if error_count > 0:
                error_msg = f"{error_count} errors encountered"
                if len(errors) <= 5:
                    error_msg += f": {'; '.join(errors)}"
                else:
                    error_msg += f". First 5 errors: {'; '.join(errors[:5])}"
                messages.warning(request, error_msg)

        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")

    return redirect('dashboard:users')

@login_required
def import_teams_csv(request):
    """Import teams from CSV file"""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')

        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('dashboard:teams')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('dashboard:teams')

        try:
            # Read the uploaded file
            file_data = csv_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(file_data))

            created_count = 0
            updated_count = 0
            error_count = 0
            errors = []

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    team_id = row.get('id', '').strip()
                    if not team_id:
                        continue

                    # Try to parse UUID
                    try:
                        team_uuid = uuid.UUID(team_id)
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid UUID format for id: {team_id}")
                        error_count += 1
                        continue

                    # Parse dates
                    created_at = None
                    if row.get('created_at'):
                        try:
                            created_at = parse_datetime(row['created_at'])
                        except:
                            pass

                    # Handle leader relationship
                    leader = None
                    if row.get('leader_id'):
                        try:
                            leader = User.objects.get(id=row['leader_id'])
                        except User.DoesNotExist:
                            pass

                    # Handle admin relationship
                    admin = None
                    if row.get('admin_id'):
                        try:
                            admin = User.objects.get(id=row['admin_id'])
                        except User.DoesNotExist:
                            pass

                    # Prepare team data
                    team_data = {
                        'created_at': created_at,
                        'name': row.get('name', '').strip(),
                        'leader': leader,
                        'region': row.get('region', '').strip(),
                        'territory': row.get('territory', '').strip() or None,
                        'van_number_plate': row.get('van_number_plate', '').strip() or None,
                        'van_location': row.get('van_location', '').strip() or None,
                        'is_active': row.get('is_active', '').lower() in ['true', '1', 'yes'],
                        'admin': admin,
                    }

                    # Remove None values from team_data for update
                    team_data = {k: v for k, v in team_data.items() if v is not None}

                    # Try to get existing team or create new one
                    team, created = Team.objects.update_or_create(
                        id=team_uuid,
                        defaults=team_data
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    error_count += 1
                    continue

            # Prepare success message
            success_parts = []
            if created_count > 0:
                success_parts.append(f"{created_count} teams created")
            if updated_count > 0:
                success_parts.append(f"{updated_count} teams updated")

            if success_parts:
                messages.success(request, f"CSV import completed: {', '.join(success_parts)}")

            if error_count > 0:
                error_msg = f"{error_count} errors encountered"
                if len(errors) <= 5:
                    error_msg += f": {'; '.join(errors)}"
                else:
                    error_msg += f". First 5 errors: {'; '.join(errors[:5])}"
                messages.warning(request, error_msg)

        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")

    return redirect('dashboard:teams')

@login_required
def team_detail(request, team_id):
    """Team detail page with members"""
    team = get_object_or_404(Team, id=team_id)

    # Get team members
    members = User.objects.filter(team=team).order_by('full_name')

    # Get team statistics
    stats = {
        'total_members': members.count(),
        'active_members': members.filter(is_active=True).count(),
        'sim_cards_assigned': SimCard.objects.filter(assigned_to_user__team=team).count(),
        'recent_activities': ActivityLog.objects.filter(user__team=team).order_by('-created_at')[:10],
    }

    context = {
        'team': team,
        'members': members,
        'stats': stats,
    }

    return render(request, 'dashboard/team_detail.html', context)

@login_required
@require_http_methods(["POST"])
def reset_user_password(request, user_id):
    """Reset user password"""
    user = get_object_or_404(User, id=user_id)

    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')

    if not new_password or not confirm_password:
        messages.error(request, 'Both password fields are required.')
        return redirect('dashboard:user_detail', user_id=user_id)

    if new_password != confirm_password:
        messages.error(request, 'Passwords do not match.')
        return redirect('dashboard:user_detail', user_id=user_id)

    if len(new_password) < 6:
        messages.error(request, 'Password must be at least 6 characters long.')
        return redirect('dashboard:user_detail', user_id=user_id)

    try:
        from django.contrib.auth.hashers import make_password

        # Hash the password using Django's recommended method
        hashed_password = make_password(new_password)

        # Update the user's password
        user.password = hashed_password
        user.save()

        messages.success(request, f'Password has been reset for {user.full_name}.')

        # Log the activity
        ActivityLog.objects.create(
            user=user,
            action_type='PASSWORD_RESET',
            details={'description': f'Password reset by admin for user {user.full_name}'},
        )

    except Exception as e:
        messages.error(request, f'Failed to reset password: {str(e)}')

    return redirect('dashboard:user_detail', user_id=user_id)

@login_required
def authentication_management(request):
    """Authentication management page"""
    from rest_framework.authtoken.models import Token
    from django.contrib.auth import get_user_model

    AuthUser = get_user_model()

    # Get search and filter parameters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    permission_filter = request.GET.get('permission', '')

    # Get authentication statistics
    total_auth_users = AuthUser.objects.count()
    active_auth_users = AuthUser.objects.filter(is_active=True).count()
    total_tokens = Token.objects.count()
    staff_users = AuthUser.objects.filter(is_staff=True).count()
    superusers = AuthUser.objects.filter(is_superuser=True).count()

    # Get recent authentication activities from Django auth events
    recent_activities = ActivityLog.objects.filter(
        action_type__in=['LOGIN', 'LOGOUT', 'PASSWORD_RESET', 'TOKEN_CREATED', 'TOKEN_REVOKED']
    ).order_by('-created_at')[:20]

    # Get all tokens with user information - with pagination
    tokens_queryset = Token.objects.select_related('user').order_by('-created')
    tokens_paginator = Paginator(tokens_queryset, 20)
    tokens_page_number = request.GET.get('tokens_page')
    tokens_page_obj = tokens_paginator.get_page(tokens_page_number)

    # Get Django auth users without tokens
    users_with_tokens = Token.objects.values_list('user_id', flat=True)
    auth_users_without_tokens = AuthUser.objects.exclude(id__in=users_with_tokens)[:20]

    # Get all Django auth users for management with search and filters
    auth_users_queryset = AuthUser.objects.all()

    # Apply search filter
    if search:
        auth_users_queryset = auth_users_queryset.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )

    # Apply status filter
    if status_filter == 'active':
        auth_users_queryset = auth_users_queryset.filter(is_active=True)
    elif status_filter == 'inactive':
        auth_users_queryset = auth_users_queryset.filter(is_active=False)

    # Apply permission filter
    if permission_filter == 'staff':
        auth_users_queryset = auth_users_queryset.filter(is_staff=True)
    elif permission_filter == 'superuser':
        auth_users_queryset = auth_users_queryset.filter(is_superuser=True)
    elif permission_filter == 'user':
        auth_users_queryset = auth_users_queryset.filter(is_staff=False, is_superuser=False)

    auth_users_queryset = auth_users_queryset.order_by('-date_joined')

    # Paginate auth users
    auth_users_paginator = Paginator(auth_users_queryset, 25)
    auth_users_page_number = request.GET.get('users_page')
    auth_users_page_obj = auth_users_paginator.get_page(auth_users_page_number)

    context = {
        'total_auth_users': total_auth_users,
        'active_auth_users': active_auth_users,
        'total_tokens': total_tokens,
        'staff_users': staff_users,
        'superusers': superusers,
        'recent_activities': recent_activities,
        'tokens_page_obj': tokens_page_obj,
        'auth_users_without_tokens': auth_users_without_tokens,
        'auth_users_page_obj': auth_users_page_obj,
        'search': search,
        'status_filter': status_filter,
        'permission_filter': permission_filter,
    }

    return render(request, 'dashboard/authentication.html', context)

@login_required
@require_http_methods(["POST"])
def revoke_token(request):
    """Revoke a user's authentication token"""
    import json
    from rest_framework.authtoken.models import Token

    try:
        data = json.loads(request.body)
        token_key = data.get('token_key')

        if not token_key:
            return JsonResponse({'success': False, 'error': 'Token key is required'})

        try:
            token = Token.objects.get(key=token_key)
            username = token.user.username
            token.delete()

            # Log the activity (skip since user is None)
            # ActivityLog requires a user, so we'll skip logging admin actions for now

            return JsonResponse({'success': True, 'message': 'Token revoked successfully'})

        except Token.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Token not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def create_token(request):
    """Create authentication token for a user"""
    import json
    from rest_framework.authtoken.models import Token
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')

        if not user_id:
            return JsonResponse({'success': False, 'error': 'User ID is required'})

        try:
            # Get the SSM user
            ssm_user = User.objects.get(id=user_id)

            # Get or create the corresponding Django auth user
            AuthUser = get_user_model()
            try:
                auth_user = AuthUser.objects.get(username=ssm_user.email)
            except AuthUser.DoesNotExist:
                # Create auth user if doesn't exist
                auth_user = AuthUser.objects.create_user(
                    username=ssm_user.email,
                    email=ssm_user.email,
                    password='temp_password_change_me'
                )
                ssm_user.auth_user = auth_user
                ssm_user.save()

            # Create token
            token, created = Token.objects.get_or_create(user=auth_user)

            if created:
                # Log the activity
                ActivityLog.objects.create(
                    user=ssm_user,
                    action_type='TOKEN_CREATED',
                    details={'description': f'Authentication token created for user {ssm_user.full_name} by admin'},
                )

                return JsonResponse({'success': True, 'message': 'Token created successfully'})
            else:
                return JsonResponse({'success': False, 'error': 'Token already exists for this user'})

        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def create_auth_token(request):
    """Create authentication token for a Django auth user"""
    import json
    from rest_framework.authtoken.models import Token
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        auth_user_id = data.get('auth_user_id')

        if not auth_user_id:
            return JsonResponse({'success': False, 'error': 'Auth user ID is required'})

        try:
            AuthUser = get_user_model()
            auth_user = AuthUser.objects.get(id=auth_user_id)

            # Create token
            token, created = Token.objects.get_or_create(user=auth_user)

            if created:
                # Skip logging since ActivityLog requires a user

                return JsonResponse({'success': True, 'message': 'Token created successfully'})
            else:
                return JsonResponse({'success': False, 'error': 'Token already exists for this user'})

        except get_user_model().DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Auth user not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def create_auth_user(request):
    """Create new Django auth user"""
    import json
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({'success': False, 'error': 'Username and password are required'})

        try:
            AuthUser = get_user_model()

            # Check if user exists
            if AuthUser.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'error': 'Username already exists'})

            # Create user
            auth_user = AuthUser.objects.create_user(
                username=username,
                email=email or '',
                password=password
            )

            # Skip logging since ActivityLog requires a user

            return JsonResponse({'success': True, 'message': 'User created successfully'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error creating user: {str(e)}'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def reset_auth_password(request):
    """Reset Django auth user password"""
    import json
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        auth_user_id = data.get('auth_user_id')
        new_password = data.get('new_password')

        if not auth_user_id or not new_password:
            return JsonResponse({'success': False, 'error': 'Auth user ID and new password are required'})

        try:
            AuthUser = get_user_model()
            auth_user = AuthUser.objects.get(id=auth_user_id)

            # Set new password
            auth_user.set_password(new_password)
            auth_user.save()

            # Skip logging since ActivityLog requires a user

            return JsonResponse({'success': True, 'message': 'Password reset successfully'})

        except get_user_model().DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Auth user not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def toggle_user_status(request):
    """Toggle Django auth user active status"""
    import json
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        auth_user_id = data.get('auth_user_id')

        if not auth_user_id:
            return JsonResponse({'success': False, 'error': 'Auth user ID is required'})

        try:
            AuthUser = get_user_model()
            auth_user = AuthUser.objects.get(id=auth_user_id)

            # Toggle active status
            auth_user.is_active = not auth_user.is_active
            auth_user.save()

            status = 'activated' if auth_user.is_active else 'deactivated'

            # Skip logging since ActivityLog requires a user

            return JsonResponse({'success': True, 'message': f'User {status} successfully'})

        except get_user_model().DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Auth user not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def toggle_staff(request):
    """Toggle Django auth user staff status"""
    import json
    from django.contrib.auth import get_user_model

    try:
        data = json.loads(request.body)
        auth_user_id = data.get('auth_user_id')

        if not auth_user_id:
            return JsonResponse({'success': False, 'error': 'Auth user ID is required'})

        try:
            AuthUser = get_user_model()
            auth_user = AuthUser.objects.get(id=auth_user_id)

            # Toggle staff status
            auth_user.is_staff = not auth_user.is_staff
            auth_user.save()

            status = 'granted' if auth_user.is_staff else 'removed'

            # Skip logging since ActivityLog requires a user

            return JsonResponse({'success': True, 'message': f'Staff access {status} successfully'})

        except get_user_model().DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Auth user not found'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def import_auth_users_csv(request):
    """Import Django auth users from CSV file"""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')

        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('dashboard:authentication')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('dashboard:authentication')

        try:
            from django.contrib.auth import get_user_model
            AuthUser = get_user_model()

            # Read the uploaded file
            file_data = csv_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(file_data))

            created_count = 0
            updated_count = 0
            error_count = 0
            errors = []

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # Extract required fields from CSV
                    email = row.get('email', '').strip()
                    full_name = row.get('full_name', '').strip()
                    phone_number = row.get('phone_number', '').strip()
                    username = row.get('username', '').strip()

                    # Skip rows without essential data
                    if not full_name and not email and not phone_number and not username:
                        continue

                    # Determine username - prefer username field, then phone, then email
                    auth_username = username or phone_number or email
                    if not auth_username:
                        errors.append(f"Row {row_num}: No valid username, phone, or email found")
                        error_count += 1
                        continue

                    # Determine email - use email field if available, otherwise None
                    auth_email = email if email else ''

                    # Get the SSM user UUID from the CSV
                    ssm_user_id = row.get('id', '').strip()
                    if not ssm_user_id:
                        errors.append(f"Row {row_num}: No SSM user ID found")
                        error_count += 1
                        continue

                    try:
                        ssm_user_uuid = uuid.UUID(ssm_user_id)
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid SSM user UUID format: {ssm_user_id}")
                        error_count += 1
                        continue

                    # Check if Django auth user already exists
                    if AuthUser.objects.filter(username=auth_username).exists():
                        auth_user = AuthUser.objects.get(username=auth_username)
                        # Update email if provided and different
                        if auth_email and auth_user.email != auth_email:
                            auth_user.email = auth_email
                            auth_user.save()

                        # Check if SSM user exists and update auth_user relationship
                        try:
                            ssm_user = User.objects.get(id=ssm_user_uuid)
                            if ssm_user.auth_user != auth_user:
                                ssm_user.auth_user = auth_user
                                ssm_user.save()
                        except User.DoesNotExist:
                            pass  # SSM user doesn't exist, that's fine for auth-only import

                        updated_count += 1
                        continue

                    # Create new Django auth user
                    auth_user = AuthUser.objects.create_user(
                        username=auth_username,
                        email=auth_email,
                        password='password123',  # Default password as requested
                        first_name=full_name.split(' ')[0] if full_name else '',
                        last_name=' '.join(full_name.split(' ')[1:]) if len(full_name.split(' ')) > 1 else ''
                    )

                    # Check if SSM user exists and update auth_user relationship
                    try:
                        ssm_user = User.objects.get(id=ssm_user_uuid)
                        ssm_user.auth_user = auth_user
                        ssm_user.save()
                    except User.DoesNotExist:
                        pass  # SSM user doesn't exist, that's fine for auth-only import

                    created_count += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    error_count += 1
                    continue

            # Prepare success message
            success_parts = []
            if created_count > 0:
                success_parts.append(f"{created_count} auth users created")
            if updated_count > 0:
                success_parts.append(f"{updated_count} auth users updated")

            if success_parts:
                messages.success(request, f"CSV import completed: {', '.join(success_parts)}. Default password: 'password123'. SSM users linked to auth users where possible.")

            if error_count > 0:
                error_msg = f"{error_count} errors encountered"
                if len(errors) <= 5:
                    error_msg += f": {'; '.join(errors)}"
                else:
                    error_msg += f". First 5 errors: {'; '.join(errors[:5])}"
                messages.warning(request, error_msg)

        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")

    return redirect('dashboard:authentication')