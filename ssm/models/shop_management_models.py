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
    owner = models.ForeignKey(User,default=None,null=True,blank=True, on_delete=models.CASCADE, related_name='owner_shops')

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


class ProductCategory(models.Model):
    """
    Model for product categories (TVs, Phones, Accessories, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    parent_category = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='subcategories')

    # Display settings
    icon = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=20, null=True, blank=True)
    display_order = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_product_categories')

    class Meta:
        db_table = 'product_categories'
        verbose_name_plural = 'Product Categories'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['parent_category']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Supplier(models.Model):
    """
    Model for supplier records
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basic Information
    supplier_code = models.CharField(max_length=50, unique=True)
    supplier_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Contact Information
    contact_person = models.CharField(max_length=200, null=True, blank=True)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(null=True, blank=True)
    alternative_phone = models.CharField(max_length=20, null=True, blank=True)

    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, null=True, blank=True)

    # Business Information
    business_registration_number = models.CharField(max_length=100, null=True, blank=True)
    tax_pin = models.CharField(max_length=50, null=True, blank=True)

    # Financial Terms
    payment_terms = models.CharField(max_length=100, null=True, blank=True,
                                     help_text="e.g., Net 30, Net 60")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Rating and Performance
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True,
                                help_text="Rating out of 5")
    total_purchases = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Metadata
    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_suppliers')
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_suppliers')

    class Meta:
        db_table = 'suppliers'
        indexes = [
            models.Index(fields=['supplier_code']),
            models.Index(fields=['status']),
            models.Index(fields=['supplier_name']),
        ]

    def __str__(self):
        return f"{self.supplier_code} - {self.supplier_name}"


class Product(models.Model):
    """
    Model for products (TVs, Phones, Accessories, etc.)
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('discontinued', 'Discontinued'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basic Information
    product_code = models.CharField(max_length=50, unique=True)
    product_name = models.CharField(max_length=200)
    model = models.CharField(max_length=100, null=True, blank=True)
    brand = models.CharField(max_length=100, null=True, blank=True)

    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name='products')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Description and Specifications
    description = models.TextField(null=True, blank=True)
    specifications = models.JSONField(default=dict, help_text="Product technical specifications")

    # Pricing
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                    help_text="Purchase/cost price")
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                      help_text="Recommended retail price")

    # Stock Information
    total_stock = models.IntegerField(default=0, help_text="Total stock across all shops")
    reorder_level = models.IntegerField(default=0, help_text="Minimum stock level before alert")
    reorder_quantity = models.IntegerField(default=0, help_text="Quantity to reorder")

    # Supplier
    default_supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='supplied_products')

    # Media
    image_url = models.URLField(null=True, blank=True)
    thumbnail_url = models.URLField(null=True, blank=True)
    images = models.JSONField(default=list, help_text="Array of image URLs")

    # Dimensions and Weight (for shipping)
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                help_text="Weight in kg")
    dimensions = models.JSONField(default=dict, null=True, blank=True,
                                 help_text="Length, width, height in cm")

    # Warranty and Support
    warranty_period = models.IntegerField(null=True, blank=True, help_text="Warranty period in months")
    warranty_details = models.TextField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict)
    notes = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_products')
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_products')
    # shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='shop_products')

    class Meta:
        db_table = 'products'
        indexes = [
            models.Index(fields=['product_code']),
            models.Index(fields=['category']),
            models.Index(fields=['status']),
            models.Index(fields=['product_name']),
        ]

    def __str__(self):
        return f"{self.product_code} - {self.product_name}"


class ShopProductInventory(models.Model):
    """
    Model to track product inventory at shop level
    """
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('damaged', 'Damaged'),
        ('returned', 'Returned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_inventory')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='shop_inventory')

    # Stock levels
    quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    available_quantity = models.IntegerField(default=0)

    # Pricing (can override product pricing at shop level)
    shop_cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    shop_selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Stock alerts
    low_stock_alert = models.BooleanField(default=False)
    min_stock_level = models.IntegerField(default=0)

    # Location in shop
    shelf_location = models.CharField(max_length=50, null=True, blank=True)
    bin_location = models.CharField(max_length=50, null=True, blank=True)

    last_stock_count_date = models.DateTimeField(null=True, blank=True)
    last_stock_count_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='counted_inventory')

    class Meta:
        db_table = 'shop_product_inventory'
        unique_together = ['shop', 'product']
        indexes = [
            models.Index(fields=['shop', 'product']),
            models.Index(fields=['low_stock_alert']),
            models.Index(fields=['available_quantity']),
        ]

    def __str__(self):
        return f"{self.shop.shop_code} - {self.product.product_name} (Qty: {self.quantity})"


class StockMovement(models.Model):
    """
    Model to track all stock movements (in/out)
    """
    MOVEMENT_TYPES = [
        ('stock_in', 'Stock In'),
        ('stock_out', 'Stock Out'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('transfer_in', 'Transfer In'),
        ('transfer_out', 'Transfer Out'),
        ('adjustment', 'Adjustment'),
        ('damage', 'Damage'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Reference
    reference_number = models.CharField(max_length=50, unique=True)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    movement_date = models.DateTimeField(auto_now_add=True)

    # Shop and Product
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='stock_movements')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_movements')

    # Quantity
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Before and After stock
    stock_before = models.IntegerField()
    stock_after = models.IntegerField()

    # Supplier (for stock in)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='stock_movements')

    # Related documents
    purchase_order_number = models.CharField(max_length=50, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True)
    delivery_note = models.CharField(max_length=50, null=True, blank=True)

    # User tracking
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_stock_movements')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approved_stock_movements')

    # Notes
    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'stock_movements'
        indexes = [
            models.Index(fields=['reference_number']),
            models.Index(fields=['shop', 'movement_date']),
            models.Index(fields=['product', 'movement_date']),
            models.Index(fields=['movement_type']),
        ]

    def __str__(self):
        return f"{self.reference_number} - {self.movement_type} - {self.product.product_name}"


class PurchaseOrder(models.Model):
    """
    Model for purchase orders to suppliers
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('ordered', 'Ordered'),
        ('partial', 'Partially Received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # PO Details
    po_number = models.CharField(max_length=50, unique=True)
    po_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='purchase_orders')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Financial
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Items (stored as JSON for simplicity)
    items = models.JSONField(default=list, help_text="Array of order items")

    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approved_purchase_orders')
    approval_date = models.DateTimeField(null=True, blank=True)

    # Delivery
    actual_delivery_date = models.DateField(null=True, blank=True)
    delivery_notes = models.TextField(null=True, blank=True)

    # User tracking
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_purchase_orders')

    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'purchase_orders'
        indexes = [
            models.Index(fields=['po_number']),
            models.Index(fields=['supplier', 'po_date']),
            models.Index(fields=['shop', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.po_number} - {self.supplier.supplier_name}"


class ProductSale(models.Model):
    """
    Model to track product sales transactions
    """
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit', 'Credit'),
    ]

    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Sale Information
    sale_number = models.CharField(max_length=50, unique=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_sales')
    sale_date = models.DateTimeField(auto_now_add=True)

    # Items (can be multiple products)
    items = models.JSONField(default=list, help_text="Array of sold items with product, quantity, price")

    # Customer Information (optional)
    customer_name = models.CharField(max_length=200, null=True, blank=True)
    customer_phone = models.CharField(max_length=20, null=True, blank=True)
    customer_email = models.EmailField(null=True, blank=True)

    # Financial
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    payment_reference = models.CharField(max_length=100, null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    change_given = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    receipt_number = models.CharField(max_length=50, null=True, blank=True)

    # User
    sold_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_sales')

    # Refund
    refund_date = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(null=True, blank=True)
    refunded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='refunded_product_sales')

    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'product_sales'
        indexes = [
            models.Index(fields=['sale_number']),
            models.Index(fields=['shop', 'sale_date']),
            models.Index(fields=['status']),
            models.Index(fields=['customer_phone']),
        ]

    def __str__(self):
        return f"{self.sale_number} - {self.shop.shop_code} - KES {self.total_amount}"