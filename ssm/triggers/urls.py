"""
URL configuration for trigger management endpoints
"""
from django.urls import path
from . import management_views

urlpatterns = [
    # Trigger registry status and statistics
    path('status/', management_views.get_trigger_registry_status, name='trigger_registry_status'),

    # Trigger listing and details
    path('list/', management_views.list_triggers, name='list_triggers'),
    path('details/<str:trigger_name>/', management_views.get_trigger_details, name='trigger_details'),

    # Trigger control
    path('toggle/<str:trigger_name>/', management_views.toggle_trigger_status, name='toggle_trigger'),
    path('execute/<str:trigger_name>/', management_views.execute_trigger_manually, name='execute_trigger'),

    # Engine control
    path('engine/toggle/', management_views.toggle_trigger_engine, name='toggle_trigger_engine'),

    # Monitoring and logs
    path('logs/', management_views.get_trigger_execution_logs, name='trigger_logs'),

    # Maintenance
    path('cache/clear/', management_views.clear_trigger_cache, name='clear_trigger_cache'),
    path('config/export/', management_views.export_trigger_config, name='export_trigger_config'),
]