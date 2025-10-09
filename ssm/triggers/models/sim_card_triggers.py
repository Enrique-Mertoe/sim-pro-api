"""
SIM Card model triggers
"""
from ..base.trigger_decorator import (
    post_save_trigger, field_changed_trigger, conditional_trigger
)
from ..base.trigger_base import TriggerContext, TriggerResult, TriggerEvent
from ..conditions.common_conditions import (
    field_equals, field_changed, status_changed_to, user_has_role
)
from ..actions.common_actions import (
    log_info, update_field, send_notification, create_audit_log
)
from ...models.base_models import TeamMetadata


@post_save_trigger(
    'SimCard',
    name='sim_card_quality_update',
    description='Update quality statistics when SIM card quality changes'
)
def handle_sim_card_quality_change(context: TriggerContext) -> TriggerResult:
    """Update team and batch quality statistics when SIM card quality changes"""
    try:
        sim_card = context.instance
        # Update team statistics if SIM is assigned to a team
        if sim_card.team:
            from ssm.models import Team
            team = sim_card.team

            # Recalculate quality metrics for the team
            team_sim_cards = team.simcard_set.all()
            total_sims = team_sim_cards.count()
            quality_sims = team_sim_cards.filter(quality='quality').count()

            if total_sims > 0:
                quality_rate = (quality_sims / total_sims) * 100

                metadata, _ = TeamMetadata.objects.get_or_create(team=team)

                perf = metadata.performance or {}
                perf.update({
                    "quality_rate": round(quality_rate, 2),
                    "total_sims": total_sims,
                    "quality_sims": quality_sims,
                })

                metadata.performance = perf
                metadata.save()

        # Update batch statistics
        if sim_card.batch:
            from ssm.models import BatchMetadata
            batch = sim_card.batch

            # Recalculate batch quality metrics
            batch_sim_cards = batch.sim_cards.all()
            total_batch_sims = batch_sim_cards.count()
            quality_batch_sims = batch_sim_cards.filter(quality='quality').count()

            # Update lot metadata if applicable
            if hasattr(batch, 'lots'):
                for lot in batch.lots.all():
                    lot_sim_cards = lot.serial_numbers
                    lot_quality_count = batch_sim_cards.filter(
                        serial_number__in=lot_sim_cards,
                        quality='Y'
                    ).count()
                    lot_nonquality_count = len(lot_sim_cards) - lot_quality_count

                    lot.quality_count = lot_quality_count
                    lot.nonquality_count = lot_nonquality_count
                    lot.save(update_fields=['quality_count', 'nonquality_count'])

        return TriggerResult(
            success=True,
            message="Quality statistics updated successfully"
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to update quality statistics: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'SimCard',
    'status',
    name='sim_card_status_notification',
    description='Send notifications when SIM card status changes'
)
def handle_sim_card_status_change(context: TriggerContext) -> TriggerResult:
    """Send notifications when SIM card status changes"""
    try:
        sim_card = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        new_status = sim_card.status

        # Create notification message
        message = f"SIM Card {sim_card.serial_number} status changed from {old_status} to {new_status}"

        # Determine notification recipients
        recipients = []

        # Add assigned user
        if sim_card.assigned_to_user:
            recipients.append(sim_card.assigned_to_user)

        # Add team leader
        if sim_card.team and sim_card.team.leader:
            recipients.append(sim_card.team.leader)

        # Add admin
        if sim_card.admin:
            recipients.append(sim_card.admin)

        # Send notifications
        if recipients:
            from ssm.models import Notification
            for user in recipients:
                Notification.objects.create(
                    user=user,
                    title="SIM Card Status Update",
                    message=message,
                    type="sim_status_change",
                    metadata={
                        'sim_card_id': str(sim_card.id),
                        'serial_number': sim_card.serial_number,
                        'old_status': old_status,
                        'new_status': new_status
                    }
                )

        return TriggerResult(
            success=True,
            message=f"Status change notifications sent to {len(recipients)} users",
            data={'recipients_count': len(recipients)}
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to send status change notifications: {str(e)}",
            error=e
        )


@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'SimCard',
    condition_func=lambda ctx: ctx.instance.fraud_flag and not getattr(ctx.old_instance, 'fraud_flag', False),
    name='sim_card_fraud_alert',
    description='Alert when SIM card is flagged for fraud'
)
def handle_fraud_flag_alert(context: TriggerContext) -> TriggerResult:
    """Send alerts when SIM card is flagged for fraud"""
    try:
        sim_card = context.instance

        # Create high-priority notification
        alert_message = f"FRAUD ALERT: SIM Card {sim_card.serial_number} has been flagged for fraud. Reason: {sim_card.fraud_reason}"

        # Get admin users and team leaders for alerts
        from ssm.models import User, Notification

        admin_users = User.objects.filter(role='admin')
        team_leaders = User.objects.filter(role='team_leader')

        alert_recipients = list(admin_users) + list(team_leaders)

        # Add specific team leader if SIM is assigned
        if sim_card.team and sim_card.team.leader:
            if sim_card.team.leader not in alert_recipients:
                alert_recipients.append(sim_card.team.leader)

        # Send high-priority notifications
        for user in alert_recipients:
            Notification.objects.create(
                user=user,
                title="🚨 FRAUD ALERT",
                message=alert_message,
                type="fraud_alert",
                metadata={
                    'sim_card_id': str(sim_card.id),
                    'serial_number': sim_card.serial_number,
                    'fraud_reason': sim_card.fraud_reason,
                    'team_id': str(sim_card.team.id) if sim_card.team else None,
                    'assigned_user_id': str(sim_card.assigned_to_user.id) if sim_card.assigned_to_user else None
                }
            )

        # Log the fraud alert
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='fraud_alert',
            details={
                'sim_card_id': str(sim_card.id),
                'serial_number': sim_card.serial_number,
                'fraud_reason': sim_card.fraud_reason,
                'alert_sent_to': len(alert_recipients)
            }
        )

        return TriggerResult(
            success=True,
            message=f"Fraud alert sent to {len(alert_recipients)} users",
            data={'alert_recipients_count': len(alert_recipients)}
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to send fraud alert: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'SimCard',
    'assigned_to_user',
    name='sim_card_assignment_tracking',
    description='Track SIM card assignments and update inventory'
)
def handle_sim_card_assignment(context: TriggerContext) -> TriggerResult:
    """Track SIM card assignments and update related inventory"""
    try:
        sim_card = context.instance
        old_user = getattr(context.old_instance, 'assigned_to_user', None) if context.old_instance else None
        new_user = sim_card.assigned_to_user

        # Update assignment timestamp
        if new_user and old_user != new_user:
            from django.utils import timezone
            sim_card.assigned_on = timezone.now()
            sim_card.save(update_fields=['assigned_on'])

        # Update lot metadata counts
        if sim_card.lot:
            from ssm.utils.lot_utils import update_lot_assignment_counts
            update_lot_assignment_counts(sim_card.lot)

        # Update shop inventory if SIM is allocated to shops
        from ssm.models import ShopInventory
        shop_inventories = ShopInventory.objects.filter(sim_card=sim_card)

        for inventory in shop_inventories:
            if new_user:
                inventory.status = 'reserved'
                inventory.notes = f"Assigned to {new_user.full_name}"
            else:
                inventory.status = 'available'
                inventory.notes = "Assignment removed"
            inventory.save(update_fields=['status', 'notes'])

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='sim_assignment_changed',
            details={
                'sim_card_id': str(sim_card.id),
                'serial_number': sim_card.serial_number,
                'old_user': str(old_user) if old_user else None,
                'new_user': str(new_user) if new_user else None,
                'shop_inventories_updated': shop_inventories.count()
            }
        )

        return TriggerResult(
            success=True,
            message="SIM card assignment tracked successfully",
            data={
                'assignment_updated': True,
                'shop_inventories_updated': shop_inventories.count()
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to track SIM card assignment: {str(e)}",
            error=e
        )


@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'SimCard',
    condition_func=lambda ctx: ctx.instance.registered_on and not getattr(ctx.old_instance, 'registered_on', None),
    name='sim_card_registration_completion',
    description='Handle SIM card registration completion'
)
def handle_sim_card_registration(context: TriggerContext) -> TriggerResult:
    """Handle actions when SIM card registration is completed"""
    try:
        sim_card = context.instance

        # Update status to active if registration is completed
        if sim_card.status == 'PENDING':
            sim_card.status = 'ACTIVE'
            sim_card.save(update_fields=['status'])

        # Update shop sales record if exists
        from ssm.models import ShopSales
        try:
            shop_sale = ShopSales.objects.get(sim_card=sim_card)
            if shop_sale.status == 'pending':
                shop_sale.status = 'completed'
                shop_sale.save(update_fields=['status'])
        except ShopSales.DoesNotExist:
            pass

        # Send completion notification to assigned user and team
        recipients = []
        if sim_card.assigned_to_user:
            recipients.append(sim_card.assigned_to_user)
        if sim_card.team and sim_card.team.leader:
            recipients.append(sim_card.team.leader)

        if recipients:
            from ssm.models import Notification
            for user in recipients:
                Notification.objects.create(
                    user=user,
                    title="SIM Card Registration Complete",
                    message=f"SIM Card {sim_card.serial_number} has been successfully registered and activated.",
                    type="registration_complete",
                    metadata={
                        'sim_card_id': str(sim_card.id),
                        'serial_number': sim_card.serial_number,
                        'registered_on': sim_card.registered_on.isoformat()
                    }
                )

        return TriggerResult(
            success=True,
            message="SIM card registration completion handled successfully",
            data={'notifications_sent': len(recipients)}
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle SIM card registration: {str(e)}",
            error=e
        )
