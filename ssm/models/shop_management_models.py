from django.db import models
import uuid
from django.utils import timezone
from .base_models import User, Team


class Shop(models.Model):
    """
    Model representing a physical shop or retail location
    """
    SHOP_TYPES = [
        ('franchise', 'Franchise'),
        ('company_owned', 'Company Owned'),
        ('dealer', 'Dealer'),
        ('agent', 'Agent'),
        ('kiosk', 'Kiosk'),
        ('mall_counter', 'Mall Counter'),
        ('supermarket', 'Supermarket'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('pending_approval', 'Pending Approval'),
        ('closed', 'Closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basic Information
    shop_code = models.CharField(max_length=50, unique=True, help_text="Unique shop identifier")
    shop_name = models.CharField(max_length=200)
    shop_type = models.CharField(max_length=20, choices=SHOP_TYPES, default='agent')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_approval')

    # Location Information
    address = models.TextField()
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    county = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)

    # Contact Information
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(null=True, blank=True)
    alternative_phone = models.CharField(max_length=20, null=True, blank=True)

    # Business Information
    business_registration_number = models.CharField(max_length=100, null=True, blank=True)
    tax_pin = models.CharField(max_length=50, null=True, blank=True)
    business_license_url = models.URLField(null=True, blank=True)

    # Operational Information
    opening_hours = models.JSONField(default=dict, help_text="Store opening hours by day")
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    shop_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='managed_shops')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_shops')
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_shops')

    # Financial Information
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                        help_text="Commission percentage")

    # Metadata
    metadata = models.JSONField(default=dict, help_text="Additional shop-specific data")
    notes = models.TextField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='verified_shops')

    class Meta:
        db_table = 'shops'
        indexes = [
            models.Index(fields=['shop_code']),
            models.Index(fields=['status']),
            models.Index(fields=['region', 'city']),
            models.Index(fields=['team']),
        ]

    def __str__(self):
        return f"{self.shop_code} - {self.shop_name}"


class ShopInventory(models.Model):
    """
    Model to track SIM card inventory at shop level
    """
    INVENTORY_STATUS = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
        ('returned', 'Returned'),
        ('damaged', 'Damaged'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='inventory')
    sim_card = models.ForeignKey('SimCard', on_delete=models.CASCADE,
                               related_name='shop_inventory')

    # Inventory tracking
    status = models.CharField(max_length=20, choices=INVENTORY_STATUS, default='available')
    allocated_date = models.DateTimeField(auto_now_add=True)
    allocated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allocated_inventory')

    # Sale Information
    sold_date = models.DateTimeField(null=True, blank=True)
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='sold_inventory')
    customer_name = models.CharField(max_length=200, null=True, blank=True)
    customer_phone = models.CharField(max_length=20, null=True, blank=True)
    customer_id_number = models.CharField(max_length=50, null=True, blank=True)

    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission_earned = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Return/Damage Information
    return_date = models.DateTimeField(null=True, blank=True)
    return_reason = models.TextField(null=True, blank=True)
    returned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='returned_inventory')

    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'shop_inventory'
        unique_together = ['shop', 'sim_card']
        indexes = [
            models.Index(fields=['shop', 'status']),
            models.Index(fields=['sold_date']),
            models.Index(fields=['allocated_date']),
        ]

    def __str__(self):
        return f"{self.shop.shop_code} - {self.sim_card.serial_number} ({self.status})"


class ShopTransfer(models.Model):
    """
    Model to track SIM card transfers between shops
    """
    TRANSFER_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Transfer Details
    transfer_reference = models.CharField(max_length=50, unique=True)
    source_shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='outgoing_shop_transfers')
    destination_shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='incoming_shop_transfers')

    # Request Information
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_shop_transfers')
    request_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()

    # Approval Information
    status = models.CharField(max_length=20, choices=TRANSFER_STATUS, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='approved_shop_transfers')
    approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)

    # Transit Information
    dispatch_date = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='dispatched_transfers')
    expected_delivery_date = models.DateTimeField(null=True, blank=True)

    # Completion Information
    received_date = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='received_transfers')

    # SIM Cards in transfer
    sim_cards = models.JSONField(default=list, help_text="List of SIM card serial numbers")
    total_quantity = models.IntegerField(default=0)
    received_quantity = models.IntegerField(null=True, blank=True)

    notes = models.TextField(null=True, blank=True)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_shop_transfers')

    class Meta:
        db_table = 'shop_transfers'
        indexes = [
            models.Index(fields=['transfer_reference']),
            models.Index(fields=['status']),
            models.Index(fields=['source_shop', 'destination_shop']),
            models.Index(fields=['request_date']),
        ]

    def __str__(self):
        return f"{self.transfer_reference}: {self.source_shop.shop_code} → {self.destination_shop.shop_code}"


class ShopSales(models.Model):
    """
    Model to track sales transactions at shop level
    """
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit', 'Credit'),
    ]

    SALE_STATUS = [
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Sale Information
    sale_reference = models.CharField(max_length=50, unique=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='sales')
    sold_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shop_sales')
    sale_date = models.DateTimeField(auto_now_add=True)

    # Customer Information
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_id_number = models.CharField(max_length=50)
    customer_email = models.EmailField(null=True, blank=True)

    # SIM Card Information
    sim_card = models.ForeignKey('SimCard', on_delete=models.CASCADE, related_name='shop_sales')

    # Financial Information
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Payment Information
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    payment_reference = models.CharField(max_length=100, null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    change_given = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Status and Processing
    status = models.CharField(max_length=20, choices=SALE_STATUS, default='completed')
    receipt_number = models.CharField(max_length=50, null=True, blank=True)

    # Refund Information
    refund_date = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(null=True, blank=True)
    refunded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='refunded_sales')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'shop_sales'
        indexes = [
            models.Index(fields=['sale_reference']),
            models.Index(fields=['shop', 'sale_date']),
            models.Index(fields=['customer_phone']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.sale_reference} - {self.shop.shop_code} - {self.customer_name}"


class ShopPerformance(models.Model):
    """
    Model to track shop performance metrics
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='performance_records')

    # Time Period
    period_start = models.DateField()
    period_end = models.DateField()
    period_type = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], default='monthly')

    # Sales Metrics
    total_sales = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    average_sale_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Inventory Metrics
    opening_stock = models.IntegerField(default=0)
    stock_received = models.IntegerField(default=0)
    closing_stock = models.IntegerField(default=0)
    stock_returned = models.IntegerField(default=0)
    stock_damaged = models.IntegerField(default=0)

    # Quality Metrics
    quality_sales = models.IntegerField(default=0)
    non_quality_sales = models.IntegerField(default=0)
    quality_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Customer Metrics
    unique_customers = models.IntegerField(default=0)
    repeat_customers = models.IntegerField(default=0)
    customer_satisfaction_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)

    # Operational Metrics
    working_days = models.IntegerField(default=0)
    sales_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Rankings and Targets
    target_sales = models.IntegerField(null=True, blank=True)
    target_revenue = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    achievement_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Additional metrics as JSON
    additional_metrics = models.JSONField(default=dict)

    calculated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calculated_performance')

    class Meta:
        db_table = 'shop_performance'
        unique_together = ['shop', 'period_start', 'period_end', 'period_type']
        indexes = [
            models.Index(fields=['shop', 'period_type']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['total_revenue']),
        ]

    def __str__(self):
        return f"{self.shop.shop_code} - {self.period_type} - {self.period_start} to {self.period_end}"


class ShopTarget(models.Model):
    """
    Model to set and track shop targets
    """
    TARGET_TYPES = [
        ('sales_volume', 'Sales Volume'),
        ('revenue', 'Revenue'),
        ('commission', 'Commission'),
        ('quality_rate', 'Quality Rate'),
        ('customer_acquisition', 'Customer Acquisition'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='targets')
    target_type = models.CharField(max_length=30, choices=TARGET_TYPES)

    # Time Period
    period_start = models.DateField()
    period_end = models.DateField()
    period_type = models.CharField(max_length=20, choices=[
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], default='monthly')

    # Target Values
    target_value = models.DecimalField(max_digits=12, decimal_places=2)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    achievement_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Status
    is_active = models.BooleanField(default=True)
    is_achieved = models.BooleanField(default=False)
    achievement_date = models.DateField(null=True, blank=True)

    # Incentives
    incentive_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    incentive_paid = models.BooleanField(default=False)
    incentive_paid_date = models.DateField(null=True, blank=True)

    set_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='set_targets')
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'shop_targets'
        unique_together = ['shop', 'target_type', 'period_start', 'period_end']
        indexes = [
            models.Index(fields=['shop', 'period_start', 'period_end']),
            models.Index(fields=['target_type']),
            models.Index(fields=['is_achieved']),
        ]

    def __str__(self):
        return f"{self.shop.shop_code} - {self.target_type} - {self.period_start} to {self.period_end}"


class ShopAuditLog(models.Model):
    """
    Model to track all activities and changes in shops
    """
    ACTION_TYPES = [
        ('shop_created', 'Shop Created'),
        ('shop_updated', 'Shop Updated'),
        ('inventory_allocated', 'Inventory Allocated'),
        ('sale_completed', 'Sale Completed'),
        ('transfer_requested', 'Transfer Requested'),
        ('transfer_approved', 'Transfer Approved'),
        ('stock_received', 'Stock Received'),
        ('target_set', 'Target Set'),
        ('performance_calculated', 'Performance Calculated'),
        ('status_changed', 'Status Changed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shop_audit_logs')
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)

    # Before and after states for tracking changes
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)

    # Additional context
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    # Related objects
    related_object_type = models.CharField(max_length=50, null=True, blank=True)
    related_object_id = models.UUIDField(null=True, blank=True)

    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'shop_audit_logs'
        indexes = [
            models.Index(fields=['shop', 'created_at']),
            models.Index(fields=['action_type']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.shop.shop_code} - {self.action_type} by {self.user.full_name}"