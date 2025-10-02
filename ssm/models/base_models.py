from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid
from django.utils import timezone


class SSMAuthUser(AbstractUser):
    """
    Custom Django User model with Supabase-compatible authentication fields
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Supabase-compatible authentication fields
    email_confirmed = models.BooleanField(default=False)
    phone_confirmed = models.BooleanField(default=False)
    email_confirmed_at = models.DateTimeField(null=True, blank=True)
    phone_confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmation_token = models.TextField(null=True, blank=True)
    recovery_token = models.TextField(null=True, blank=True)
    email_change_token = models.TextField(null=True, blank=True)
    new_email = models.EmailField(null=True, blank=True)
    invited_at = models.DateTimeField(null=True, blank=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    recovery_sent_at = models.DateTimeField(null=True, blank=True)
    email_change_sent_at = models.DateTimeField(null=True, blank=True)
    new_phone = models.TextField(null=True, blank=True)
    phone_change_token = models.TextField(null=True, blank=True)
    phone_change_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    email_change_confirm_status = models.SmallIntegerField(default=0)
    banned_until = models.DateTimeField(null=True, blank=True)

    # Phone number for authentication
    phone = models.TextField(null=True, blank=True)

    # Metadata fields for Supabase compatibility
    raw_app_meta_data = models.JSONField(default=dict, blank=True)
    raw_user_meta_data = models.JSONField(default=dict, blank=True)

    # Additional timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auth_users'

    def __str__(self):
        return self.email or self.username


class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(null=True, blank=True)
    full_name = models.TextField()
    id_number = models.TextField()
    id_front_url = models.TextField()
    id_back_url = models.TextField()
    phone_number = models.TextField(null=True, blank=True)
    mobigo_number = models.TextField(null=True, blank=True)
    role = models.TextField()
    team = models.ForeignKey('Team', default=None, on_delete=models.SET_NULL, null=True, blank=True)
    staff_type = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    auth_user = models.OneToOneField("ssm.SSMAuthUser", on_delete=models.CASCADE, null=True, blank=True)
    status = models.TextField(default='ACTIVE')
    admin = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    username = models.TextField(null=True, blank=True)
    is_first_login = models.BooleanField(default=False)
    password = models.CharField(max_length=255, null=True, blank=True)
    soft_delete = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.full_name


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.TextField()
    leader = models.ForeignKey(User, default=None, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='led_teams')
    region = models.TextField()
    territory = models.TextField(null=True, blank=True)
    van_number_plate = models.TextField(null=True, blank=True)
    van_location = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='administered_teams')

    class Meta:
        db_table = 'teams'

    def __str__(self):
        return self.name


class TeamGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="groups"
    )
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='admin_team_groups')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)  # NEW
    is_active = models.BooleanField(default=True)  # NEW
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # RECOMMENDED

    class Meta:
        db_table = "team_groups"
        unique_together = ("team", "name")

    def __str__(self):
        return f"{self.name} ({self.team.name})"


class TeamGroupMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        TeamGroup,
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    user = models.ForeignKey(
        User,  # or your custom user model
        on_delete=models.CASCADE,
        related_name="group_memberships"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "team_group_memberships"
        unique_together = ("group", "user")

    def __str__(self):
        return f"{self.user.name} in {self.group.name}"


class TeamMetadata(models.Model):
    team = models.OneToOneField(Team, on_delete=models.CASCADE, related_name="metadata")
    performance = models.JSONField(default=dict, blank=True, null=True)
    notes = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Metadata for {self.team.name}"

    class Meta:
        db_table = 'team_metadata'


class SimCard(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    serial_number = models.TextField()
    sold_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='sold_sim_cards')
    sale_date = models.DateTimeField(null=True, blank=True)
    sale_location = models.TextField(null=True, blank=True)
    activation_date = models.DateTimeField(null=True, blank=True)
    top_up_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    top_up_date = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default='PENDING')
    team = models.ForeignKey(Team, default=None, null=True, blank=True, on_delete=models.SET_NULL)
    region = models.TextField(null=True, blank=True)
    fraud_flag = models.BooleanField(default=False)
    fraud_reason = models.TextField(null=True, blank=True)
    quality = models.TextField(default='NONQUALITY')
    match = models.TextField(default='N')
    assigned_on = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    registered_on = models.DateTimeField(null=True, blank=True)
    assigned_to_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='assigned_sim_cards')
    registered_by_user = models.ForeignKey(User, default=None, null=True, blank=True, on_delete=models.CASCADE,
                                           related_name='registered_sim_cards')
    batch = models.ForeignKey('BatchMetadata', on_delete=models.CASCADE, related_name='sim_cards', default=None)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_sim_cards')
    usage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    in_transit = models.BooleanField(default=False)
    lot = models.TextField(null=True, blank=True)
    ba_msisdn = models.TextField(null=True, blank=True)
    mobigo = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'sim_cards'

    def __str__(self):
        return self.serial_number


class BatchMetadata(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    batch_id = models.TextField()
    order_number = models.TextField(null=True, blank=True)
    requisition_number = models.TextField(null=True, blank=True)
    company_name = models.TextField(null=True, blank=True)
    collection_point = models.TextField(null=True, blank=True)
    move_order_number = models.TextField(null=True, blank=True)
    date_created = models.TextField(null=True, blank=True)
    lot_numbers = models.JSONField(default=list)
    item_description = models.TextField(null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    created_by_user = models.ForeignKey(User, on_delete=models.CASCADE)
    teams = models.JSONField(default=list)
    admin = models.ForeignKey(User, default=None, on_delete=models.CASCADE, related_name='admin_batches')

    class Meta:
        db_table = 'batch_metadata'

    def __str__(self):
        return self.batch_id


class LotMetadata(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    batch = models.ForeignKey(BatchMetadata, on_delete=models.CASCADE, related_name='lots')
    lot_number = models.TextField()
    serial_numbers = models.JSONField(default=list)
    assigned_team = models.ForeignKey('Team', on_delete=models.SET_NULL, null=True, blank=True)
    assigned_on = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default='PENDING')  # PENDING, ASSIGNED, DISTRIBUTED
    total_sims = models.IntegerField()
    quality_count = models.IntegerField(default=0)
    nonquality_count = models.IntegerField(default=0)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_lots')

    class Meta:
        db_table = 'lot_metadata'
        unique_together = ['batch', 'lot_number']

    def __str__(self):
        return f"{self.batch.batch_id} - {self.lot_number}"


class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.TextField()
    details = models.JSONField()
    ip_address = models.TextField(null=True, blank=True)
    device_info = models.TextField(null=True, blank=True)
    is_offline_action = models.BooleanField(default=False)
    sync_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'activity_logs'

    def __str__(self):
        return f"{self.user.full_name} - {self.action_type}"


class OnboardingRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='onboarding_requests')
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_onboarding_requests')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='reviewed_requests')
    request_type = models.TextField(default='')
    review_notes = models.TextField(null=True, blank=True)
    review_date = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default='pending')
    user_data = models.JSONField(default=dict,
                                 help_text='User details as JSON: full_name, id_number, id_front_url, id_back_url, phone_number, mobigo_number, role, team_id, staff_type, email, username, etc.')

    class Meta:
        db_table = 'onboarding_requests'

    def __str__(self):
        return f"{self.full_name} - {self.status}"


class SimCardTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    source_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='outgoing_transfers')
    destination_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='incoming_transfers')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_transfers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_transfers')
    approval_date = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default='PENDING')
    reason = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    sim_cards = models.JSONField()
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_transfers')

    class Meta:
        db_table = 'sim_card_transfers'

    def __str__(self):
        return f"Transfer from {self.source_team.name} to {self.destination_team.name}"


class PaymentRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reference = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    plan_id = models.TextField()
    phone_number = models.TextField()
    status = models.TextField(default='pending')
    provider_id = models.TextField(null=True, blank=True)
    checkout_url = models.TextField(null=True, blank=True)
    transaction_id = models.TextField(null=True, blank=True)
    payment_method = models.TextField(null=True, blank=True)
    payment_details = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'payment_requests'

    def __str__(self):
        return f"{self.user.full_name} - {self.amount}"


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan_id = models.UUIDField()
    status = models.TextField(default='active')
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    payment_reference = models.TextField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    cancellation_date = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)
    is_trial = models.BooleanField(default=False)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    trial_days = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f"{self.user.full_name} - {self.status}"


class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price_monthly = models.IntegerField()
    price_annual = models.IntegerField()
    features = models.JSONField(default=list)
    is_recommended = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_plans'

    def __str__(self):
        return self.name


class ForumTopic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.TextField()
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_topics')
    is_pinned = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    view_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'forum_topics'

    def __str__(self):
        return self.title


class ForumPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(ForumTopic, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_posts')

    class Meta:
        db_table = 'forum_posts'

    def __str__(self):
        return f"Post by {self.created_by.full_name} on {self.topic.title}"


class ForumLike(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic = models.ForeignKey(ForumTopic, on_delete=models.CASCADE, null=True, blank=True)
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'forum_likes'
        constraints = [
            models.CheckConstraint(
                check=(
                        (models.Q(topic__isnull=False) & models.Q(post__isnull=True)) |
                        (models.Q(topic__isnull=True) & models.Q(post__isnull=False))
                ),
                name='topic_or_post_required'
            )
        ]

    def __str__(self):
        if self.topic:
            return f"{self.user.full_name} liked topic: {self.topic.title}"
        return f"{self.user.full_name} liked post by {self.post.created_by.full_name}"


class SecurityRequestLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    request_id = models.UUIDField(default=uuid.uuid4)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(null=True, blank=True)
    referer = models.TextField(null=True, blank=True)
    origin = models.TextField(null=True, blank=True)
    method = models.CharField(max_length=10)
    path = models.TextField()
    query_params = models.JSONField(null=True, blank=True)
    headers = models.JSONField(null=True, blank=True)
    body_size = models.IntegerField(null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    asn = models.IntegerField(null=True, blank=True)
    isp = models.CharField(max_length=255, null=True, blank=True)
    threat_level = models.CharField(max_length=20, default='safe')
    threat_categories = models.JSONField(null=True, blank=True)
    risk_score = models.IntegerField(default=0)
    confidence_score = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    signature_matches = models.JSONField(null=True, blank=True)
    behavioral_flags = models.JSONField(null=True, blank=True)
    anomaly_score = models.DecimalField(max_digits=5, decimal_places=4, default=0.0)
    response_status = models.IntegerField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    blocked = models.BooleanField(default=False)
    challenge_issued = models.BooleanField(default=False)
    session_id = models.CharField(max_length=255, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'security_request_logs'

    def __str__(self):
        return f"{self.ip_address} - {self.method} {self.path}"


class TaskStatus(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)
    progress = models.IntegerField(default=0)
    total_records = models.IntegerField(default=0)
    processed_records = models.IntegerField(default=0)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_status'

    def __str__(self):
        return f"Task {self.id} - {self.status}"


class Config(models.Model):
    key = models.TextField(primary_key=True)
    value = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'config'

    def __str__(self):
        return self.key


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.TextField()
    message = models.TextField()
    type = models.TextField()
    read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications'

    def __str__(self):
        return f"{self.user.full_name} - {self.title}"


class PasswordResetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("ssm.SSMAuthUser", on_delete=models.CASCADE)
    token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_requests'

    def __str__(self):
        return f"Reset request for {self.user.full_name}"


class AdminOnboarding(models.Model):
    """
    Tracks onboarding progress for admin users (tenants)
    Only admins go through onboarding process
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.OneToOneField(User, on_delete=models.CASCADE, related_name='onboarding_status')

    # Onboarding steps completion
    email_verified = models.BooleanField(default=False)
    profile_completed = models.BooleanField(default=False)
    business_info_completed = models.BooleanField(default=False)
    system_tour_completed = models.BooleanField(default=False)
    onboarding_completed = models.BooleanField(default=False)

    # Billing activation
    billing_active = models.BooleanField(default=False)
    billing_start_date = models.DateTimeField(null=True, blank=True)

    # Timestamps for each step
    email_verified_at = models.DateTimeField(null=True, blank=True)
    profile_completed_at = models.DateTimeField(null=True, blank=True)
    business_info_completed_at = models.DateTimeField(null=True, blank=True)
    system_tour_completed_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_onboarding'

    def __str__(self):
        return f"Onboarding for {self.admin.full_name}"


class BusinessInfo(models.Model):
    """
    Stores business/company information for admin users (tenants)
    Separate from User model to keep tenant-level data isolated
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.OneToOneField(User, on_delete=models.CASCADE, related_name='business_info')

    # Business details
    dealer_code = models.TextField(unique=True)

    # Contact information
    contact_phone = models.TextField(null=True, blank=True)

    # Additional metadata
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_info'

    def __str__(self):
        return self.dealer_code
