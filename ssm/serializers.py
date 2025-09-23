from rest_framework import serializers
from .models import (
    User, Team, SimCard, BatchMetadata, ActivityLog, OnboardingRequest,
    SimCardTransfer, PaymentRequest, Subscription, SubscriptionPlan,
    ForumTopic, ForumPost, ForumLike, SecurityRequestLog, TaskStatus,
    Config, Notification, PasswordResetRequest
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class TeamSerializer(serializers.ModelSerializer):
    leader_name = serializers.CharField(source='leader.full_name', read_only=True)
    admin_name = serializers.CharField(source='admin.full_name', read_only=True)
    
    class Meta:
        model = Team
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class SimCardSerializer(serializers.ModelSerializer):
    sold_by_name = serializers.CharField(source='sold_by_user.full_name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to_user.full_name', read_only=True)
    registered_by_name = serializers.CharField(source='registered_by_user.full_name', read_only=True)
    
    class Meta:
        model = SimCard
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class BatchMetadataSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by_user.full_name', read_only=True)
    sim_count = serializers.SerializerMethodField()
    
    class Meta:
        model = BatchMetadata
        fields = '__all__'
        read_only_fields = ('id', 'created_at')
    
    def get_sim_count(self, obj):
        return SimCard.objects.filter(batch_id=obj.batch_id).count()


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class OnboardingRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    
    class Meta:
        model = OnboardingRequest
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class SimCardTransferSerializer(serializers.ModelSerializer):
    source_team_name = serializers.CharField(source='source_team.name', read_only=True)
    destination_team_name = serializers.CharField(source='destination_team.name', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    
    class Meta:
        model = SimCardTransfer
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class PaymentRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = PaymentRequest
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class SubscriptionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class ForumTopicSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    post_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ForumTopic
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'view_count')
    
    def get_post_count(self, obj):
        return obj.posts.count()
    
    def get_like_count(self, obj):
        return ForumLike.objects.filter(topic=obj).count()


class ForumPostSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    like_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ForumPost
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')
    
    def get_like_count(self, obj):
        return ForumLike.objects.filter(post=obj).count()


class ForumLikeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    
    class Meta:
        model = ForumLike
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class SecurityRequestLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = SecurityRequestLog
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'processed_at')


class TaskStatusSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = TaskStatus
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Config
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class NotificationSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class PasswordResetRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = PasswordResetRequest
        fields = '__all__'
        read_only_fields = ('id', 'created_at')