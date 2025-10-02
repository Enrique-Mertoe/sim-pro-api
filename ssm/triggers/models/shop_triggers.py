"""
Shop management model triggers
"""
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Avg

from ..base.trigger_decorator import (
    post_save_trigger, field_changed_trigger, conditional_trigger, pre_save_trigger
)
from ..base.trigger_base import TriggerContext, TriggerResult, TriggerEvent
from ..conditions.common_conditions import (
    field_equals, field_changed, status_changed_to, quantity_above, quantity_below
)


@field_changed_trigger(
    'Shop',
    'status',
    name='shop_status_change_handler',
    description='Handle shop status changes and notify stakeholders'
)
def handle_shop_status_change(context: TriggerContext) -> TriggerResult:
    """Handle shop status changes and create appropriate notifications"""
    try:
        shop = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        new_status = shop.status

        # Create audit log entry
        from ssm.models import ShopAuditLog
        ShopAuditLog.objects.create(
            shop=shop,
            user=context.user,
            action_type='status_changed',
            description=f"Shop status changed from {old_status} to {new_status}",
            before_state={'status': old_status},
            after_state={'status': new_status},
            metadata={
                'trigger_event': context.event.value,
                'timestamp': context.timestamp.isoformat()
            }
        )

        # Send notifications based on status change
        notification_message = f"Shop {shop.shop_code} - {shop.shop_name} status changed to {new_status}"

        # Determine recipients
        recipients = []
        if shop.shop_manager:
            recipients.append(shop.shop_manager)
        if shop.admin:
            recipients.append(shop.admin)

        # Add team members if shop is linked to a team
        if shop.team:
            team_members = shop.team.user_set.filter(role__in=['team_leader', 'admin'])
            recipients.extend(team_members)

        # Create notifications
        from ssm.models import Notification
        for user in set(recipients):  # Remove duplicates
            Notification.objects.create(
                user=user,
                title="Shop Status Update",
                message=notification_message,
                type="shop_status_change",
                metadata={
                    'shop_id': str(shop.id),
                    'shop_code': shop.shop_code,
                    'old_status': old_status,
                    'new_status': new_status
                }
            )

        # Handle specific status transitions
        if new_status == 'active' and old_status in ['pending_approval', 'inactive']:
            # Shop activated - initialize inventory tracking
            _initialize_shop_operations(shop)

        elif new_status == 'suspended':
            # Shop suspended - notify about inventory freeze
            _handle_shop_suspension(shop)

        elif new_status == 'closed':
            # Shop closed - handle final inventory and transfers
            _handle_shop_closure(shop)

        return TriggerResult(
            success=True,
            message=f"Shop status change handled successfully. Notifications sent to {len(set(recipients))} users",
            data={
                'old_status': old_status,
                'new_status': new_status,
                'notifications_sent': len(set(recipients))
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle shop status change: {str(e)}",
            error=e
        )


@post_save_trigger(
    'ShopSales',
    name='shop_sales_performance_update',
    description='Update shop performance metrics when a sale is completed'
)
def handle_shop_sales_update(context: TriggerContext) -> TriggerResult:
    """Update shop performance metrics when sales are recorded"""
    try:
        sale = context.instance
        shop = sale.shop

        # Only process completed sales
        if sale.status != 'completed':
            return TriggerResult(success=True, message="Sale not completed, skipping metrics update")

        # Calculate current month performance
        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (current_month.replace(month=current_month.month + 1)
                     if current_month.month < 12
                     else current_month.replace(year=current_month.year + 1, month=1))

        # Get or create performance record for current month
        from ssm.models import ShopPerformance
        performance, created = ShopPerformance.objects.get_or_create(
            shop=shop,
            period_start=current_month.date(),
            period_end=(next_month - timezone.timedelta(days=1)).date(),
            period_type='monthly',
            defaults={
                'calculated_by': context.user,
                'total_sales': 0,
                'total_revenue': Decimal('0.00'),
                'total_commission': Decimal('0.00')
            }
        )

        # Recalculate monthly metrics
        monthly_sales = shop.sales.filter(
            sale_date__gte=current_month,
            sale_date__lt=next_month,
            status='completed'
        )

        total_sales = monthly_sales.count()
        total_revenue = monthly_sales.aggregate(Sum('net_amount'))['net_amount__sum'] or Decimal('0.00')
        total_commission = monthly_sales.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
        average_sale_value = monthly_sales.aggregate(Avg('net_amount'))['net_amount__avg'] or Decimal('0.00')

        # Quality metrics
        quality_sales = monthly_sales.filter(sim_card__quality='quality').count()
        non_quality_sales = monthly_sales.filter(sim_card__quality='non_quality').count()
        quality_rate = (quality_sales / total_sales * 100) if total_sales > 0 else 0

        # Update performance record
        performance.total_sales = total_sales
        performance.total_revenue = total_revenue
        performance.total_commission = total_commission
        performance.average_sale_value = average_sale_value
        performance.quality_sales = quality_sales
        performance.non_quality_sales = non_quality_sales
        performance.quality_rate = Decimal(str(round(quality_rate, 2)))

        # Calculate achievement percentage if targets exist
        from ssm.models import ShopTarget
        revenue_target = ShopTarget.objects.filter(
            shop=shop,
            target_type='revenue',
            period_start__lte=current_month.date(),
            period_end__gte=current_month.date(),
            is_active=True
        ).first()

        if revenue_target:
            achievement = (total_revenue / revenue_target.target_value * 100) if revenue_target.target_value > 0 else 0
            performance.achievement_percentage = Decimal(str(round(achievement, 2)))

        performance.save()

        return TriggerResult(
            success=True,
            message="Shop performance metrics updated successfully",
            data={
                'shop_code': shop.shop_code,
                'total_sales': total_sales,
                'total_revenue': float(total_revenue),
                'quality_rate': float(quality_rate)
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to update shop performance metrics: {str(e)}",
            error=e
        )


@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'ShopInventory',
    condition_func=lambda ctx: ctx.instance.status == 'sold' and getattr(ctx.old_instance, 'status', '') != 'sold',
    name='shop_inventory_sale_tracking',
    description='Track inventory sales and update shop balance'
)
def handle_inventory_sale(context: TriggerContext) -> TriggerResult:
    """Handle inventory sale completion and update shop financials"""
    try:
        inventory = context.instance
        shop = inventory.shop

        # Update shop balance if commission is earned
        if inventory.commission_earned:
            shop.current_balance += inventory.commission_earned
            shop.save(update_fields=['current_balance'])

        # Create shop audit log
        from ssm.models import ShopAuditLog
        ShopAuditLog.objects.create(
            shop=shop,
            user=context.user or inventory.sold_by,
            action_type='sale_completed',
            description=f"SIM card {inventory.sim_card.serial_number} sold",
            after_state={
                'inventory_id': str(inventory.id),
                'sim_serial': inventory.sim_card.serial_number,
                'selling_price': float(inventory.selling_price) if inventory.selling_price else 0,
                'commission': float(inventory.commission_earned) if inventory.commission_earned else 0
            },
            metadata={
                'customer_name': inventory.customer_name,
                'customer_phone': inventory.customer_phone,
                'sale_date': inventory.sold_date.isoformat() if inventory.sold_date else None
            }
        )

        # Check inventory levels and create alerts if low
        available_inventory = shop.inventory.filter(status='available').count()
        if available_inventory <= 10:  # Low inventory threshold
            _create_low_inventory_alert(shop, available_inventory)

        return TriggerResult(
            success=True,
            message="Inventory sale tracked successfully",
            data={
                'shop_balance_updated': bool(inventory.commission_earned),
                'available_inventory': available_inventory
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to track inventory sale: {str(e)}",
            error=e
        )


@post_save_trigger(
    'ShopTransfer',
    name='shop_transfer_workflow',
    description='Handle shop transfer workflow and notifications'
)
def handle_shop_transfer_workflow(context: TriggerContext) -> TriggerResult:
    """Handle shop transfer workflow stages"""
    try:
        transfer = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        current_status = transfer.status

        # Skip if status hasn't changed
        if old_status == current_status:
            return TriggerResult(success=True, message="No status change detected")

        # Handle different workflow stages
        if current_status == 'approved' and old_status == 'pending':
            _handle_transfer_approval(transfer, context.user)

        elif current_status == 'in_transit' and old_status == 'approved':
            _handle_transfer_dispatch(transfer, context.user)

        elif current_status == 'completed' and old_status == 'in_transit':
            _handle_transfer_completion(transfer, context.user)

        elif current_status == 'rejected':
            _handle_transfer_rejection(transfer, context.user)

        elif current_status == 'cancelled':
            _handle_transfer_cancellation(transfer, context.user)

        # Create audit log for status change
        from ssm.models import ShopAuditLog
        for shop in [transfer.source_shop, transfer.destination_shop]:
            ShopAuditLog.objects.create(
                shop=shop,
                user=context.user,
                action_type='transfer_status_changed',
                description=f"Transfer {transfer.transfer_reference} status changed to {current_status}",
                before_state={'transfer_status': old_status},
                after_state={'transfer_status': current_status},
                related_object_type='ShopTransfer',
                related_object_id=transfer.id,
                metadata={
                    'transfer_reference': transfer.transfer_reference,
                    'other_shop': shop.shop_code if shop == transfer.source_shop else transfer.destination_shop.shop_code
                }
            )

        return TriggerResult(
            success=True,
            message=f"Transfer workflow handled for status: {current_status}",
            data={
                'transfer_reference': transfer.transfer_reference,
                'old_status': old_status,
                'new_status': current_status
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle transfer workflow: {str(e)}",
            error=e
        )


# Helper functions for trigger actions

def _initialize_shop_operations(shop):
    """Initialize shop operations when activated"""
    try:
        # Create initial performance record
        from ssm.models import ShopPerformance
        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        ShopPerformance.objects.get_or_create(
            shop=shop,
            period_start=current_month.date(),
            period_type='monthly',
            defaults={
                'calculated_by': shop.admin,
                'total_sales': 0,
                'total_revenue': Decimal('0.00')
            }
        )

        # Send welcome notification to shop manager
        if shop.shop_manager:
            from ssm.models import Notification
            Notification.objects.create(
                user=shop.shop_manager,
                title="Shop Activated",
                message=f"Congratulations! Your shop {shop.shop_name} has been activated and is ready for operations.",
                type="shop_activation",
                metadata={'shop_id': str(shop.id), 'shop_code': shop.shop_code}
            )

    except Exception as e:
        logger.error(f"Failed to initialize shop operations for {shop.shop_code}: {e}")


def _handle_shop_suspension(shop):
    """Handle shop suspension"""
    try:
        # Freeze all pending transfers
        from ssm.models import ShopTransfer
        pending_transfers = ShopTransfer.objects.filter(
            models.Q(source_shop=shop) | models.Q(destination_shop=shop),
            status__in=['pending', 'approved']
        )

        for transfer in pending_transfers:
            transfer.status = 'cancelled'
            transfer.notes = f"Cancelled due to shop suspension: {shop.shop_code}"
            transfer.save()

        # Notify stakeholders
        from ssm.models import Notification
        if shop.shop_manager:
            Notification.objects.create(
                user=shop.shop_manager,
                title="Shop Suspended",
                message=f"Your shop {shop.shop_name} has been suspended. All pending operations have been frozen.",
                type="shop_suspension",
                metadata={'shop_id': str(shop.id), 'shop_code': shop.shop_code}
            )

    except Exception as e:
        logger.error(f"Failed to handle shop suspension for {shop.shop_code}: {e}")


def _handle_shop_closure(shop):
    """Handle shop closure"""
    try:
        # Return all available inventory to central warehouse
        available_inventory = shop.inventory.filter(status='available')

        if available_inventory.exists():
            # Create return transfer record
            from ssm.models import ShopTransfer
            transfer = ShopTransfer.objects.create(
                transfer_reference=f"CLOSURE_{shop.shop_code}_{timezone.now().strftime('%Y%m%d')}",
                source_shop=shop,
                destination_shop=None,  # Central warehouse
                requested_by=shop.admin,
                reason="Shop closure - returning inventory",
                status='approved',
                sim_cards=[inv.sim_card.serial_number for inv in available_inventory],
                total_quantity=available_inventory.count(),
                admin=shop.admin
            )

        # Final performance calculation
        _calculate_final_shop_performance(shop)

    except Exception as e:
        logger.error(f"Failed to handle shop closure for {shop.shop_code}: {e}")


def _create_low_inventory_alert(shop, available_count):
    """Create low inventory alert"""
    try:
        from ssm.models import Notification

        # Alert shop manager
        if shop.shop_manager:
            Notification.objects.create(
                user=shop.shop_manager,
                title="Low Inventory Alert",
                message=f"Your shop {shop.shop_name} has only {available_count} SIM cards remaining in inventory.",
                type="low_inventory",
                metadata={
                    'shop_id': str(shop.id),
                    'shop_code': shop.shop_code,
                    'available_count': available_count
                }
            )

        # Alert admin if critically low (<=5)
        if available_count <= 5 and shop.admin:
            Notification.objects.create(
                user=shop.admin,
                title="Critical Inventory Alert",
                message=f"Shop {shop.shop_code} has critically low inventory: {available_count} SIM cards remaining.",
                type="critical_inventory",
                metadata={
                    'shop_id': str(shop.id),
                    'shop_code': shop.shop_code,
                    'available_count': available_count
                }
            )

    except Exception as e:
        logger.error(f"Failed to create low inventory alert for {shop.shop_code}: {e}")


def _handle_transfer_approval(transfer, approver):
    """Handle transfer approval"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Transfer Approved",
            message=f"Your transfer request {transfer.transfer_reference} has been approved and is ready for dispatch.",
            type="transfer_approved",
            metadata={
                'transfer_id': str(transfer.id),
                'transfer_reference': transfer.transfer_reference,
                'approved_by': str(approver) if approver else 'System'
            }
        )

        # Set dispatch date for next day
        transfer.expected_delivery_date = timezone.now().date() + timezone.timedelta(days=1)
        transfer.save(update_fields=['expected_delivery_date'])

    except Exception as e:
        logger.error(f"Failed to handle transfer approval: {e}")


def _handle_transfer_dispatch(transfer, dispatcher):
    """Handle transfer dispatch"""
    try:
        transfer.dispatch_date = timezone.now()
        transfer.dispatched_by = dispatcher
        transfer.save(update_fields=['dispatch_date', 'dispatched_by'])

        # Notify destination shop
        from ssm.models import Notification
        if transfer.destination_shop.shop_manager:
            Notification.objects.create(
                user=transfer.destination_shop.shop_manager,
                title="Transfer Dispatched",
                message=f"Transfer {transfer.transfer_reference} has been dispatched and is on its way to your shop.",
                type="transfer_dispatched",
                metadata={
                    'transfer_id': str(transfer.id),
                    'transfer_reference': transfer.transfer_reference,
                    'expected_delivery': transfer.expected_delivery_date.isoformat() if transfer.expected_delivery_date else None
                }
            )

    except Exception as e:
        logger.error(f"Failed to handle transfer dispatch: {e}")


def _handle_transfer_completion(transfer, receiver):
    """Handle transfer completion"""
    try:
        # Update inventory at destination shop
        from ssm.models import ShopInventory, SimCard

        sim_cards = SimCard.objects.filter(serial_number__in=transfer.sim_cards)
        created_count = 0

        for sim_card in sim_cards:
            inventory, created = ShopInventory.objects.get_or_create(
                shop=transfer.destination_shop,
                sim_card=sim_card,
                defaults={
                    'status': 'available',
                    'allocated_by': receiver or transfer.destination_shop.admin,
                    'notes': f"Received via transfer {transfer.transfer_reference}"
                }
            )
            if created:
                created_count += 1

        transfer.received_quantity = created_count
        transfer.received_date = timezone.now()
        transfer.received_by = receiver
        transfer.save(update_fields=['received_quantity', 'received_date', 'received_by'])

        # Notify completion
        from ssm.models import Notification
        Notification.objects.create(
            user=transfer.requested_by,
            title="Transfer Completed",
            message=f"Transfer {transfer.transfer_reference} has been completed. {created_count} items received.",
            type="transfer_completed",
            metadata={
                'transfer_id': str(transfer.id),
                'transfer_reference': transfer.transfer_reference,
                'items_received': created_count
            }
        )

    except Exception as e:
        logger.error(f"Failed to handle transfer completion: {e}")


def _handle_transfer_rejection(transfer, rejector):
    """Handle transfer rejection"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Transfer Rejected",
            message=f"Your transfer request {transfer.transfer_reference} has been rejected. Reason: {transfer.rejection_reason}",
            type="transfer_rejected",
            metadata={
                'transfer_id': str(transfer.id),
                'transfer_reference': transfer.transfer_reference,
                'rejection_reason': transfer.rejection_reason,
                'rejected_by': str(rejector) if rejector else 'System'
            }
        )

    except Exception as e:
        logger.error(f"Failed to handle transfer rejection: {e}")


def _handle_transfer_cancellation(transfer, canceller):
    """Handle transfer cancellation"""
    try:
        from ssm.models import Notification

        # Notify relevant parties
        users_to_notify = [transfer.requested_by]
        if transfer.approved_by:
            users_to_notify.append(transfer.approved_by)

        for user in set(users_to_notify):
            Notification.objects.create(
                user=user,
                title="Transfer Cancelled",
                message=f"Transfer {transfer.transfer_reference} has been cancelled.",
                type="transfer_cancelled",
                metadata={
                    'transfer_id': str(transfer.id),
                    'transfer_reference': transfer.transfer_reference,
                    'cancelled_by': str(canceller) if canceller else 'System'
                }
            )

    except Exception as e:
        logger.error(f"Failed to handle transfer cancellation: {e}")


def _calculate_final_shop_performance(shop):
    """Calculate final performance metrics for closing shop"""
    try:
        from ssm.models import ShopPerformance
        from django.db.models import Sum, Count, Avg

        # Get all sales for final calculation
        all_sales = shop.sales.filter(status='completed')

        if all_sales.exists():
            final_performance = ShopPerformance.objects.create(
                shop=shop,
                period_start=shop.created_at.date(),
                period_end=timezone.now().date(),
                period_type='final',
                total_sales=all_sales.count(),
                total_revenue=all_sales.aggregate(Sum('net_amount'))['net_amount__sum'] or Decimal('0.00'),
                total_commission=all_sales.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00'),
                average_sale_value=all_sales.aggregate(Avg('net_amount'))['net_amount__avg'] or Decimal('0.00'),
                calculated_by=shop.admin
            )

    except Exception as e:
        logger.error(f"Failed to calculate final performance for {shop.shop_code}: {e}")


import logging
logger = logging.getLogger(__name__)
from django.db import models