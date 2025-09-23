from django.urls import path
from . import auth_views

app_name = 'api'

urlpatterns = [
    # Authentication endpoints
    path('auth/login/', auth_views.login_api, name='login'),
    path('auth/register/', auth_views.register_api, name='register'),
    path('auth/verify/', auth_views.verify_token, name='verify'),
    path('auth/logout/', auth_views.logout_api, name='logout'),

    # Dashboard API endpoints (to be created later)
    # path('dashboard/stats/', api_views.dashboard_stats, name='dashboard_stats'),
    # path('users/', api_views.users_list, name='users_list'),
    # path('teams/', api_views.teams_list, name='teams_list'),
    # path('sim-cards/', api_views.sim_cards_list, name='sim_cards_list'),
    # path('activities/', api_views.activities_list, name='activities_list'),
]