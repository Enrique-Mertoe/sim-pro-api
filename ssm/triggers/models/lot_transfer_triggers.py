"""
Lot transfer model triggers
"""
from django.utils import timezone

from ..base.trigger_decorator import (
    post_save_trigger, field_changed_trigger, pre_delete_trigger
)
from ..base.trigger_base import TriggerContext, TriggerResult


@post_save_trigger(
    'SimCardTransfer',
    name='lot_transfer_request_created',
    description='Handle lot transfer request creation and update lot statuses'
)
def handle_lot_transfer_request_created(context: TriggerContext) -> TriggerResult:
    """Handle lot transfer request creation - mark lots as in_transit"""
    try:
        transfer = context.instance
        is_new = context.created

        # Only process for newly created transfer requests
        if not is_new:
            return TriggerResult(success=True, message="Not a new transfer request")

        from ssm.models import LotMetadata

        # Get all lots involved in the transfer
        lot_ids = transfer.lots if isinstance(transfer.lots, list) else []

        if not lot_ids:
            return TriggerResult(
                success=False,
                message="No lots specified in transfer request"
            )

        # Update lot statuses to indicate they're in a transfer request
        updated_lots = LotMetadata.objects.filter(
            id__in=lot_ids
        ).update(status='IN_TRANSFER_REQUEST')

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user_id=transfer.requested_by.id if transfer.requested_by else None,
            action_type='lot_transfer_request_created',
            details={
                'transfer_id': str(transfer.id),
                'lot_ids': lot_ids,
                'lots_count': len(lot_ids),
                'source_team': transfer.source_team.name if transfer.source_team else None,
                'destination_team': transfer.destination_team.name if transfer.destination_team else None,
                'status': transfer.status,
                'lots_updated': updated_lots
            }
        )

        # Send notification to destination team leader
        from ssm.models import Notification
        if transfer.destination_team and transfer.destination_team.leader:
            Notification.objects.create(
                user=transfer.destination_team.leader,
                title="New Lot Transfer Request",
                message=f"Transfer request for {len(lot_ids)} lot(s) from {transfer.source_team.name if transfer.source_team else 'Unknown'}",
                type="lot_transfer_request",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(lot_ids),
                    'source_team': transfer.source_team.name if transfer.source_team else None
                }
            )

        return TriggerResult(
            success=True,
            message=f"Lot transfer request created - {updated_lots} lots marked as IN_TRANSFER_REQUEST",
            data={
                'transfer_id': str(transfer.id),
                'lots_updated': updated_lots,
                'lots_count': len(lot_ids)
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot transfer request creation: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'SimCardTransfer',
    'status',
    name='lot_transfer_status_change_handler',
    description='Handle lot transfer status changes (approval, rejection, cancellation)'
)
def handle_lot_transfer_status_change(context: TriggerContext) -> TriggerResult:
    """Handle lot transfer status changes and update lot statuses accordingly"""
    try:
        transfer = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        new_status = transfer.status

        from ssm.models import LotMetadata

        # Get all lots involved in the transfer
        lot_ids = transfer.lots if isinstance(transfer.lots, list) else []

        if not lot_ids:
            return TriggerResult(success=True, message="No lots in transfer")

        lots = LotMetadata.objects.filter(id__in=lot_ids)
        updated_count = 0

        # Handle different status transitions
        if new_status == 'APPROVED' and old_status == 'PENDING':
            # Transfer approved - actually transfer the lots
            updated_count = lots.update(
                assigned_team=transfer.destination_team,
                status='PENDING',  # Reset to PENDING for the new team
                assigned_on=timezone.now()
            )

            # Update SIM cards team assignment
            # from ssm.models import SimCard
            # for lot in lots:
            #     SimCard.objects.filter(
            #         serial_number__in=lot.serial_numbers
            #     ).update(
            #         team=transfer.destination_team,
            #         assigned_on=timezone.now()
            #     )

            # Send approval notifications
            _send_transfer_approval_notifications(transfer, context.user)

        elif new_status == 'REJECTED':
            # Transfer rejected - restore lots to original state
            updated_count = lots.update(
                status='PENDING',  # Reset to PENDING
                assigned_team=transfer.source_team  # Keep with source team
            )

            # Send rejection notifications
            _send_transfer_rejection_notifications(transfer, context.user)

        elif new_status == 'CANCELLED':
            # Transfer cancelled - restore lots to original state
            updated_count = lots.update(
                status='PENDING',
                assigned_team=transfer.source_team
            )

            # Send cancellation notifications
            _send_transfer_cancellation_notifications(transfer, context.user)

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user_id=context.user.id if context.user else None,
            action_type='lot_transfer_status_changed',
            details={
                'transfer_id': str(transfer.id),
                'lot_ids': lot_ids,
                'lots_count': len(lot_ids),
                'old_status': old_status,
                'new_status': new_status,
                'source_team': transfer.source_team.name if transfer.source_team else None,
                'destination_team': transfer.destination_team.name if transfer.destination_team else None,
                'lots_updated': updated_count
            }
        )

        return TriggerResult(
            success=True,
            message=f"Lot transfer status changed from {old_status} to {new_status} - {updated_count} lots updated",
            data={
                'old_status': old_status,
                'new_status': new_status,
                'lots_updated': updated_count
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot transfer status change: {str(e)}",
            error=e
        )


@pre_delete_trigger(
    'SimCardTransfer',
    name='lot_transfer_deletion_handler',
    description='Handle lot transfer deletion and restore lot statuses'
)
def handle_lot_transfer_deletion(context: TriggerContext) -> TriggerResult:
    """Handle lot transfer deletion - restore lots to original state"""
    try:
        transfer = context.instance

        from ssm.models import LotMetadata

        # Get all lots involved in the transfer
        lot_ids = transfer.lots if isinstance(transfer.lots, list) else []

        if not lot_ids:
            return TriggerResult(success=True, message="No lots to restore")

        # Restore lots to PENDING status with source team
        # Only restore if they were in transfer status
        updated_count = LotMetadata.objects.filter(
            id__in=lot_ids,
            status='IN_TRANSFER_REQUEST'
        ).update(
            status='PENDING',
            assigned_team=transfer.source_team
        )

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user_id=context.user.id if context.user else None,
            action_type='lot_transfer_deleted',
            details={
                'transfer_id': str(transfer.id),
                'lot_ids': lot_ids,
                'lots_count': len(lot_ids),
                'source_team': transfer.source_team.name if transfer.source_team else None,
                'destination_team': transfer.destination_team.name if transfer.destination_team else None,
                'lots_restored': updated_count,
                'transfer_status': transfer.status
            }
        )

        # Send notification to requester
        from ssm.models import Notification
        if transfer.requested_by:
            Notification.objects.create(
                user=transfer.requested_by,
                title="Lot Transfer Request Deleted",
                message=f"Transfer request for {len(lot_ids)} lot(s) has been deleted",
                type="lot_transfer_deleted",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(lot_ids),
                    'lots_restored': updated_count
                }
            )

        return TriggerResult(
            success=True,
            message=f"Lot transfer deleted - {updated_count} lots restored to PENDING status",
            data={
                'lots_restored': updated_count,
                'lots_count': len(lot_ids)
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot transfer deletion: {str(e)}",
            error=e
        )


# Helper functions for notifications

def _send_transfer_approval_notifications(transfer, approver):
    """Send notifications when transfer is approved"""
    try:
        from ssm.models import Notification

        # Notify requester
        if transfer.requested_by:
            Notification.objects.create(
                user=transfer.requested_by,
                title="Lot Transfer Approved",
                message=f"Your transfer request for {len(transfer.lots)} lot(s) has been approved",
                type="lot_transfer_approved",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(transfer.lots),
                    'approved_by': approver.full_name if approver else 'System',
                    'destination_team': transfer.destination_team.name if transfer.destination_team else None
                }
            )

        # Notify destination team leader
        if transfer.destination_team and transfer.destination_team.leader:
            Notification.objects.create(
                user=transfer.destination_team.leader,
                title="Lot Transfer Approved",
                message=f"Transfer of {len(transfer.lots)} lot(s) to your team has been approved",
                type="lot_transfer_approved",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(transfer.lots),
                    'source_team': transfer.source_team.name if transfer.source_team else None
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send transfer approval notifications: {e}")


def _send_transfer_rejection_notifications(transfer, rejector):
    """Send notifications when transfer is rejected"""
    try:
        from ssm.models import Notification

        # Notify requester
        if transfer.requested_by:
            Notification.objects.create(
                user=transfer.requested_by,
                title="Lot Transfer Rejected",
                message=f"Your transfer request for {len(transfer.lots)} lot(s) has been rejected",
                type="lot_transfer_rejected",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(transfer.lots),
                    'rejected_by': rejector.full_name if rejector else 'System',
                    'notes': transfer.notes
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send transfer rejection notifications: {e}")


def _send_transfer_cancellation_notifications(transfer, canceller):
    """Send notifications when transfer is cancelled"""
    try:
        from ssm.models import Notification

        # Notify destination team leader
        if transfer.destination_team and transfer.destination_team.leader:
            Notification.objects.create(
                user=transfer.destination_team.leader,
                title="Lot Transfer Cancelled",
                message=f"Transfer request for {len(transfer.lots)} lot(s) has been cancelled",
                type="lot_transfer_cancelled",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lots_count': len(transfer.lots),
                    'cancelled_by': canceller.full_name if canceller else 'System'
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send transfer cancellation notifications: {e}")