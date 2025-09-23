from django.urls import path
from . import dashboard_views

app_name = 'dashboard'

urlpatterns = [
    # Authentication
    path('login/', dashboard_views.dashboard_login, name='login'),
    path('logout/', dashboard_views.dashboard_logout, name='logout'),

    # Main dashboard
    path('', dashboard_views.dashboard_home, name='home'),

    # Users management
    path('users/', dashboard_views.users_list, name='users'),
    path('users/<uuid:user_id>/', dashboard_views.user_detail, name='user_detail'),
    path('users/<uuid:user_id>/reset-password/', dashboard_views.reset_user_password, name='reset_user_password'),
    path('users/import-csv/', dashboard_views.import_users_csv, name='import_users_csv'),

    # SIM Cards management
    path('sim-cards/', dashboard_views.sim_cards_list, name='sim_cards'),

    # Teams management
    path('teams/', dashboard_views.teams_list, name='teams'),
    path('teams/<uuid:team_id>/', dashboard_views.team_detail, name='team_detail'),
    path('teams/import-csv/', dashboard_views.import_teams_csv, name='import_teams_csv'),

    # Onboarding requests
    path('onboarding/', dashboard_views.onboarding_requests_list, name='onboarding_requests'),
    path('onboarding/<uuid:request_id>/approve/', dashboard_views.approve_onboarding_request, name='approve_onboarding'),

    # Subscriptions
    path('subscriptions/', dashboard_views.subscriptions_list, name='subscriptions'),

    # Activity logs
    path('activities/', dashboard_views.activities_list, name='activities'),

    # Authentication management
    path('authentication/', dashboard_views.authentication_management, name='authentication'),
    path('authentication/revoke-token/', dashboard_views.revoke_token, name='revoke_token'),
    path('authentication/create-token/', dashboard_views.create_token, name='create_token'),
    path('authentication/create-auth-token/', dashboard_views.create_auth_token, name='create_auth_token'),
    path('authentication/create-auth-user/', dashboard_views.create_auth_user, name='create_auth_user'),
    path('authentication/reset-auth-password/', dashboard_views.reset_auth_password, name='reset_auth_password'),
    path('authentication/toggle-user-status/', dashboard_views.toggle_user_status, name='toggle_user_status'),
    path('authentication/toggle-staff/', dashboard_views.toggle_staff, name='toggle_staff'),
    path('authentication/import-csv/', dashboard_views.import_auth_users_csv, name='import_auth_users_csv'),

    # API endpoints
    path('api/stats/', dashboard_views.api_stats, name='api_stats'),
]