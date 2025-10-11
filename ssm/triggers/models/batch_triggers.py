"""
Batch management model triggers
"""
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Avg

from ..base.trigger_decorator import (
    post_save_trigger, field_changed_trigger, conditional_trigger, pre_delete_trigger
)
from ..base.trigger_base import TriggerContext, TriggerResult, TriggerEvent


@pre_delete_trigger(
    'BatchMetadata',
    name='batch_cascade_delete',
    description='Cascade delete batch lots and SIM cards before batch deletion'
)
def handle_batch_cascade_delete(context: TriggerContext) -> TriggerResult:
    """Delete all lots and SIM cards associated with a batch before deleting the batch"""
    try:
        batch = context.instance

        # Get all lots in this batch
        from ssm.models import LotMetadata, SimCard
        lots = LotMetadata.objects.filter(batch=batch)

        deleted_counts = {
            'lots': 0,
            'sim_cards': 0
        }
        print("lots",lots)
        # For each lot, delete SIM cards with that lot number
        for lot in lots:
            # Delete SIM cards that belong to this lot
            sim_cards_deleted = SimCard.objects.filter(
                lot=lot.lot_number,
                batch=batch
            ).delete()
            print("found",sim_cards_deleted)
            deleted_counts['sim_cards'] += sim_cards_deleted[0] if sim_cards_deleted else 0

        # Delete all lots in the batch
        lots_deleted = lots.delete()
        deleted_counts['lots'] = lots_deleted[0] if lots_deleted else 0

        # Create activity log
        from ssm.models import ActivityLog
        if context.user:
            ActivityLog.objects.create(
                user=context.user,
                action_type='batch_cascade_deleted',
                details={
                    'batch_id': str(batch.id),
                    'batch_number': batch.batch_id,
                    'lots_deleted': deleted_counts['lots'],
                    'sim_cards_deleted': deleted_counts['sim_cards']
                }
            )

        return TriggerResult(
            success=True,
            message=f"Cascade delete completed: {deleted_counts['lots']} lots and {deleted_counts['sim_cards']} SIM cards deleted",
            data=deleted_counts
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to cascade delete batch: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'Batch',
    'status',
    name='batch_status_change_handler',
    description='Handle batch status changes and cascade to lots'
)
def handle_batch_status_change(context: TriggerContext) -> TriggerResult:
    """Handle batch status changes"""
    try:
        batch = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        new_status = batch.status

        # Update lots status based on batch status
        lots_updated = 0
        if hasattr(batch, 'lots'):
            for lot in batch.lots.all():
                if new_status == 'active' and lot.status == 'pending':
                    lot.status = 'active'
                    lot.save(update_fields=['status'])
                    lots_updated += 1
                elif new_status == 'suspended':
                    lot.status = 'suspended'
                    lot.save(update_fields=['status'])
                    lots_updated += 1

        # Handle completion
        if new_status == 'completed':
            batch.completed_at = timezone.now()
            batch.save(update_fields=['completed_at'])
            _handle_batch_completion(batch, context.user)

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='batch_status_changed',
            details={
                'batch_id': str(batch.id),
                'batch_number': batch.batch_id,
                'old_status': old_status,
                'new_status': new_status,
                'lots_updated': lots_updated if 'lots_updated' in locals() else 0
            }
        )

        # Send notifications
        _send_batch_status_notifications(batch, old_status, new_status, context.user)

        return TriggerResult(
            success=True,
            message=f"Batch status changed from {old_status} to {new_status}",
            data={
                'old_status': old_status,
                'new_status': new_status,
                'lots_updated': lots_updated if 'lots_updated' in locals() else 0
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle batch status change: {str(e)}",
            error=e
        )

@post_save_trigger(
    'BatchTransfer',
    name='batch_transfer_workflow',
    description='Handle batch transfer workflow between teams'
)
def handle_batch_transfer_workflow(context: TriggerContext) -> TriggerResult:
    """Handle batch transfer workflow stages"""
    try:
        transfer = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        current_status = transfer.status

        if old_status == current_status:
            return TriggerResult(success=True, message="No status change detected")

        # Handle workflow stages
        if current_status == 'approved' and old_status == 'pending':
            _handle_batch_transfer_approval(transfer, context.user)

        elif current_status == 'completed' and old_status == 'approved':
            _handle_batch_transfer_completion(transfer, context.user)

        elif current_status == 'rejected':
            _handle_batch_transfer_rejection(transfer, context.user)

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='batch_transfer_status_changed',
            details={
                'transfer_id': str(transfer.id),
                'batch_id': str(transfer.batch.id),
                'batch_number': transfer.batch.batch_id,
                'old_status': old_status,
                'new_status': current_status,
                'source_team': transfer.source_team.name if transfer.source_team else None,
                'destination_team': transfer.destination_team.name if transfer.destination_team else None
            }
        )

        return TriggerResult(
            success=True,
            message=f"Batch transfer workflow handled for status: {current_status}",
            data={
                'old_status': old_status,
                'new_status': current_status,
                'batch_number': transfer.batch.batch_id
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle batch transfer workflow: {str(e)}",
            error=e
        )


# Helper functions

def _check_batch_completion_condition(batch):
    """Check if batch should be auto-completed"""
    try:
        if batch.status == 'completed':
            return False

        if hasattr(batch, 'lots'):
            total_lots = batch.lots.count()
            completed_lots = batch.lots.filter(status='completed').count()
            return total_lots > 0 and completed_lots == total_lots

        return False
    except:
        return False


def _handle_batch_completion(batch, user):
    """Handle batch completion tasks"""
    try:
        # Calculate final metrics
        _calculate_final_batch_metrics(batch)

        # Create completion notification
        from ssm.models import Notification
        if batch.created_by:
            Notification.objects.create(
                user=batch.created_by,
                title="Batch Completed",
                message=f"Batch {batch.batch_id} has been completed",
                type="batch_completed",
                metadata={
                    'batch_id': str(batch.id),
                    'batch_number': batch.batch_id,
                    'completed_by': str(user) if user else 'System'
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle batch completion: {e}")


def _calculate_final_batch_metrics(batch):
    """Calculate final batch performance metrics"""
    try:
        from ssm.models import SimCard, BatchPerformanceSnapshot

        # Get all SIM cards in batch
        batch_sims = SimCard.objects.filter(batch=batch)

        # Calculate comprehensive metrics
        total_sims = batch_sims.count()
        quality_sims = batch_sims.filter(quality='quality').count()
        registered_sims = batch_sims.filter(registered_on__isnull=False).count()
        sold_sims = batch_sims.filter(status='SOLD').count()

        # Calculate rates
        quality_rate = (quality_sims / total_sims * 100) if total_sims > 0 else 0
        registration_rate = (registered_sims / total_sims * 100) if total_sims > 0 else 0
        sales_rate = (sold_sims / total_sims * 100) if total_sims > 0 else 0

        # Create final performance snapshot
        BatchPerformanceSnapshot.objects.create(
            batch=batch,
            total_sims=total_sims,
            quality_sims=quality_sims,
            non_quality_sims=total_sims - quality_sims,
            registered_sims=registered_sims,
            sold_sims=sold_sims,
            quality_rate=round(quality_rate, 2),
            registration_rate=round(registration_rate, 2),
            sales_rate=round(sales_rate, 2),
            snapshot_type='completion',
            notes=f'Final metrics calculated upon batch completion'
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to calculate final batch metrics: {e}")


def _send_batch_status_notifications(batch, old_status, new_status, user):
    """Send notifications for batch status changes"""
    try:
        from ssm.models import Notification

        # Determine recipients
        recipients = []
        if batch.created_by:
            recipients.append(batch.created_by)

        # Add team members if batch is assigned to a team
        if hasattr(batch, 'assigned_team') and batch.assigned_team:
            team_members = batch.assigned_team.user_set.filter(role__in=['team_leader', 'admin'])
            recipients.extend(team_members)

        # Send notifications
        message = f"Batch {batch.batch_id} status changed from {old_status} to {new_status}"
        for recipient in set(recipients):
            Notification.objects.create(
                user=recipient,
                title="Batch Status Update",
                message=message,
                type="batch_status_change",
                metadata={
                    'batch_id': str(batch.id),
                    'batch_number': batch.batch_id,
                    'old_status': old_status,
                    'new_status': new_status
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send batch status notifications: {e}")


def _handle_batch_transfer_approval(transfer, approver):
    """Handle batch transfer approval"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Batch Transfer Approved",
            message=f"Your batch transfer request for {transfer.batch.batch_id} has been approved",
            type="batch_transfer_approved",
            metadata={
                'transfer_id': str(transfer.id),
                'batch_number': transfer.batch.batch_id,
                'approved_by': str(approver) if approver else 'System'
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle batch transfer approval: {e}")


def _handle_batch_transfer_completion(transfer, receiver):
    """Handle batch transfer completion"""
    try:
        # Update batch assignment
        transfer.batch.assigned_team = transfer.destination_team
        transfer.batch.save(update_fields=['assigned_team'])

        # Update all SIM cards in batch
        from ssm.models import SimCard
        SimCard.objects.filter(batch=transfer.batch).update(team=transfer.destination_team)

        # Update all lots in batch
        if hasattr(transfer.batch, 'lots'):
            transfer.batch.lots.update(assigned_team=transfer.destination_team)

        transfer.completed_at = timezone.now()
        transfer.completed_by = receiver
        transfer.save(update_fields=['completed_at', 'completed_by'])

        # Notify completion
        from ssm.models import Notification
        Notification.objects.create(
            user=transfer.requested_by,
            title="Batch Transfer Completed",
            message=f"Batch {transfer.batch.batch_id} transfer has been completed",
            type="batch_transfer_completed",
            metadata={
                'transfer_id': str(transfer.id),
                'batch_number': transfer.batch.batch_id
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle batch transfer completion: {e}")


def _handle_batch_transfer_rejection(transfer, rejector):
    """Handle batch transfer rejection"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Batch Transfer Rejected",
            message=f"Your batch transfer request for {transfer.batch.batch_id} has been rejected",
            type="batch_transfer_rejected",
            metadata={
                'transfer_id': str(transfer.id),
                'batch_number': transfer.batch.batch_id,
                'rejected_by': str(rejector) if rejector else 'System'
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle batch transfer rejection: {e}")
