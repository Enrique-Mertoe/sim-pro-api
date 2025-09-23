from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'teams', views.TeamViewSet)
router.register(r'sim-cards', views.SimCardViewSet)
router.register(r'batch-metadata', views.BatchMetadataViewSet)
router.register(r'activity-logs', views.ActivityLogViewSet)
router.register(r'onboarding-requests', views.OnboardingRequestViewSet)
router.register(r'sim-card-transfers', views.SimCardTransferViewSet)
router.register(r'payment-requests', views.PaymentRequestViewSet)
router.register(r'subscriptions', views.SubscriptionViewSet)
router.register(r'subscription-plans', views.SubscriptionPlanViewSet)
router.register(r'forum-topics', views.ForumTopicViewSet)
router.register(r'forum-posts', views.ForumPostViewSet)
router.register(r'forum-likes', views.ForumLikeViewSet)
router.register(r'security-request-logs', views.SecurityRequestLogViewSet)
router.register(r'task-status', views.TaskStatusViewSet)
router.register(r'config', views.ConfigViewSet)
router.register(r'notifications', views.NotificationViewSet)
router.register(r'password-reset-requests', views.PasswordResetRequestViewSet)

urlpatterns = [
    # Django REST Framework endpoints (for admin/advanced usage)
    path('api/v1/', include(router.urls)),
    
    # Supabase-compatible endpoints (for SDK usage)
    path('api/', include('ssm.supabase_urls')),
]