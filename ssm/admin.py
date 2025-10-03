from django.contrib import admin
from .models import (
    SSMAuthUser, User, Team, TeamGroup, TeamGroupMembership, SimCard,
    BatchMetadata, LotMetadata, ActivityLog, OnboardingRequest,
    SimCardTransfer, PaymentRequest, Subscription, SubscriptionPlan,
    ForumTopic, ForumPost, ForumLike, SecurityRequestLog, TaskStatus,
    Config, Notification, PasswordResetRequest, AdminOnboarding, BusinessInfo,
    UserSettings, Shop, ShopInventory, ShopTransfer, ShopSales, ShopPerformance,
    ShopTarget, ShopAuditLog
)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'role', 'team', 'is_active', 'status']
    list_filter = ['role', 'is_active', 'status', 'team']
    search_fields = ['full_name', 'email', 'id_number']

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'leader', 'region', 'is_active']
    list_filter = ['region', 'is_active']
    search_fields = ['name', 'region']

@admin.register(SimCard)
class SimCardAdmin(admin.ModelAdmin):
    list_display = ['serial_number', 'status', 'team', 'sold_by_user', 'quality', 'match']
    list_filter = ['status', 'quality', 'match', 'fraud_flag', 'team']
    search_fields = ['serial_number', 'batch_id']

@admin.register(BatchMetadata)
class BatchMetadataAdmin(admin.ModelAdmin):
    list_display = ['batch_id', 'admin', 'created_by_user', 'quantity', 'created_at']
    list_filter = ['admin', 'created_at']
    search_fields = ['batch_id', 'order_number']

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'created_at', 'ip_address']
    list_filter = ['action_type', 'created_at', 'is_offline_action']
    search_fields = ['user__full_name', 'action_type']
    readonly_fields = ['created_at']

@admin.register(OnboardingRequest)
class OnboardingRequestAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'get_role', 'status', 'requested_by', 'reviewed_by', 'request_type', 'created_at']
    list_filter = ['status', 'request_type', 'created_at']
    search_fields = ['user_data__full_name', 'user_data__id_number', 'user_data__email']
    readonly_fields = ['id', 'created_at']

    def get_full_name(self, obj):
        return obj.user_data.get('full_name', 'N/A')
    get_full_name.short_description = 'Full Name'
    get_full_name.admin_order_field = 'user_data__full_name'

    def get_role(self, obj):
        return obj.user_data.get('role', 'N/A')
    get_role.short_description = 'Role'
    get_role.admin_order_field = 'user_data__role'

@admin.register(SimCardTransfer)
class SimCardTransferAdmin(admin.ModelAdmin):
    list_display = ['source_team', 'destination_team', 'requested_by', 'status', 'created_at']
    list_filter = ['status', 'created_at']

@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'status', 'reference', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['reference', 'user__full_name']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'starts_at', 'expires_at']
    list_filter = ['status', 'auto_renew']

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_monthly', 'price_annual', 'is_active', 'is_recommended']
    list_filter = ['is_active', 'is_recommended']

@admin.register(ForumTopic)
class ForumTopicAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'is_pinned', 'is_closed', 'view_count', 'created_at']
    list_filter = ['is_pinned', 'is_closed', 'created_at']
    search_fields = ['title', 'content']

@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ['topic', 'created_by', 'created_at']
    list_filter = ['created_at']

@admin.register(SecurityRequestLog)
class SecurityRequestLogAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'method', 'path', 'threat_level', 'risk_score', 'blocked', 'created_at']
    list_filter = ['threat_level', 'blocked', 'method', 'created_at']
    search_fields = ['ip_address', 'path']

@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ['key', 'created_at', 'updated_at']
    search_fields = ['key']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'type', 'read', 'created_at']
    list_filter = ['type', 'read', 'created_at']
    search_fields = ['title', 'user__full_name']

@admin.register(SSMAuthUser)
class SSMAuthUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['username', 'email']

@admin.register(TeamGroup)
class TeamGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'team', 'admin', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']

@admin.register(TeamGroupMembership)
class TeamGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ['group', 'user', 'joined_at']
    list_filter = ['joined_at']
    search_fields = ['group__name', 'user__full_name']

@admin.register(LotMetadata)
class LotMetadataAdmin(admin.ModelAdmin):
    list_display = ['lot_number', 'batch', 'assigned_team', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['lot_number', 'batch__batch_id']

@admin.register(AdminOnboarding)
class AdminOnboardingAdmin(admin.ModelAdmin):
    list_display = ['admin', 'onboarding_completed', 'billing_active', 'created_at']
    list_filter = ['onboarding_completed', 'billing_active', 'created_at']
    search_fields = ['admin__full_name']

@admin.register(BusinessInfo)
class BusinessInfoAdmin(admin.ModelAdmin):
    list_display = ['admin', 'dealer_code', 'contact_phone', 'created_at']
    search_fields = ['dealer_code', 'admin__full_name']

@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'theme', 'language', 'two_factor_enabled', 'updated_at']
    list_filter = ['theme', 'two_factor_enabled']
    search_fields = ['user__full_name']

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ['shop_code', 'shop_name', 'shop_manager', 'status', 'region', 'created_at']
    list_filter = ['status', 'shop_type', 'region', 'created_at']
    search_fields = ['shop_code', 'shop_name', 'region']

@admin.register(ShopInventory)
class ShopInventoryAdmin(admin.ModelAdmin):
    list_display = ['shop', 'sim_card', 'status', 'allocated_date', 'sold_date']
    list_filter = ['status', 'shop', 'allocated_date']
    search_fields = ['shop__shop_code', 'sim_card__serial_number']

@admin.register(ShopTransfer)
class ShopTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_reference', 'source_shop', 'destination_shop', 'requested_by', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['transfer_reference', 'source_shop__shop_code', 'destination_shop__shop_code']

@admin.register(ShopSales)
class ShopSalesAdmin(admin.ModelAdmin):
    list_display = ['sale_reference', 'shop', 'sold_by', 'customer_name', 'net_amount', 'status', 'created_at']
    list_filter = ['status', 'shop', 'payment_method', 'created_at']
    search_fields = ['sale_reference', 'customer_name', 'customer_phone']

@admin.register(ShopPerformance)
class ShopPerformanceAdmin(admin.ModelAdmin):
    list_display = ['shop', 'period_type', 'period_start', 'period_end', 'total_sales', 'total_revenue']
    list_filter = ['shop', 'period_type', 'period_start']
    search_fields = ['shop__shop_code']

@admin.register(ShopTarget)
class ShopTargetAdmin(admin.ModelAdmin):
    list_display = ['shop', 'target_type', 'target_value', 'current_value', 'period_start', 'period_end', 'is_achieved']
    list_filter = ['shop', 'target_type', 'period_type', 'is_achieved']
    search_fields = ['shop__shop_code']

@admin.register(ShopAuditLog)
class ShopAuditLogAdmin(admin.ModelAdmin):
    list_display = ['shop', 'action_type', 'user', 'created_at']
    list_filter = ['action_type', 'created_at']
    search_fields = ['shop__shop_code', 'user__full_name', 'action_type']

admin.site.register(ForumLike)
admin.site.register(TaskStatus)
admin.site.register(PasswordResetRequest)
