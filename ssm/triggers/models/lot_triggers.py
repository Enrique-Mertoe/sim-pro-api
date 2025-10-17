"""
Lot management model triggers
"""
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Q

from ..base.trigger_decorator import (
    post_save_trigger, field_changed_trigger, conditional_trigger, pre_save_trigger
)
from ..base.trigger_base import TriggerContext, TriggerResult, TriggerEvent
from ssm.models import LotMetadata
from ...utils.lot_utils import update_lot_assignment_counts


# @post_save_trigger(
#     'LotMetadata',
#     name='lot_serial_numbers_creation',
#     description='Create SIM card records when lot is created with serial numbers'
# )
# def handle_lot_serial_numbers_creation(context: TriggerContext[LotMetadata]) -> TriggerResult:
#     """Create SIM card records from lot serial numbers on lot creation"""
#     try:
#         lot = context.instance
#
#         # Only process if this is a new lot with serial numbers
#         if context.created and lot.serial_numbers:
#             from ssm.models import SimCard
#
#             # Get existing serial numbers to avoid duplicates
#             existing_serials = set(
#                 SimCard.objects.filter(
#                     serial_number__in=lot.serial_numbers
#                 ).values_list('serial_number', flat=True)
#             )
#
#             # Create SIM card records for new serial numbers
#             sim_cards_to_create = []
#             for serial_number in lot.serial_numbers:
#                 if serial_number not in existing_serials:
#                     sim_cards_to_create.append(
#                         SimCard(
#                             serial_number=serial_number,
#                             batch=lot.batch,
#                             lot=lot.lot_number,
#                             team=lot.assigned_team,
#                             admin=lot.admin,
#                             status='PENDING',
#                             quality='N',
#                             match='Y'
#                         )
#                     )
#
#             # Bulk create SIM cards
#             created_count = 0
#             if sim_cards_to_create:
#                 SimCard.objects.bulk_create(sim_cards_to_create, batch_size=500)
#                 created_count = len(sim_cards_to_create)
#
#             return TriggerResult(
#                 success=True,
#                 message=f"Created {created_count} SIM card records for lot {lot.lot_number}",
#                 data={
#                     'lot_number': lot.lot_number,
#                     'total_serials': len(lot.serial_numbers),
#                     'created_count': created_count,
#                     'skipped_duplicates': len(existing_serials)
#                 }
#             )
#
#         return TriggerResult(
#             success=True,
#             message="No serial numbers to process",
#             data={}
#         )
#
#     except Exception as e:
#         return TriggerResult(
#             success=False,
#             message=f"Failed to create SIM cards from lot serial numbers: {str(e)}",
#             error=e
#         )


@post_save_trigger(
    'LotMetadata',
    name='lot_quality_metrics_update',
    description='Update lot quality metrics when lot is saved'
)
def handle_lot_quality_update(context: TriggerContext[LotMetadata]) -> TriggerResult:
    """Update lot quality metrics based on SIM card quality"""
    try:
        lot = context.instance

        # Get SIM cards in this lot
        from ssm.models import SimCard
        lot_sim_cards = SimCard.objects.filter(
            serial_number__in=lot.serial_numbers
        )

        # Calculate quality metrics
        total_sims = lot_sim_cards.count()
        quality_sims = lot_sim_cards.filter(quality='Y').count()
        non_quality_sims = lot_sim_cards.filter(quality='N').count()

        # Update lot metrics
        lot.quality_count = quality_sims
        lot.nonquality_count = non_quality_sims
        lot.save(update_fields=['quality_count', 'nonquality_count'])

        return TriggerResult(
            success=True,
            message="Lot quality metrics updated successfully",
            data={
                'total_sims': total_sims,
                'quality_count': quality_sims,
                'non_quality_count': non_quality_sims
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to update lot quality metrics: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'Lot',
    'status',
    name='lot_status_change_handler',
    description='Handle lot status changes and update related records'
)
def handle_lot_status_change(context: TriggerContext) -> TriggerResult:
    """Handle lot status changes"""
    try:
        lot = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        new_status = lot.status

        # Update SIM cards status based on lot status
        from ssm.models import SimCard
        lot_sim_cards = SimCard.objects.filter(serial_number__in=lot.serial_numbers)

        if new_status == 'active':
            lot_sim_cards.update(status='PENDING')
        elif new_status == 'suspended':
            lot_sim_cards.update(status='SUSPENDED')
        elif new_status == 'completed':
            # Mark lot completion timestamp
            lot.completed_at = timezone.now()
            lot.save(update_fields=['completed_at'])

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='lot_status_changed',
            details={
                'lot_id': str(lot.id),
                'lot_number': lot.lot_number,
                'old_status': old_status,
                'new_status': new_status,
                'affected_sim_cards': lot_sim_cards.count()
            }
        )

        # Send notifications to relevant users
        _send_lot_status_notifications(lot, old_status, new_status, context.user)

        return TriggerResult(
            success=True,
            message=f"Lot status changed from {old_status} to {new_status}",
            data={
                'old_status': old_status,
                'new_status': new_status,
                'affected_sim_cards': lot_sim_cards.count()
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot status change: {str(e)}",
            error=e
        )


@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'Lot',
    condition_func=lambda ctx: ctx.instance.quality_count + ctx.instance.nonquality_count == len(
        ctx.instance.serial_numbers),
    name='lot_completion_check',
    description='Check if lot is completed when all SIMs are processed'
)
def handle_lot_completion_check(context: TriggerContext) -> TriggerResult:
    """Check and handle lot completion when all SIMs are processed"""
    try:
        lot = context.instance

        # Mark lot as completed if not already
        if lot.status != 'completed':
            lot.status = 'completed'
            lot.completed_at = timezone.now()
            lot.save(update_fields=['status', 'completed_at'])

            # Calculate final quality rate
            total_sims = len(lot.serial_numbers)
            quality_rate = (lot.quality_count / total_sims * 100) if total_sims > 0 else 0

            # Create completion notification
            from ssm.models import Notification
            if lot.batch and lot.batch.created_by:
                Notification.objects.create(
                    user=lot.batch.created_by,
                    title="Lot Completed",
                    message=f"Lot {lot.lot_number} has been completed with {quality_rate:.1f}% quality rate",
                    type="lot_completed",
                    metadata={
                        'lot_id': str(lot.id),
                        'lot_number': lot.lot_number,
                        'quality_rate': quality_rate,
                        'total_sims': total_sims
                    }
                )

            # Check if batch is completed
            if lot.batch:
                _check_batch_completion(lot.batch)

        return TriggerResult(
            success=True,
            message="Lot completion check completed",
            data={'lot_completed': lot.status == 'completed'}
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to check lot completion: {str(e)}",
            error=e
        )


@field_changed_trigger(
    'LotMetadata',
    'assigned_team_id',
    name='lot_team_change_handler',
    description='Handle lot team assignment changes'
)
def handle_lot_team_change(context: TriggerContext[LotMetadata]) -> TriggerResult:
    """Handle lot team assignment changes and update SIM cards"""
    try:
        lot = context.instance
        old_team = getattr(context.old_instance, 'assigned_team', None) if context.old_instance else None
        new_team = lot.assigned_team

        # Update assigned_on timestamp when team is assigned
        if new_team:
            lot.assigned_on = timezone.now()
            lot.save(update_fields=['assigned_on'])
        elif not new_team:
            lot.assigned_on = None
            lot.save(update_fields=['assigned_on'])

        # Update all SIM cards in lot to new team
        from ssm.models import SimCard
        updated_count = SimCard.objects.filter(
            serial_number__in=lot.serial_numbers
        ).update(team=new_team)
        update_lot_assignment_counts(lot.lot_number)

        # Update batch teams field
        batch = lot.batch
        if batch:
            # Build teams structure with lot assignments
            teams_dict = {}
            for batch_lot in batch.lots.all():
                if batch_lot.assigned_team_id and batch_lot.assigned_team:
                    team_id = str(batch_lot.assigned_team_id)
                    if team_id not in teams_dict:
                        teams_dict[team_id] = {
                            'teamId': team_id,
                            'teamName': batch_lot.assigned_team.name,
                            'lotNumbers': []
                        }
                    teams_dict[team_id]['lotNumbers'].append(batch_lot.lot_number)

            # Update batch teams field
            batch.teams = list(teams_dict.values())
            batch.save(update_fields=['teams'])

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user_id=context.user.id,
            action_type='lot_team_changed',
            details={
                'lot_id': str(lot.id),
                'lot_number': lot.lot_number,
                'old_team': old_team.name if old_team else None,
                'new_team': new_team.name if new_team else None,
                'sim_cards_updated': updated_count
            }
        )

        # Send notifications
        from ssm.models import Notification
        recipients = []

        # Notify old team leader
        if old_team and old_team.leader:
            recipients.append(old_team.leader)
            Notification.objects.create(
                user=old_team.leader,
                title="Lot Reassigned",
                message=f"Lot {lot.lot_number} has been reassigned from your team",
                type="lot_team_change",
                metadata={
                    'lot_id': str(lot.id),
                    'lot_number': lot.lot_number,
                    'action': 'removed'
                }
            )

        # Notify new team leader
        if new_team and new_team.leader:
            recipients.append(new_team.leader)
            Notification.objects.create(
                user=new_team.leader,
                title="Lot Assigned",
                message=f"Lot {lot.lot_number} has been assigned to your team",
                type="lot_team_change",
                metadata={
                    'lot_id': str(lot.id),
                    'lot_number': lot.lot_number,
                    'action': 'assigned'
                }
            )

        return TriggerResult(
            success=True,
            message=f"Lot team changed from {old_team} to {new_team}",
            data={
                'old_team': old_team.name if old_team else None,
                'new_team': new_team.name if new_team else None,
                'sim_cards_updated': updated_count,
                'notifications_sent': len(recipients),
                'batch_teams_updated': len(batch.teams) if batch else 0
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot team change: {str(e)}",
            error=e
        )


@post_save_trigger(
    'LotTransfer',
    name='lot_transfer_workflow',
    description='Handle lot transfer workflow and inventory updates'
)
def handle_lot_transfer_workflow(context: TriggerContext) -> TriggerResult:
    """Handle lot transfer workflow stages"""
    try:
        transfer = context.instance
        old_status = getattr(context.old_instance, 'status', None) if context.old_instance else None
        current_status = transfer.status

        # Skip if status hasn't changed
        if old_status == current_status:
            return TriggerResult(success=True, message="No status change detected")

        # Handle different workflow stages
        if current_status == 'approved' and old_status == 'pending':
            _handle_lot_transfer_approval(transfer, context.user)

        elif current_status == 'in_transit' and old_status == 'approved':
            _handle_lot_transfer_dispatch(transfer, context.user)

        elif current_status == 'completed' and old_status == 'in_transit':
            _handle_lot_transfer_completion(transfer, context.user)

        elif current_status == 'rejected':
            _handle_lot_transfer_rejection(transfer, context.user)

        # Create activity log
        from ssm.models import ActivityLog
        ActivityLog.objects.create(
            user=context.user,
            action_type='lot_transfer_status_changed',
            details={
                'transfer_id': str(transfer.id),
                'lot_id': str(transfer.lot.id),
                'lot_number': transfer.lot.lot_number,
                'old_status': old_status,
                'new_status': current_status,
                'source_team': transfer.source_team.name if transfer.source_team else None,
                'destination_team': transfer.destination_team.name if transfer.destination_team else None
            }
        )

        return TriggerResult(
            success=True,
            message=f"Lot transfer workflow handled for status: {current_status}",
            data={
                'old_status': old_status,
                'new_status': current_status,
                'lot_number': transfer.lot.lot_number
            }
        )

    except Exception as e:
        return TriggerResult(
            success=False,
            message=f"Failed to handle lot transfer workflow: {str(e)}",
            error=e
        )


# Helper functions

def _send_lot_status_notifications(lot, old_status, new_status, user):
    """Send notifications for lot status changes"""
    try:
        from ssm.models import Notification

        # Determine recipients
        recipients = []
        if lot.batch and lot.batch.created_by:
            recipients.append(lot.batch.created_by)

        # Add team members if lot is assigned to a team
        if hasattr(lot, 'assigned_team') and lot.assigned_team:
            team_members = lot.assigned_team.user_set.filter(role__in=['team_leader', 'admin'])
            recipients.extend(team_members)

        # Send notifications
        message = f"Lot {lot.lot_number} status changed from {old_status} to {new_status}"
        for recipient in set(recipients):
            Notification.objects.create(
                user=recipient,
                title="Lot Status Update",
                message=message,
                type="lot_status_change",
                metadata={
                    'lot_id': str(lot.id),
                    'lot_number': lot.lot_number,
                    'old_status': old_status,
                    'new_status': new_status
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send lot status notifications: {e}")


def _check_batch_completion(batch):
    """Check if batch is completed based on lot completion"""
    try:
        total_lots = batch.lots.count()
        completed_lots = batch.lots.filter(status='completed').count()

        if total_lots > 0 and completed_lots == total_lots:
            batch.status = 'completed'
            batch.completed_at = timezone.now()
            batch.save(update_fields=['status', 'completed_at'])

            # Send batch completion notification
            from ssm.models import Notification
            if batch.created_by:
                Notification.objects.create(
                    user=batch.created_by,
                    title="Batch Completed",
                    message=f"Batch {batch.batch_id} has been completed. All {total_lots} lots are processed.",
                    type="batch_completed",
                    metadata={
                        'batch_id': str(batch.id),
                        'batch_number': batch.batch_id,
                        'total_lots': total_lots
                    }
                )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to check batch completion: {e}")


def _handle_lot_transfer_approval(transfer, approver):
    """Handle lot transfer approval"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Lot Transfer Approved",
            message=f"Your lot transfer request for {transfer.lot.lot_number} has been approved",
            type="lot_transfer_approved",
            metadata={
                'transfer_id': str(transfer.id),
                'lot_number': transfer.lot.lot_number,
                'approved_by': str(approver) if approver else 'System'
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle lot transfer approval: {e}")


def _handle_lot_transfer_dispatch(transfer, dispatcher):
    """Handle lot transfer dispatch"""
    try:
        transfer.dispatch_date = timezone.now()
        transfer.dispatched_by = dispatcher
        transfer.save(update_fields=['dispatch_date', 'dispatched_by'])

        # Notify destination team
        from ssm.models import Notification
        if transfer.destination_team and transfer.destination_team.leader:
            Notification.objects.create(
                user=transfer.destination_team.leader,
                title="Lot Transfer Dispatched",
                message=f"Lot {transfer.lot.lot_number} has been dispatched to your team",
                type="lot_transfer_dispatched",
                metadata={
                    'transfer_id': str(transfer.id),
                    'lot_number': transfer.lot.lot_number
                }
            )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle lot transfer dispatch: {e}")


def _handle_lot_transfer_completion(transfer, receiver):
    """Handle lot transfer completion"""
    try:
        # Update lot assignment
        transfer.lot.assigned_team = transfer.destination_team
        transfer.lot.save(update_fields=['assigned_team'])

        # Update SIM cards team assignment
        from ssm.models import SimCard
        SimCard.objects.filter(
            serial_number__in=transfer.lot.serial_numbers
        ).update(team=transfer.destination_team)

        transfer.received_date = timezone.now()
        transfer.received_by = receiver
        transfer.save(update_fields=['received_date', 'received_by'])

        # Notify completion
        from ssm.models import Notification
        Notification.objects.create(
            user=transfer.requested_by,
            title="Lot Transfer Completed",
            message=f"Lot {transfer.lot.lot_number} transfer has been completed",
            type="lot_transfer_completed",
            metadata={
                'transfer_id': str(transfer.id),
                'lot_number': transfer.lot.lot_number
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle lot transfer completion: {e}")


def _handle_lot_transfer_rejection(transfer, rejector):
    """Handle lot transfer rejection"""
    try:
        from ssm.models import Notification

        # Notify requesting user
        Notification.objects.create(
            user=transfer.requested_by,
            title="Lot Transfer Rejected",
            message=f"Your lot transfer request for {transfer.lot.lot_number} has been rejected",
            type="lot_transfer_rejected",
            metadata={
                'transfer_id': str(transfer.id),
                'lot_number': transfer.lot.lot_number,
                'rejected_by': str(rejector) if rejector else 'System'
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to handle lot transfer rejection: {e}")
