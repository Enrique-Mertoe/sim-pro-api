from django.db import models
import uuid
from .base_models import User
from .shop_management_models import Product, Shop


class ProductInstance(models.Model):
    """
    Model to track individual product units with serial numbers
    """
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
        ('damaged', 'Damaged'),
        ('returned', 'Returned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Link to product catalog
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='instances')
    
    # Individual unit tracking (barcode = serial number)
    serial_number = models.CharField(max_length=100, unique=True)
    barcode = models.CharField(max_length=100, unique=True)  # Same as serial_number
    
    # Current location and status
    current_shop = models.ForeignKey(Shop, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='product_instances')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Sale information
    sold_date = models.DateTimeField(null=True, blank=True)
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='sold_instances')
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Customer info (when sold)
    customer_name = models.CharField(max_length=200, null=True, blank=True)
    customer_phone = models.CharField(max_length=20, null=True, blank=True)
    
    # Tracking
    allocated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allocated_instances')
    allocated_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_instances'
        indexes = [
            models.Index(fields=['serial_number']),
            models.Index(fields=['barcode']),
            models.Index(fields=['product', 'status']),
            models.Index(fields=['current_shop', 'status']),
        ]

    def __str__(self):
        return f"{self.product.product_name} - {self.serial_number}"