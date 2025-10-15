from django.db.models import Q
from ..models.base_models import User, Team, SimCard, BatchMetadata, LotMetadata
from ..models.shop_management_models import Shop, Product, ProductCategory, Supplier
from ..models.product_instance_model import ProductInstance


def get_searched(user, query):
    """
    Sophisticated search function that searches across multiple models
    and returns the results in a structured format.

    Args:
        user: The user making the search request
        query: The search query string

    Returns:
        A dictionary containing search results categorized by entity type
    """
    if not query or len(query.strip()) < 2:
        return {
            "success": False,
            "message": "Search query must be at least 2 characters long",
            "results": {}
        }

    # Normalize query
    query = query.strip().lower()
    admin = user if user.role == "admin" else user.admin

    # Initialize results dictionary
    results = {
        "users": [],
        "teams": [],
        "shops": [],
        "products": [],
        "product_instances": [],
        "sim_cards": [],
        "batches": [],
        "lots": [],
        "suppliers": [],
        "categories": []
    }

    # Search Users
    user_results = User.objects.filter(
        Q(full_name__icontains=query) |
        Q(email__icontains=query) |
        Q(phone_number__icontains=query) |
        Q(username__icontains=query) |
        Q(id_number__icontains=query) |
        Q(role__icontains=query)
    ).filter(admin=admin)[:10]

    for user_obj in user_results:
        matched_fields = []
        if query in (user_obj.full_name or '').lower(): matched_fields.append('name')
        if query in (user_obj.email or '').lower(): matched_fields.append('email')
        if query in (user_obj.phone_number or '').lower(): matched_fields.append('phone')
        if query in (user_obj.role or '').lower(): matched_fields.append('role')
        
        results["users"].append({
            "id": str(user_obj.id),
            "name": user_obj.full_name,
            "email": user_obj.email,
            "phone": user_obj.phone_number,
            "role": user_obj.role,
            "type": "User",
            "matched_fields": matched_fields
        })

    # Search Teams
    team_results = Team.objects.filter(
        Q(name__icontains=query) |
        Q(region__icontains=query) |
        Q(territory__icontains=query)
    ).filter(admin=admin)[:10]

    for team in team_results:
        matched_fields = []
        if query in (team.name or '').lower(): matched_fields.append('name')
        if query in (team.region or '').lower(): matched_fields.append('region')
        if query in (team.territory or '').lower(): matched_fields.append('territory')
        
        results["teams"].append({
            "id": str(team.id),
            "name": team.name,
            "region": team.region,
            "territory": team.territory,
            "type": "Team",
            "matched_fields": matched_fields
        })

    # Search Shops
    shop_results = Shop.objects.filter(
        Q(shop_name__icontains=query) |
        Q(shop_code__icontains=query) |
        Q(address__icontains=query) |
        Q(city__icontains=query) |
        Q(region__icontains=query) |
        Q(phone_number__icontains=query) |
        Q(email__icontains=query)
    ).filter(admin=admin)[:10]

    for shop in shop_results:
        results["shops"].append({
            "id": str(shop.id),
            "name": shop.shop_name,
            "code": shop.shop_code,
            "address": shop.address,
            "city": shop.city,
            "region": shop.region,
            "type": "Shop"
        })

    # Search Products
    product_results = Product.objects.filter(
        Q(product_name__icontains=query) |
        Q(product_code__icontains=query) |
        Q(model__icontains=query) |
        Q(brand__icontains=query) |
        Q(description__icontains=query)
    ).filter(admin=admin)[:10]

    for product in product_results:
        results["products"].append({
            "id": str(product.id),
            "name": product.product_name,
            "code": product.product_code,
            "model": product.model,
            "brand": product.brand,
            "price": float(product.selling_price),
            "type": "Product"
        })

    # Search Product Instances
    product_instance_results = ProductInstance.objects.filter(
        Q(serial_number__icontains=query) |
        Q(barcode__icontains=query) |
        Q(customer_name__icontains=query) |
        Q(customer_phone__icontains=query) |
        Q(product__product_name__icontains=query)
    )[:10]

    for instance in product_instance_results:
        results["product_instances"].append({
            "id": str(instance.id),
            "serial_number": instance.serial_number,
            "barcode": instance.barcode,
            "product_name": instance.product.product_name,
            "status": instance.status,
            "customer_name": instance.customer_name,
            "type": "Product Instance"
        })

    # Search SIM Cards
    sim_results = SimCard.objects.filter(
        Q(serial_number__icontains=query) |
        Q(ba_msisdn__icontains=query) |
        Q(mobigo__icontains=query) |
        Q(status__icontains=query)
    ).filter(admin=admin)[:10]

    for sim in sim_results:
        matched_fields = []
        if query in (sim.serial_number or '').lower(): matched_fields.append('serial_number')
        if query in (sim.ba_msisdn or '').lower(): matched_fields.append('msisdn')
        if query in (sim.mobigo or '').lower(): matched_fields.append('mobigo')
        if query in (sim.status or '').lower(): matched_fields.append('status')
        
        results["sim_cards"].append({
            "id": str(sim.id),
            "serial_number": sim.serial_number,
            "msisdn": sim.ba_msisdn,
            "mobigo": sim.mobigo,
            "status": sim.status,
            "type": "SIM Card",
            "matched_fields": matched_fields
        })

    # Search Batches
    batch_results = BatchMetadata.objects.filter(
        Q(batch_id__icontains=query) |
        Q(order_number__icontains=query) |
        Q(requisition_number__icontains=query) |
        Q(company_name__icontains=query) |
        Q(collection_point__icontains=query)
    ).filter(admin=admin)[:10]

    for batch in batch_results:
        results["batches"].append({
            "id": str(batch.id),
            "batch_id": batch.batch_id,
            "order_number": batch.order_number,
            "requisition_number": batch.requisition_number,
            "company_name": batch.company_name,
            "type": "Batch"
        })

    # Search Lots
    lot_results = LotMetadata.objects.filter(
        Q(lot_number__icontains=query) |
        Q(status__icontains=query) |
        Q(batch__batch_id__icontains=query)
    ).filter(admin=admin)[:10]

    for lot in lot_results:
        results["lots"].append({
            "id": str(lot.id),
            "lot_number": lot.lot_number,
            "batch_id": lot.batch.batch_id,
            "status": lot.status,
            "total_sims": lot.total_sims,
            "type": "Lot"
        })

    # Search Suppliers
    supplier_results = Supplier.objects.filter(
        Q(supplier_name__icontains=query) |
        Q(supplier_code__icontains=query) |
        Q(contact_person__icontains=query) |
        Q(phone_number__icontains=query) |
        Q(email__icontains=query)
    ).filter(admin=admin)[:10]

    for supplier in supplier_results:
        results["suppliers"].append({
            "id": str(supplier.id),
            "name": supplier.supplier_name,
            "code": supplier.supplier_code,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone_number,
            "type": "Supplier"
        })

    # Search Product Categories
    category_results = ProductCategory.objects.filter(
        Q(name__icontains=query) |
        Q(code__icontains=query) |
        Q(description__icontains=query)
    ).filter(admin=admin)[:10]

    for category in category_results:
        results["categories"].append({
            "id": str(category.id),
            "name": category.name,
            "code": category.code,
            "description": category.description,
            "type": "Product Category"
        })

    # Count total results
    total_results = sum(len(results[key]) for key in results)

    # Prepare final response
    response = {
        "success": True,
        "message": f"Found {total_results} results for '{query}'",
        "query": query,
        "results": results
    }

    return response


functions = {
    "get_searched": get_searched
}
