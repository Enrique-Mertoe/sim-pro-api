"""
Common trigger actions for SSM models
"""
import logging
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from django.db import models, transaction
from django.core.mail import send_mail
from django.conf import settings

from ..base.trigger_base import TriggerAction, TriggerContext, TriggerResult

logger = logging.getLogger(__name__)


class LogAction(TriggerAction):
    """Action that logs information"""

    def __init__(self, message: str, level: str = 'INFO', include_context: bool = True):
        self.message = message
        self.level = level.upper()
        self.include_context = include_context

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            log_message = self.message

            if self.include_context:
                context_info = {
                    'event': context.event.value,
                    'model': context.model.__name__,
                    'instance_id': str(context.instance.pk) if context.instance else None,
                    'user': str(context.user) if context.user else None,
                    'timestamp': context.timestamp.isoformat()
                }
                log_message += f" | Context: {json.dumps(context_info)}"

            # Log based on level
            if self.level == 'DEBUG':
                logger.debug(log_message)
            elif self.level == 'INFO':
                logger.info(log_message)
            elif self.level == 'WARNING':
                logger.warning(log_message)
            elif self.level == 'ERROR':
                logger.error(log_message)
            elif self.level == 'CRITICAL':
                logger.critical(log_message)

            return TriggerResult(success=True, message="Log entry created")

        except Exception as e:
            return TriggerResult(success=False, message=f"Logging failed: {str(e)}", error=e)

    def description(self) -> str:
        return f"Log message: {self.message} (level: {self.level})"


class UpdateFieldAction(TriggerAction):
    """Action that updates a field on the instance"""

    def __init__(self, field_name: str, value: Any, condition_field: str = None, condition_value: Any = None):
        self.field_name = field_name
        self.value = value
        self.condition_field = condition_field
        self.condition_value = condition_value

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            if not context.instance:
                return TriggerResult(success=False, message="No instance to update")

            # Check condition if specified
            if self.condition_field:
                current_value = getattr(context.instance, self.condition_field, None)
                if current_value != self.condition_value:
                    return TriggerResult(
                        success=True,
                        message=f"Condition not met: {self.condition_field}={current_value}"
                    )

            # Update the field
            old_value = getattr(context.instance, self.field_name, None)
            setattr(context.instance, self.field_name, self.value)

            with transaction.atomic():
                context.instance.save(update_fields=[self.field_name])

            return TriggerResult(
                success=True,
                message=f"Updated {self.field_name} from {old_value} to {self.value}",
                data={
                    'field_name': self.field_name,
                    'old_value': old_value,
                    'new_value': self.value
                },
                modified_fields=[self.field_name]
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Field update failed: {str(e)}", error=e)

    def description(self) -> str:
        desc = f"Update field '{self.field_name}' to '{self.value}'"
        if self.condition_field:
            desc += f" if {self.condition_field}={self.condition_value}"
        return desc


class CreateRecordAction(TriggerAction):
    """Action that creates a new record"""

    def __init__(self, model_class: models.Model, field_data: Dict[str, Any],
                 related_field: str = None):
        self.model_class = model_class
        self.field_data = field_data
        self.related_field = related_field

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            # Prepare field data
            data = self.field_data.copy()

            # Add related field if specified
            if self.related_field and context.instance:
                data[self.related_field] = context.instance

            # Add user if available and field exists
            if context.user and 'created_by' in [f.name for f in self.model_class._meta.fields]:
                data['created_by'] = context.user

            with transaction.atomic():
                new_record = self.model_class.objects.create(**data)

            return TriggerResult(
                success=True,
                message=f"Created {self.model_class.__name__} record",
                data={
                    'created_record_id': str(new_record.pk),
                    'model': self.model_class.__name__
                }
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Record creation failed: {str(e)}", error=e)

    def description(self) -> str:
        return f"Create {self.model_class.__name__} record"


class SendEmailAction(TriggerAction):
    """Action that sends an email"""

    def __init__(self, subject: str, message: str, recipient_emails: List[str],
                 from_email: str = None, use_template: bool = False):
        self.subject = subject
        self.message = message
        self.recipient_emails = recipient_emails
        self.from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
        self.use_template = use_template

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            # Replace placeholders in subject and message
            subject = self._replace_placeholders(self.subject, context)
            message = self._replace_placeholders(self.message, context)

            send_mail(
                subject=subject,
                message=message,
                from_email=self.from_email,
                recipient_list=self.recipient_emails,
                fail_silently=False
            )

            return TriggerResult(
                success=True,
                message=f"Email sent to {len(self.recipient_emails)} recipients",
                data={
                    'recipients': self.recipient_emails,
                    'subject': subject
                }
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Email sending failed: {str(e)}", error=e)

    def _replace_placeholders(self, text: str, context: TriggerContext) -> str:
        """Replace placeholders in text with context data"""
        replacements = {
            '{event}': context.event.value,
            '{model}': context.model.__name__,
            '{timestamp}': context.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            '{user}': str(context.user) if context.user else 'System',
        }

        if context.instance:
            replacements['{instance_id}'] = str(context.instance.pk)
            # Add common fields if they exist
            for field in ['name', 'title', 'status', 'shop_code', 'serial_number']:
                if hasattr(context.instance, field):
                    replacements[f'{{{field}}}'] = str(getattr(context.instance, field))

        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)

        return text

    def description(self) -> str:
        return f"Send email to {len(self.recipient_emails)} recipients: {self.subject}"


class NotificationAction(TriggerAction):
    """Action that creates system notifications"""

    def __init__(self, title: str, message: str, notification_type: str = 'info',
                 target_users: List[Any] = None):
        self.title = title
        self.message = message
        self.notification_type = notification_type
        self.target_users = target_users or []

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            from ssm.models import Notification, User

            # Replace placeholders
            title = self._replace_placeholders(self.title, context)
            message = self._replace_placeholders(self.message, context)

            # Determine target users
            users_to_notify = self.target_users.copy()
            if not users_to_notify and context.user:
                users_to_notify = [context.user]

            notifications_created = 0
            with transaction.atomic():
                for user in users_to_notify:
                    # Ensure user is a User instance
                    if not isinstance(user, User):
                        try:
                            user = User.objects.get(pk=user)
                        except User.DoesNotExist:
                            continue

                    Notification.objects.create(
                        user=user,
                        title=title,
                        message=message,
                        type=self.notification_type,
                        metadata={
                            'trigger_event': context.event.value,
                            'source_model': context.model.__name__,
                            'source_id': str(context.instance.pk) if context.instance else None
                        }
                    )
                    notifications_created += 1

            return TriggerResult(
                success=True,
                message=f"Created {notifications_created} notifications",
                data={
                    'notifications_created': notifications_created,
                    'title': title
                }
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Notification creation failed: {str(e)}", error=e)

    def _replace_placeholders(self, text: str, context: TriggerContext) -> str:
        """Replace placeholders in text with context data"""
        replacements = {
            '{event}': context.event.value,
            '{model}': context.model.__name__,
            '{timestamp}': context.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            '{user}': str(context.user) if context.user else 'System',
        }

        if context.instance:
            replacements['{instance_id}'] = str(context.instance.pk)

        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)

        return text

    def description(self) -> str:
        return f"Create notification: {self.title}"


class HTTPWebhookAction(TriggerAction):
    """Action that sends HTTP webhook requests"""

    def __init__(self, url: str, method: str = 'POST', headers: Dict[str, str] = None,
                 payload_template: Dict[str, Any] = None):
        self.url = url
        self.method = method.upper()
        self.headers = headers or {'Content-Type': 'application/json'}
        self.payload_template = payload_template or {}

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            import requests

            # Build payload
            payload = self._build_payload(context)

            # Send request
            response = requests.request(
                method=self.method,
                url=self.url,
                json=payload,
                headers=self.headers,
                timeout=30
            )

            response.raise_for_status()

            return TriggerResult(
                success=True,
                message=f"Webhook sent successfully (status: {response.status_code})",
                data={
                    'status_code': response.status_code,
                    'response_text': response.text[:500]  # Limit response text
                }
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Webhook failed: {str(e)}", error=e)

    def _build_payload(self, context: TriggerContext) -> Dict[str, Any]:
        """Build webhook payload from context"""
        payload = {
            'event': context.event.value,
            'model': context.model.__name__,
            'timestamp': context.timestamp.isoformat(),
            'trigger_id': context.trigger_id
        }

        if context.instance:
            payload['instance'] = {
                'id': str(context.instance.pk),
                'model': context.instance.__class__.__name__
            }

        if context.user:
            payload['user'] = {
                'id': str(context.user.pk) if hasattr(context.user, 'pk') else str(context.user),
                'username': getattr(context.user, 'username', None)
            }

        # Merge with template
        payload.update(self.payload_template)

        return payload

    def description(self) -> str:
        return f"Send {self.method} webhook to {self.url}"


class AuditLogAction(TriggerAction):
    """Action that creates detailed audit log entries"""

    def __init__(self, action_type: str, description: str = None, include_changes: bool = True):
        self.action_type = action_type
        self.description = description
        self.include_changes = include_changes

    def execute(self, context: TriggerContext) -> TriggerResult:
        try:
            from ssm.models import ActivityLog

            # Build details
            details = {
                'trigger_event': context.event.value,
                'action_type': self.action_type,
                'timestamp': context.timestamp.isoformat()
            }

            if self.include_changes and context.old_instance and context.instance:
                details['changes'] = context.get_field_changes()

            if context.metadata:
                details['metadata'] = context.metadata

            # Create audit log
            with transaction.atomic():
                ActivityLog.objects.create(
                    user=context.user,
                    action_type=self.action_type,
                    details=details,
                    ip_address=getattr(context.request, 'META', {}).get('REMOTE_ADDR') if context.request else None
                )

            return TriggerResult(
                success=True,
                message="Audit log entry created",
                data={'action_type': self.action_type}
            )

        except Exception as e:
            return TriggerResult(success=False, message=f"Audit log creation failed: {str(e)}", error=e)

    def description(self) -> str:
        return f"Create audit log: {self.action_type}"


# Convenience functions for creating common actions
def log_info(message: str, include_context: bool = True) -> LogAction:
    return LogAction(message, 'INFO', include_context)


def log_warning(message: str, include_context: bool = True) -> LogAction:
    return LogAction(message, 'WARNING', include_context)


def log_error(message: str, include_context: bool = True) -> LogAction:
    return LogAction(message, 'ERROR', include_context)


def update_field(field_name: str, value: Any) -> UpdateFieldAction:
    return UpdateFieldAction(field_name, value)


def send_notification(title: str, message: str, users: List[Any] = None) -> NotificationAction:
    return NotificationAction(title, message, target_users=users)


def create_audit_log(action_type: str, description: str = None) -> AuditLogAction:
    return AuditLogAction(action_type, description)