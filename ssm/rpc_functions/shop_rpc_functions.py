from django.db import models
from django.db.models import Q, Sum, Count, Avg, F
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import calendar

from django.utils import timezone

from ..models.shop_management_models import (
    Shop, ProductCategory, Supplier, Product, ShopProductInventory,
    StockMovement, PurchaseOrder, ProductSale
)
from ..models.product_instance_model import ProductInstance


# ==================== SHOP MANAGEMENT ====================

def get_all_shops(user):
    """
    Get all shops with summary statistics
    """
    base = Shop.objects.filter(admin=user if user.role == "admin" and not user.admin else user.admin)
    if user.admin and user.role not in ["admin"]:
        base = base.filter(owner=user)
    shops = base.select_related('shop_manager', 'team')

    result = []
    for shop in shops:
        # Get inventory count
        inventory_count = ShopProductInventory.objects.filter(shop=shop).aggregate(
            total_products=Count('id'),
            total_stock=Sum('quantity')
        )

        # Get sales summary
        sales_summary = ProductSale.objects.filter(
            shop=shop,
            status='completed'
        ).aggregate(
            total_sales=Count('id'),
            total_revenue=Sum('total_amount')
        )

        result.append({
            'id': str(shop.id),
            'shop_code': shop.shop_code,
            'shop_name': shop.shop_name,
            'shop_type': shop.shop_type,
            'status': shop.status,
            'city': shop.city,
            'region': shop.region,
            'phone_number': shop.phone_number,
            'shop_manager': {
                'name': shop.shop_manager.full_name if shop.shop_manager else None,
                'email': shop.shop_manager.email if shop.shop_manager else None
            } if shop.shop_manager else None,
            'inventory': {
                'total_products': inventory_count['total_products'] or 0,
                'total_stock': inventory_count['total_stock'] or 0
            },
            'sales': {
                'total_sales': sales_summary['total_sales'] or 0,
                'total_revenue': float(sales_summary['total_revenue'] or 0)
            },
            "owner": {
                "id": shop.owner.id,
                "full_name": shop.owner.full_name,
            } if shop.owner else None,
            'created_at': shop.created_at.isoformat(),
        })

    return result


def create_shop(user, shop_data):
    """
    Create a new shop with auto-generated shop code
    """
    admin_user = user.admin
    if not admin_user:
        return {'success': False, 'error': 'Invalid Operation'}
    if user.role not in ["team_leader", "mpesa_only_agent"]:
        return {'success': False, 'error': 'Unable to complete operation'}
    # Generate shop code based on city and region
    city_prefix = shop_data['city'][:3].upper()
    region_prefix = shop_data['region'][:3].upper()

    # Get count of existing shops in same region for numbering
    existing_count = Shop.objects.filter(
        region__iexact=shop_data['region'],
        admin=admin_user,
        owner=user
    ).count() + 1

    # Generate unique shop code
    shop_code = f"{city_prefix}-{region_prefix}-{existing_count:03d}"

    # Ensure uniqueness
    while Shop.objects.filter(shop_code=shop_code, admin=admin_user, owner=user).exists():
        existing_count += 1
        shop_code = f"{city_prefix}-{region_prefix}-{existing_count:03d}"

    shop = Shop.objects.create(
        shop_code=shop_code,
        shop_name=shop_data['shop_name'],
        shop_type=shop_data.get('shop_type', 'agent'),
        status=shop_data.get('status', 'pending_approval'),
        address=shop_data['address'],
        city=shop_data['city'],
        region=shop_data['region'],
        county=shop_data.get('county'),
        phone_number=shop_data['phone_number'],
        email=shop_data.get('email'),
        created_by=user,
        admin=admin_user,
        owner=user,
    )

    return {'success': True, 'shop_id': str(shop.id), 'shop_code': shop_code}


# ==================== PRODUCT MANAGEMENT ====================

def get_all_products(user, category_id=None, search=None):
    """
    Get all products with filtering options
    """
    if user.admin and user.role not in ["team_leader"]:
        raise "UnAuthorised operation"
    query = Product.objects.filter(admin=user.admin or user).select_related('category', 'default_supplier')

    if category_id:
        query = query.filter(category_id=category_id)

    if search:
        query = query.filter(
            Q(product_name__icontains=search) |
            Q(product_code__icontains=search) |
            Q(barcode__icontains=search)
        )

    products = []
    for product in query:
        products.append({
            'id': str(product.id),
            'product_code': product.product_code,
            'product_name': product.product_name,
            'model': product.model,
            'brand': product.brand,
            'category': {
                'id': str(product.category.id),
                'name': product.category.name,
                'code': product.category.code
            },
            'status': product.status,
            'cost_price': float(product.cost_price),
            'selling_price': float(product.selling_price),
            'total_stock': product.total_stock,
            'reorder_level': product.reorder_level,
            'supplier': {
                'id': str(product.default_supplier.id),
                'name': product.default_supplier.supplier_name
            } if product.default_supplier else None,
            'image_url': product.image_url,
            'created_at': product.created_at.isoformat()
        })

    return products


def create_product(user, product_data):
    """
    Create a new product with optional serial numbers for instances
    """
    # Auto-generate product code from brand and model
    brand = product_data.get('brand', 'PROD')[:3].upper()
    model = product_data.get('model', product_data['product_name'])[:5].upper().replace(' ', '')

    # Get admin user
    admin_user = user if user.role == "admin" and not user.admin else user.admin

    # Count existing products with similar code
    base_code = f"{brand}-{model}"
    existing_count = Product.objects.filter(
        product_code__startswith=base_code,
        admin=admin_user
    ).count() + 1

    product_code = f"{base_code}-{existing_count:03d}"

    # Create single product
    product = Product.objects.create(
        product_code=product_code,
        product_name=product_data['product_name'],
        model=product_data.get('model'),
        brand=product_data.get('brand'),
        category_id=product_data['category_id'],
        description=product_data.get('description'),
        cost_price=product_data['cost_price'],
        selling_price=product_data['selling_price'],
        retail_price=product_data.get('retail_price'),
        reorder_level=product_data.get('reorder_level', 0),
        reorder_quantity=product_data.get('reorder_quantity', 0),

        created_by=user,
        admin=admin_user,
        # shop_id=product_data['shop_id']
    )

    # Handle serial numbers if provided
    # serial_numbers = product_data.get('barcodes', [])
    # print("prd",product_data)
    # shop_id = product_data.get('shop_id')
    #
    # if serial_numbers and shop_id:
    #     instances = []
    #     for serial in serial_numbers:
    #         instance = ProductInstance.objects.create(
    #             product=product,
    #             serial_number=serial,
    #             barcode=serial,  # barcode = serial number
    #             current_shop_id=shop_id,
    #             status='available',
    #             allocated_by=user
    #         )
    #         instances.append(str(instance.id))
    #
    #     # Create/update shop inventory
    #     inventory, created = ShopProductInventory.objects.get_or_create(
    #         shop_id=shop_id,
    #         product=product,
    #         defaults={'quantity': 0, 'available_quantity': 0}
    #     )
    #     inventory.quantity += len(serial_numbers)
    #     inventory.available_quantity += len(serial_numbers)
    #     inventory.save()
    #
    #     return {
    #         'success': True,
    #         'product_id': str(product.id),
    #         'instances_created': len(instances),
    #         'instance_ids': instances
    #     }

    return {'success': True, 'product_id': str(product.id)}


def allocate_product_instances(user, product_id, shop_id, serial_numbers):
    """
    Allocate product instances with serial numbers to a shop
    """
    product = Product.objects.get(id=product_id)
    shop = Shop.objects.get(id=shop_id)

    instances = []
    for serial in serial_numbers:
        instance = ProductInstance.objects.create(
            product=product,
            serial_number=serial,
            current_shop=shop,
            status='available',
            allocated_by=user
        )
        instances.append(str(instance.id))

    # Update shop inventory quantity
    inventory, created = ShopProductInventory.objects.get_or_create(
        shop=shop,
        product=product,
        defaults={'quantity': 0, 'available_quantity': 0}
    )
    inventory.quantity += len(serial_numbers)
    inventory.available_quantity += len(serial_numbers)
    inventory.save()

    return {'success': True, 'instance_ids': instances}


def sell_product_by_barcode(user, shop_id, barcode, customer_data, sale_price):
    """
    Sell a product by scanning its barcode (which is the serial number)
    """
    try:
        instance = ProductInstance.objects.get(
            barcode=barcode,
            current_shop_id=shop_id,
            status='available'
        )

        # Mark as sold
        instance.status = 'sold'
        instance.sold_date = timezone.now()
        instance.sold_by = user
        instance.sale_price = sale_price
        instance.customer_name = customer_data.get('name')
        instance.customer_phone = customer_data.get('phone')
        instance.save()

        # Update shop inventory
        inventory = ShopProductInventory.objects.get(
            shop_id=shop_id,
            product=instance.product
        )
        inventory.available_quantity -= 1
        inventory.save()

        return {
            'success': True,
            'product': {
                'name': instance.product.product_name,
                'price': float(sale_price),
                'serial': instance.serial_number
            }
        }

    except ProductInstance.DoesNotExist:
        return {'success': False, 'error': 'Product not found or not available'}


def update_product(user, product_id, product_data):
    """
    Update product information
    """
    product = Product.objects.get(id=product_id, admin=user)

    for key, value in product_data.items():
        if hasattr(product, key):
            setattr(product, key, value)

    product.save()

    return {'success': True}


# ==================== PRODUCT CATEGORIES ====================

def get_shop_inventory_with_serials(user, shop_id):
    """
    Get shop inventory with available serial numbers
    """
    shop = Shop.objects.get(id=shop_id)
    inventory = ShopProductInventory.objects.filter(shop=shop).select_related('product')

    result = []
    for inv in inventory:
        # Get available instances
        instances = ProductInstance.objects.filter(
            product=inv.product,
            current_shop=shop,
            status='available'
        ).values_list('serial_number', flat=True)

        result.append({
            'product_id': str(inv.product.id),
            'product_name': inv.product.product_name,
            'total_quantity': inv.quantity,
            'available_quantity': inv.available_quantity,
            'available_serials': list(instances),
            'selling_price': float(inv.product.selling_price)
        })

    return result


def get_all_categories(user):
    """
    Get all product categories
    """
    categories = ProductCategory.objects.filter(
        admin=user if user.role == "admin" and not user.admin else user.admin).prefetch_related('products')

    result = []
    for category in categories:
        result.append({
            'id': str(category.id),
            'name': category.name,
            'code': category.code,
            'description': category.description,
            'icon': category.icon,
            'color': category.color,
            'product_count': category.products.count(),
            'is_active': category.is_active
        })

    return result


def create_category(user, category_data):
    """
    Create a new product category
    """
    # Auto-generate category code from name
    name = category_data['name']
    code = name.upper().replace(' ', '_')[:10]

    # Ensure uniqueness
    admin_user = user if user.role == "admin" and not user.admin else user.admin
    existing_count = ProductCategory.objects.filter(
        code__startswith=code,
        admin=admin_user
    ).count()

    if existing_count > 0:
        code = f"{code}_{existing_count + 1}"

    category = ProductCategory.objects.create(
        name=category_data['name'],
        code=code,
        description=category_data.get('description'),
        icon=category_data.get('icon'),
        color=category_data.get('color'),
        admin=admin_user
    )

    return {'success': True, 'category_id': str(category.id)}


# ==================== INVENTORY MANAGEMENT ====================

def get_shop_inventory(user, shop_id):
    """
    Get inventory for a specific shop
    """
    inventory = ShopProductInventory.objects.filter(
        shop_id=shop_id,
        shop__admin=user
    ).select_related('product', 'product__category')

    result = []
    for item in inventory:
        result.append({
            'id': str(item.id),
            'product': {
                'id': str(item.product.id),
                'name': item.product.product_name,
                'code': item.product.product_code,
                'barcode': item.product.barcode,
                'category': item.product.category.name
            },
            'quantity': item.quantity,
            'reserved_quantity': item.reserved_quantity,
            'available_quantity': item.available_quantity,
            'shop_selling_price': float(item.shop_selling_price) if item.shop_selling_price else float(
                item.product.selling_price),
            'low_stock_alert': item.low_stock_alert,
            'min_stock_level': item.min_stock_level,
            'shelf_location': item.shelf_location
        })

    return result


def get_low_stock_alerts(user, shop_id=None):
    """
    Get products with low stock alerts
    """
    query = ShopProductInventory.objects.filter(
        shop__admin=user,
        low_stock_alert=True
    ).select_related('shop', 'product')

    if shop_id:
        query = query.filter(shop_id=shop_id)

    alerts = []
    for item in query:
        alerts.append({
            'id': str(item.id),
            'shop': {
                'id': str(item.shop.id),
                'name': item.shop.shop_name,
                'code': item.shop.shop_code
            },
            'product': {
                'id': str(item.product.id),
                'name': item.product.product_name,
                'code': item.product.product_code
            },
            'current_stock': item.quantity,
            'min_stock_level': item.min_stock_level,
            'reorder_quantity': item.product.reorder_quantity
        })

    return alerts


def record_stock_movement(user, movement_data):
    """
    Record stock in/out movement
    """
    # Get current stock
    inventory = ShopProductInventory.objects.get(
        shop_id=movement_data['shop_id'],
        product_id=movement_data['product_id']
    )

    stock_before = inventory.quantity
    quantity = movement_data['quantity']
    movement_type = movement_data['movement_type']

    # Calculate new stock
    if movement_type in ['stock_in', 'return', 'transfer_in']:
        stock_after = stock_before + quantity
    else:
        stock_after = stock_before - quantity

    # Create movement record
    movement = StockMovement.objects.create(
        reference_number=movement_data.get('reference_number', f"SM-{uuid.uuid4().hex[:8].upper()}"),
        movement_type=movement_type,
        shop_id=movement_data['shop_id'],
        product_id=movement_data['product_id'],
        quantity=quantity,
        unit_cost=movement_data.get('unit_cost'),
        total_cost=movement_data.get('total_cost'),
        stock_before=stock_before,
        stock_after=stock_after,
        supplier_id=movement_data.get('supplier_id'),
        purchase_order_number=movement_data.get('purchase_order_number'),
        invoice_number=movement_data.get('invoice_number'),
        notes=movement_data.get('notes'),
        created_by=user
    )

    # Update inventory
    inventory.quantity = stock_after
    inventory.available_quantity = stock_after - inventory.reserved_quantity

    # Check low stock alert
    if inventory.min_stock_level > 0 and stock_after <= inventory.min_stock_level:
        inventory.low_stock_alert = True
    else:
        inventory.low_stock_alert = False

    inventory.save()

    # Update product total stock
    product = Product.objects.get(id=movement_data['product_id'])
    total_stock = ShopProductInventory.objects.filter(product=product).aggregate(
        total=Sum('quantity')
    )['total'] or 0
    product.total_stock = total_stock
    product.save()

    return {
        'success': True,
        'movement_id': str(movement.id),
        'stock_after': stock_after
    }


# ==================== SALES MANAGEMENT ====================

def record_sale(user, sale_data):
    """
    Record a product sale
    """
    sale = ProductSale.objects.create(
        sale_number=sale_data.get('sale_number', f"SALE-{uuid.uuid4().hex[:8].upper()}"),
        shop_id=sale_data['shop_id'],
        items=sale_data['items'],
        customer_name=sale_data.get('customer_name'),
        customer_phone=sale_data.get('customer_phone'),
        customer_email=sale_data.get('customer_email'),
        subtotal=sale_data['subtotal'],
        tax_amount=sale_data.get('tax_amount', 0),
        discount_amount=sale_data.get('discount_amount', 0),
        total_amount=sale_data['total_amount'],
        payment_method=sale_data['payment_method'],
        payment_reference=sale_data.get('payment_reference'),
        amount_paid=sale_data['amount_paid'],
        change_given=sale_data.get('change_given', 0),
        receipt_number=sale_data.get('receipt_number'),
        sold_by=user
    )

    # Update inventory for each item
    for item in sale_data['items']:
        # Record as stock out movement
        record_stock_movement(user, {
            'shop_id': sale_data['shop_id'],
            'product_id': item['product_id'],
            'quantity': item['quantity'],
            'movement_type': 'sale',
            'reference_number': sale.sale_number
        })

    return {
        'success': True,
        'sale_id': str(sale.id),
        'sale_number': sale.sale_number,
        'receipt_number': sale.receipt_number
    }


def get_sales_history(user, shop_id=None, start_date=None, end_date=None):
    """
    Get sales history with filtering
    """
    query = ProductSale.objects.filter(sold_by__admin=user).select_related('shop')

    if shop_id:
        query = query.filter(shop_id=shop_id)

    if start_date:
        query = query.filter(sale_date__gte=start_date)

    if end_date:
        query = query.filter(sale_date__lte=end_date)

    sales = []
    for sale in query.order_by('-sale_date'):
        sales.append({
            'id': str(sale.id),
            'sale_number': sale.sale_number,
            'shop': {
                'id': str(sale.shop.id),
                'name': sale.shop.shop_name
            },
            'sale_date': sale.sale_date.isoformat(),
            'customer_name': sale.customer_name,
            'customer_phone': sale.customer_phone,
            'items': sale.items,
            'total_amount': float(sale.total_amount),
            'payment_method': sale.payment_method,
            'status': sale.status,
            'receipt_number': sale.receipt_number
        })

    return sales


# ==================== SUPPLIER MANAGEMENT ====================

def get_all_suppliers(user):
    """
    Get all suppliers
    """
    suppliers = Supplier.objects.filter(admin=user)

    result = []
    for supplier in suppliers:
        result.append({
            'id': str(supplier.id),
            'supplier_code': supplier.supplier_code,
            'supplier_name': supplier.supplier_name,
            'status': supplier.status,
            'contact_person': supplier.contact_person,
            'phone_number': supplier.phone_number,
            'email': supplier.email,
            'city': supplier.city,
            'country': supplier.country,
            'payment_terms': supplier.payment_terms,
            'credit_limit': float(supplier.credit_limit),
            'current_balance': float(supplier.current_balance),
            'rating': float(supplier.rating) if supplier.rating else None,
            'total_purchases': float(supplier.total_purchases)
        })

    return result


def create_supplier(user, supplier_data):
    """
    Create a new supplier
    """
    supplier = Supplier.objects.create(
        supplier_code=supplier_data['supplier_code'],
        supplier_name=supplier_data['supplier_name'],
        contact_person=supplier_data.get('contact_person'),
        phone_number=supplier_data['phone_number'],
        email=supplier_data.get('email'),
        address=supplier_data['address'],
        city=supplier_data['city'],
        country=supplier_data['country'],
        payment_terms=supplier_data.get('payment_terms'),
        created_by=user,
        admin=user
    )

    return {'success': True, 'supplier_id': str(supplier.id)}


# ==================== ANALYTICS & REPORTING ====================

def get_shop_analytics(user, shop_id, start_date=None, end_date=None):
    """
    Get analytics for a specific shop
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Sales analytics
    sales = ProductSale.objects.filter(
        shop_id=shop_id,
        shop__admin=user,
        sale_date__gte=start_date,
        sale_date__lte=end_date,
        status='completed'
    )

    sales_summary = sales.aggregate(
        total_sales=Count('id'),
        total_revenue=Sum('total_amount'),
        average_sale=Avg('total_amount')
    )

    # Inventory summary
    inventory_summary = ShopProductInventory.objects.filter(
        shop_id=shop_id
    ).aggregate(
        total_products=Count('id'),
        total_stock_value=Sum(F('quantity') * F('product__cost_price')),
        low_stock_items=Count('id', filter=Q(low_stock_alert=True))
    )

    # Top selling products
    stock_movements = StockMovement.objects.filter(
        shop_id=shop_id,
        movement_type='sale',
        movement_date__gte=start_date,
        movement_date__lte=end_date
    ).values('product__product_name').annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:10]

    return {
        'sales': {
            'total_sales': sales_summary['total_sales'] or 0,
            'total_revenue': float(sales_summary['total_revenue'] or 0),
            'average_sale': float(sales_summary['average_sale'] or 0)
        },
        'inventory': {
            'total_products': inventory_summary['total_products'] or 0,
            'total_stock_value': float(inventory_summary['total_stock_value'] or 0),
            'low_stock_items': inventory_summary['low_stock_items'] or 0
        },
        'top_products': [
            {
                'product_name': item['product__product_name'],
                'quantity_sold': item['total_quantity']
            }
            for item in stock_movements
        ]
    }


def get_shop_summary(user, shop_id=None):
    """
    Get shop summary statistics for current user's shops
    Includes month-to-date sales, comparison with last month, and forecasts
    """
    now = timezone.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Calculate same period last month
    if now.month == 1:
        last_month = 12
        last_year = now.year - 1
    else:
        last_month = now.month - 1
        last_year = now.year

    last_month_start = now.replace(year=last_year, month=last_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_same_day = now.replace(year=last_year, month=last_month, day=min(now.day, calendar.monthrange(last_year, last_month)[1]))

    # Get last day of current month
    _, last_day_of_month = calendar.monthrange(now.year, now.month)
    current_month_end = now.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)

    # Get last month end
    _, last_month_last_day = calendar.monthrange(last_year, last_month)
    last_month_end = last_month_start.replace(day=last_month_last_day, hour=23, minute=59, second=59, microsecond=999999)

    # Build shop query
    base_shops = Shop.objects.filter(admin=user if user.role == "admin" and not user.admin else user.admin)
    if user.admin and user.role not in ["admin"]:
        base_shops = base_shops.filter(owner=user)

    if shop_id:
        base_shops = base_shops.filter(id=shop_id)

    shop_ids = list(base_shops.values_list('id', flat=True))

    # Month-to-date sales (current month from day 1 to today)
    mtd_sales = ProductSale.objects.filter(
        shop_id__in=shop_ids,
        status='completed',
        sale_date__gte=current_month_start,
        sale_date__lte=now
    ).aggregate(
        total_revenue=Sum('total_amount'),
        total_count=Count('id')
    )

    # Last month's sales for same time period (day 1 to same day as today)
    last_month_same_period_sales = ProductSale.objects.filter(
        shop_id__in=shop_ids,
        status='completed',
        sale_date__gte=last_month_start,
        sale_date__lte=last_month_same_day
    ).aggregate(
        total_revenue=Sum('total_amount'),
        total_count=Count('id')
    )

    # Last month's total sales (entire month)
    last_month_total_sales = ProductSale.objects.filter(
        shop_id__in=shop_ids,
        status='completed',
        sale_date__gte=last_month_start,
        sale_date__lte=last_month_end
    ).aggregate(
        total_revenue=Sum('total_amount'),
        total_count=Count('id')
    )

    # Calculate metrics
    mtd_revenue = float(mtd_sales['total_revenue'] or 0)
    last_month_same_period_revenue = float(last_month_same_period_sales['total_revenue'] or 0)
    last_month_total_revenue = float(last_month_total_sales['total_revenue'] or 0)

    # Calculate percentage change compared to last month same period
    if last_month_same_period_revenue > 0:
        mtd_change_percentage = ((mtd_revenue - last_month_same_period_revenue) / last_month_same_period_revenue) * 100
    else:
        mtd_change_percentage = 100.0 if mtd_revenue > 0 else 0.0

    # Forecast for current month
    days_elapsed = (now - current_month_start).days + 1
    days_in_month = last_day_of_month

    if days_elapsed > 0:
        daily_average = mtd_revenue / days_elapsed
        forecasted_revenue = daily_average * days_in_month
    else:
        forecasted_revenue = 0.0

    # Calculate forecast vs last month percentage
    if last_month_total_revenue > 0:
        forecast_change_percentage = ((forecasted_revenue - last_month_total_revenue) / last_month_total_revenue) * 100
    else:
        forecast_change_percentage = 100.0 if forecasted_revenue > 0 else 0.0

    # Get total inventory value (all products across all user's shops)
    total_inventory_value = ShopProductInventory.objects.filter(
        shop_id__in=shop_ids
    ).aggregate(
        total_value=Sum(F('quantity') * F('product__selling_price'))
    )

    inventory_value = float(total_inventory_value['total_value'] or 0)

    return {
        'month_to_date': {
            'revenue': mtd_revenue,
            'sales_count': mtd_sales['total_count'] or 0,
            'change_percentage': round(mtd_change_percentage, 2),
            'trend': 'up' if mtd_change_percentage >= 0 else 'down'
        },
        'last_month_same_period': {
            'revenue': last_month_same_period_revenue,
            'sales_count': last_month_same_period_sales['total_count'] or 0,
            'period_start': last_month_start.strftime('%b %d'),
            'period_end': last_month_same_day.strftime('%b %d')
        },
        'forecast': {
            'total_revenue': round(forecasted_revenue, 2),
            'change_percentage': round(forecast_change_percentage, 2),
            'trend': 'up' if forecast_change_percentage >= 0 else 'down'
        },
        'last_month_total': {
            'revenue': last_month_total_revenue,
            'sales_count': last_month_total_sales['total_count'] or 0
        },
        'inventory': {
            'total_value': inventory_value,
            'product_count': ShopProductInventory.objects.filter(shop_id__in=shop_ids).count()
        },
        'period_info': {
            'current_month': now.strftime('%B %Y'),
            'days_elapsed': days_elapsed,
            'days_in_month': days_in_month
        }
    }


# Export all functions for RPC registration
functions = {
    # Shop management
    'get_all_shops': get_all_shops,
    'create_shop': create_shop,
    'get_shop_summary': get_shop_summary,

    # Product management
    'get_all_products': get_all_products,
    'create_product': create_product,
    'update_product': update_product,

    # Categories
    'get_all_categories': get_all_categories,
    'create_category': create_category,

    # Inventory
    'get_shop_inventory': get_shop_inventory,
    'get_low_stock_alerts': get_low_stock_alerts,
    'record_stock_movement': record_stock_movement,

    # Sales
    'record_sale': record_sale,
    'get_sales_history': get_sales_history,

    # Suppliers
    'get_all_suppliers': get_all_suppliers,
    'create_supplier': create_supplier,

    # Analytics
    'get_shop_analytics': get_shop_analytics,
}
