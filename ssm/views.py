from django.shortcuts import render
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Avg
from .models import (
    User, Team, SimCard, BatchMetadata, ActivityLog, OnboardingRequest,
    SimCardTransfer, PaymentRequest, Subscription, SubscriptionPlan,
    ForumTopic, ForumPost, ForumLike, SecurityRequestLog, TaskStatus,
    Config, Notification, PasswordResetRequest
)
from .serializers import (
    UserSerializer, TeamSerializer, SimCardSerializer, BatchMetadataSerializer,
    ActivityLogSerializer, OnboardingRequestSerializer, SimCardTransferSerializer,
    PaymentRequestSerializer, SubscriptionSerializer, SubscriptionPlanSerializer,
    ForumTopicSerializer, ForumPostSerializer, ForumLikeSerializer,
    SecurityRequestLogSerializer, TaskStatusSerializer, ConfigSerializer,
    NotificationSerializer, PasswordResetRequestSerializer
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = User.objects.all()
        # Add filtering based on user role and permissions
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) |
                Q(email__icontains=search) |
                Q(id_number__icontains=search)
            )
        return queryset
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        try:
            user = User.objects.get(auth_user_id=request.user.id)
            serializer = self.get_serializer(user)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        
        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action_type='USER_STATUS_CHANGED',
            details={
                'target_user_id': str(user.id),
                'new_status': 'active' if user.is_active else 'inactive'
            },
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return Response({'status': 'active' if user.is_active else 'inactive'})


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Team.objects.all()
        region = self.request.query_params.get('region', None)
        if region:
            queryset = queryset.filter(region=region)
        
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
            
        return queryset.select_related('leader', 'admin')
    
    def perform_create(self, serializer):
        team = serializer.save()
        # Update leader's team_id when team is created
        if team.leader:
            team.leader.team = team
            team.leader.save()
    
    def perform_update(self, serializer):
        old_leader_id = self.get_object().leader_id
        team = serializer.save()
        
        # Update team_id for new leader
        if team.leader and team.leader_id != old_leader_id:
            team.leader.team = team
            team.leader.save()
        
        # Clear team_id for old leader if changed
        if old_leader_id and old_leader_id != team.leader_id:
            try:
                old_leader = User.objects.get(id=old_leader_id)
                old_leader.team = None
                old_leader.save()
            except User.DoesNotExist:
                pass
    
    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        team = self.get_object()
        # Get team performance metrics
        sim_cards = SimCard.objects.filter(team=team)
        
        performance_data = {
            'team_id': team.id,
            'team_name': team.name,
            'total_sim_cards': sim_cards.count(),
            'quality_sim_cards': sim_cards.filter(quality='QUALITY').count(),
            'matched_sim_cards': sim_cards.filter(match='Y').count(),
            'fraud_flags': sim_cards.filter(fraud_flag=True).count(),
            'avg_top_up': sim_cards.aggregate(Avg('top_up_amount'))['top_up_amount__avg'] or 0
        }
        
        return Response(performance_data)


class SimCardViewSet(viewsets.ModelViewSet):
    queryset = SimCard.objects.all()
    serializer_class = SimCardSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = SimCard.objects.all()
        
        # Filters
        serial_number = self.request.query_params.get('serial_number', None)
        if serial_number:
            queryset = queryset.filter(serial_number__icontains=serial_number)
        
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        team_id = self.request.query_params.get('team_id', None)
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        
        batch_id = self.request.query_params.get('batch_id', None)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        
        return queryset.select_related('team', 'sold_by_user', 'assigned_to_user', 'registered_by_user')
    
    def perform_update(self, serializer):
        old_obj = self.get_object()
        new_obj = serializer.save()
        
        # Trigger functionality: Update registered_on when status changes to REGISTERED
        if old_obj.status != 'REGISTERED' and new_obj.status == 'REGISTERED':
            new_obj.registered_on = timezone.now()
            new_obj.save()
    
    @action(detail=False, methods=['post'])
    def bulk_update_status(self, request):
        sim_card_ids = request.data.get('sim_card_ids', [])
        new_status = request.data.get('status')
        
        if not sim_card_ids or not new_status:
            return Response({'error': 'sim_card_ids and status are required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            sim_cards = SimCard.objects.filter(id__in=sim_card_ids)
            updated_count = 0
            
            for sim_card in sim_cards:
                old_status = sim_card.status
                sim_card.status = new_status
                
                # Apply trigger logic
                if old_status != 'REGISTERED' and new_status == 'REGISTERED':
                    sim_card.registered_on = timezone.now()
                
                sim_card.save()
                updated_count += 1
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action_type='BULK_SIM_STATUS_UPDATE',
                details={
                    'sim_card_count': updated_count,
                    'new_status': new_status,
                    'sim_card_ids': sim_card_ids
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return Response({'updated_count': updated_count})


class BatchMetadataViewSet(viewsets.ModelViewSet):
    queryset = BatchMetadata.objects.all()
    serializer_class = BatchMetadataSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = BatchMetadata.objects.all()
        
        team_id = self.request.query_params.get('team_id', None)
        if team_id:
            queryset = queryset.filter(team_id=team_id)
            
        batch_id = self.request.query_params.get('batch_id', None)
        if batch_id:
            queryset = queryset.filter(batch_id__icontains=batch_id)
        
        return queryset.select_related('team', 'created_by_user')


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityLog.objects.all()
    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = ActivityLog.objects.all().order_by('-created_at')
        
        user_id = self.request.query_params.get('user_id', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        action_type = self.request.query_params.get('action_type', None)
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        
        return queryset.select_related('user')


class OnboardingRequestViewSet(viewsets.ModelViewSet):
    queryset = OnboardingRequest.objects.all()
    serializer_class = OnboardingRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = OnboardingRequest.objects.all().order_by('-created_at')
        
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related('requested_by', 'reviewed_by', 'team')
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        onboarding_request = self.get_object()
        
        if onboarding_request.status.lower() == 'approved':
            return Response({'error': 'Request already approved'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Update request status
            onboarding_request.status = 'APPROVED'
            onboarding_request.reviewed_by = request.user
            onboarding_request.review_date = timezone.now()
            onboarding_request.save()
            
            # Create new user (trigger functionality)
            if onboarding_request.request_type != 'DELETION':
                import uuid
                new_user = User.objects.create(
                    email=f"{onboarding_request.full_name.lower().replace(' ', '')}@{onboarding_request.id_number}.temp",
                    full_name=onboarding_request.full_name,
                    id_number=onboarding_request.id_number,
                    id_front_url=onboarding_request.id_front_url,
                    id_back_url=onboarding_request.id_back_url,
                    phone_number=onboarding_request.phone_number,
                    mobigo_number=onboarding_request.mobigo_number,
                    role=onboarding_request.role,
                    team=onboarding_request.team,
                    staff_type=onboarding_request.staff_type,
                    status='ACTIVE',
                    is_active=True,
                    auth_user_id=uuid.uuid4()  # Generate a unique auth_user_id
                )
                
                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action_type='USER_CREATED',
                    details={
                        'request_id': str(onboarding_request.id),
                        'full_name': onboarding_request.full_name,
                        'role': onboarding_request.role,
                        'team_id': str(onboarding_request.team.id) if onboarding_request.team else None
                    },
                    ip_address=request.META.get('REMOTE_ADDR'),
                    is_offline_action=False
                )
        
        return Response({'message': 'Onboarding request approved successfully'})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        onboarding_request = self.get_object()
        
        onboarding_request.status = 'REJECTED'
        onboarding_request.reviewed_by = request.user
        onboarding_request.review_date = timezone.now()
        onboarding_request.review_notes = request.data.get('review_notes', '')
        onboarding_request.save()
        
        return Response({'message': 'Onboarding request rejected'})


class SimCardTransferViewSet(viewsets.ModelViewSet):
    queryset = SimCardTransfer.objects.all()
    serializer_class = SimCardTransferSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SimCardTransfer.objects.all().select_related(
            'source_team', 'destination_team', 'requested_by', 'approved_by'
        )
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        
        if transfer.status == 'approved':
            return Response({'error': 'Transfer already approved'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Update transfer status
            transfer.status = 'approved'
            transfer.approved_by = request.user
            transfer.approval_date = timezone.now()
            transfer.save()
            
            # Transfer SIM cards (trigger functionality)
            sim_card_ids = transfer.sim_cards if isinstance(transfer.sim_cards, list) else []
            sim_cards_to_update = SimCard.objects.filter(
                id__in=sim_card_ids,
                team=transfer.source_team
            ).exclude(status='sold')
            
            updated_count = 0
            for sim_card in sim_cards_to_update:
                sim_card.team = transfer.destination_team
                sim_card.updated_at = timezone.now()
                sim_card.save()
                updated_count += 1
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action_type='SIM_TRANSFER_APPROVED',
                details={
                    'transfer_id': str(transfer.id),
                    'source_team': transfer.source_team.name,
                    'destination_team': transfer.destination_team.name,
                    'sim_cards_transferred': updated_count
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return Response({'message': f'Transfer approved. {updated_count} SIM cards transferred.'})


class PaymentRequestViewSet(viewsets.ModelViewSet):
    queryset = PaymentRequest.objects.all()
    serializer_class = PaymentRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PaymentRequest.objects.all().select_related('user')


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.all().select_related('user')


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            return SubscriptionPlan.objects.filter(is_active=is_active.lower() == 'true')
        return SubscriptionPlan.objects.all()


class ForumTopicViewSet(viewsets.ModelViewSet):
    queryset = ForumTopic.objects.all()
    serializer_class = ForumTopicSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ForumTopic.objects.all().select_related('created_by').order_by('-is_pinned', '-created_at')
    
    def perform_create(self, serializer):
        # Get the current user from the User model, not auth.User
        try:
            current_user = User.objects.get(auth_user_id=self.request.user.id)
            serializer.save(created_by=current_user)
        except User.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        topic = self.get_object()
        try:
            user = User.objects.get(auth_user_id=request.user.id)
        except User.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        like, created = ForumLike.objects.get_or_create(
            user=user, topic=topic,
            defaults={'user': user, 'topic': topic}
        )
        
        if not created:
            like.delete()
            return Response({'liked': False})
        
        return Response({'liked': True})
    
    @action(detail=True, methods=['post'])
    def increment_view_count(self, request, pk=None):
        topic = self.get_object()
        topic.view_count += 1
        topic.save()
        return Response({'view_count': topic.view_count})


class ForumPostViewSet(viewsets.ModelViewSet):
    queryset = ForumPost.objects.all()
    serializer_class = ForumPostSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        topic_id = self.request.query_params.get('topic_id', None)
        queryset = ForumPost.objects.all().select_related('created_by', 'topic')
        
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)
        
        return queryset.order_by('created_at')
    
    def perform_create(self, serializer):
        try:
            current_user = User.objects.get(auth_user_id=self.request.user.id)
            serializer.save(created_by=current_user)
        except User.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        post = self.get_object()
        try:
            user = User.objects.get(auth_user_id=request.user.id)
        except User.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        like, created = ForumLike.objects.get_or_create(
            user=user, post=post,
            defaults={'user': user, 'post': post}
        )
        
        if not created:
            like.delete()
            return Response({'liked': False})
        
        return Response({'liked': True})


class ForumLikeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ForumLike.objects.all()
    serializer_class = ForumLikeSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ForumLike.objects.all().select_related('user', 'topic', 'post')


class SecurityRequestLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SecurityRequestLog.objects.all()
    serializer_class = SecurityRequestLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SecurityRequestLog.objects.all().select_related('user').order_by('-created_at')


class TaskStatusViewSet(viewsets.ModelViewSet):
    queryset = TaskStatus.objects.all()
    serializer_class = TaskStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return TaskStatus.objects.all().select_related('user').order_by('-created_at')


class ConfigViewSet(viewsets.ModelViewSet):
    queryset = Config.objects.all()
    serializer_class = ConfigSerializer
    permission_classes = [permissions.IsAuthenticated]


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user_id = self.request.query_params.get('user_id', None)
        queryset = Notification.objects.all().select_related('user').order_by('-created_at')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        unread_only = self.request.query_params.get('unread_only', None)
        if unread_only and unread_only.lower() == 'true':
            queryset = queryset.filter(read=False)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.read = True
        notification.save()
        return Response({'read': True})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        count = Notification.objects.filter(user_id=user_id, read=False).update(read=True)
        return Response({'marked_as_read': count})


class PasswordResetRequestViewSet(viewsets.ModelViewSet):
    queryset = PasswordResetRequest.objects.all()
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PasswordResetRequest.objects.all().select_related('user').order_by('-created_at')


@api_view(['GET'])
@permission_classes([])
def health_check(request):
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([])
def home(request):
    return Response({'message': 'SSM Backend API', 'version': '1.0.0'})
