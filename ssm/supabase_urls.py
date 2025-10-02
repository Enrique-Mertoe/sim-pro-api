"""
URL patterns for Supabase-compatible API endpoints
These match exactly what the solobase-js SDK expects
"""
from django.urls import path, include
from . import supabase_views, subscription_views, supabase_admin_views, rpc_views, db_views

urlpatterns = [
    # Authentication endpoints
    path('auth/signup', supabase_views.auth_signup, name='auth_signup'),
    path('auth/login', supabase_views.auth_login, name='auth_login'),
    path('auth/logout', supabase_views.auth_logout, name='auth_logout'),
    path('auth/me', supabase_views.auth_me, name='auth_me'),
    path('auth/refresh', supabase_views.auth_refresh, name='auth_refresh'),
    path('auth/recover', supabase_views.auth_recover, name='auth_recover'),
    path('auth/reset-password', supabase_views.auth_reset_password, name='auth_reset_password'),
    path('auth/update-password', supabase_views.auth_update_password, name='auth_update_password'),
    path('auth/verify', supabase_views.auth_verify_otp, name='auth_verify_otp'),
    path('auth/verify-email', supabase_views.auth_verify_email, name='auth_verify_email'),
    path('auth/resend-verification', supabase_views.auth_resend_verification, name='auth_resend_verification'),

    # Admin authentication endpoints
    path('auth/admin/users', supabase_admin_views.auth_admin_users, name='auth_admin_users'),
    path('auth/admin/users/<str:user_id>', supabase_admin_views.auth_admin_user_by_id, name='auth_admin_user_by_id'),
    path('auth/admin/generate_link', supabase_admin_views.auth_admin_generate_link, name='auth_admin_generate_link'),
    path('auth/admin/invite', supabase_admin_views.auth_admin_invite, name='auth_admin_invite'),

    # Database endpoints (original format)
    path('db/select', db_views.db_select, name='db_select'),
    path('db/insert', db_views.db_insert, name='db_insert'),
    path('db/update', db_views.db_update, name='db_update'),
    path('db/delete', db_views.db_delete, name='db_delete'),

    # PostgREST-style endpoints (for SDK compatibility)
    path('rest/v1/<str:table_name>', supabase_views.postgrest_handler, name='postgrest_handler'),

    # RPC endpoints (Remote Procedure Calls)
    path('rest/v1/rpc/<str:function_name>', rpc_views.rpc_handler, name='rpc_handler'),

    # Trigger management endpoints
    path('rest/v1/triggers/', include('ssm.triggers.urls')),

    # Storage endpoints - Supabase Storage API compatible
    path('storage/v1/object/<str:bucket_name>', supabase_views.storage_upload_to_bucket, name='storage_upload_bucket'),
    path('storage/v1/object/<str:bucket_name>/<path:file_path>', supabase_views.storage_file_operations,
         name='storage_file_ops'),
    path('storage/v1/object/list/<str:bucket_name>', supabase_views.storage_list_files, name='storage_list'),
    path('storage/v1/object/public/<str:bucket_name>/<path:file_path>', supabase_views.storage_get_public_url,
         name='storage_public'),

    # Subscription endpoints
    path('subscriptions/check', subscription_views.check_user_subscription, name="subscription_check"),
    path('subscriptions/create', subscription_views.create_subscription, name="subscription_create"),
    path('subscriptions/<str:subscription_id>/cancel', subscription_views.cancel_subscription,
         name="subscription_cancel"),
    # Legacy storage endpoints
    path('rest/v1/storage/upload', supabase_views.storage_upload, name='storage_upload'),
    path('rest/v1/storage/<str:filename>', supabase_views.storage_download, name='storage_download'),
]
