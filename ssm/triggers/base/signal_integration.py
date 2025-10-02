"""
Django signals integration for the trigger system
"""
import logging
import copy
from typing import Dict, Any, Optional
from django.db.models.signals import (
    pre_save, post_save, pre_delete, post_delete,
    pre_migrate, post_migrate
)
from django.dispatch import receiver
from django.db import models
from django.contrib.auth import get_user_model

from .trigger_base import TriggerEvent, TriggerContext
from .trigger_engine import TriggerEngine
from ..registry.trigger_registry import get_global_registry

logger = logging.getLogger(__name__)

# Global trigger engine instance
_trigger_engine = None


def get_trigger_engine() -> TriggerEngine:
    """Get the global trigger engine instance"""
    global _trigger_engine
    if _trigger_engine is None:
        registry = get_global_registry()
        _trigger_engine = TriggerEngine(registry)
    return _trigger_engine


class TriggerSignalHandler:
    """Handler for Django signals that executes triggers"""

    def __init__(self):
        self.engine = get_trigger_engine()
        self.enabled = True
        self._instance_cache = {}  # Cache for storing pre-save instances

    def handle_pre_save(self, sender, instance, raw=False, using=None, update_fields=None, **kwargs):
        """Handle pre_save signal"""
        if not self.enabled:
            return

        try:
            # Store the old instance for comparison in post_save
            if instance.pk:
                try:
                    old_instance = sender.objects.get(pk=instance.pk)
                    self._instance_cache[f"{sender.__name__}_{instance.pk}"] = copy.deepcopy(old_instance)
                except sender.DoesNotExist:
                    pass

            # Create context for pre_save
            context = TriggerContext(
                event=TriggerEvent.PRE_SAVE,
                model=sender,
                instance=instance,
                raw=raw,
                using=using,
                update_fields=update_fields
            )

            # Execute triggers
            self.engine.execute_triggers(TriggerEvent.PRE_SAVE, context)

        except Exception as e:
            logger.error(f"Error in pre_save trigger handler: {e}")

    def handle_post_save(self, sender, instance, created=False, raw=False, using=None, update_fields=None, **kwargs):
        """Handle post_save signal"""
        if not self.enabled:
            return

        try:
            # Get old instance from cache if it exists
            cache_key = f"{sender.__name__}_{instance.pk}"
            old_instance = self._instance_cache.pop(cache_key, None)

            # Create context for post_save
            context = TriggerContext(
                event=TriggerEvent.POST_SAVE,
                model=sender,
                instance=instance,
                old_instance=old_instance,
                created=created,
                raw=raw,
                using=using,
                update_fields=update_fields
            )

            # Execute triggers
            self.engine.execute_triggers(TriggerEvent.POST_SAVE, context)

        except Exception as e:
            logger.error(f"Error in post_save trigger handler: {e}")

    def handle_pre_delete(self, sender, instance, using=None, **kwargs):
        """Handle pre_delete signal"""
        if not self.enabled:
            return

        try:
            # Create context for pre_delete
            context = TriggerContext(
                event=TriggerEvent.PRE_DELETE,
                model=sender,
                instance=instance,
                using=using
            )

            # Execute triggers
            self.engine.execute_triggers(TriggerEvent.PRE_DELETE, context)

        except Exception as e:
            logger.error(f"Error in pre_delete trigger handler: {e}")

    def handle_post_delete(self, sender, instance, using=None, **kwargs):
        """Handle post_delete signal"""
        if not self.enabled:
            return

        try:
            # Create context for post_delete
            context = TriggerContext(
                event=TriggerEvent.POST_DELETE,
                model=sender,
                instance=instance,
                using=using
            )

            # Execute triggers
            self.engine.execute_triggers(TriggerEvent.POST_DELETE, context)

        except Exception as e:
            logger.error(f"Error in post_delete trigger handler: {e}")

    def enable(self):
        """Enable signal handling"""
        self.enabled = True
        logger.info("Trigger signal handler enabled")

    def disable(self):
        """Disable signal handling"""
        self.enabled = False
        logger.info("Trigger signal handler disabled")

    def clear_cache(self):
        """Clear instance cache"""
        self._instance_cache.clear()
        logger.debug("Trigger signal handler cache cleared")


# Global signal handler instance
_signal_handler = TriggerSignalHandler()


def get_signal_handler() -> TriggerSignalHandler:
    """Get the global signal handler instance"""
    return _signal_handler


# Signal receivers that delegate to the handler
@receiver(pre_save)
def trigger_pre_save_handler(sender, **kwargs):
    """Pre-save signal receiver"""
    _signal_handler.handle_pre_save(sender, **kwargs)


@receiver(post_save)
def trigger_post_save_handler(sender, **kwargs):
    """Post-save signal receiver"""
    _signal_handler.handle_post_save(sender, **kwargs)


@receiver(pre_delete)
def trigger_pre_delete_handler(sender, **kwargs):
    """Pre-delete signal receiver"""
    _signal_handler.handle_pre_delete(sender, **kwargs)


@receiver(post_delete)
def trigger_post_delete_handler(sender, **kwargs):
    """Post-delete signal receiver"""
    _signal_handler.handle_post_delete(sender, **kwargs)


# Middleware for adding request context to triggers
class TriggerRequestMiddleware:
    """Middleware to add request context to triggers"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in thread-local storage for access in triggers
        _set_current_request(request)

        try:
            response = self.get_response(request)
            return response
        finally:
            # Clean up request context
            _clear_current_request()

    def process_exception(self, request, exception):
        """Handle exceptions and clear context"""
        _clear_current_request()
        return None


# Thread-local storage for request context
import threading
_local = threading.local()


def _set_current_request(request):
    """Set current request in thread-local storage"""
    _local.current_request = request

    # Also try to extract user from request
    if hasattr(request, 'user') and request.user.is_authenticated:
        _local.current_user = request.user


def _clear_current_request():
    """Clear current request from thread-local storage"""
    if hasattr(_local, 'current_request'):
        delattr(_local, 'current_request')
    if hasattr(_local, 'current_user'):
        delattr(_local, 'current_user')


def get_current_request():
    """Get current request from thread-local storage"""
    return getattr(_local, 'current_request', None)


def get_current_user():
    """Get current user from thread-local storage"""
    return getattr(_local, 'current_user', None)


# Enhanced context creation that includes request/user info
def create_enhanced_context(
    event: TriggerEvent,
    model: models.Model,
    instance: Optional[models.Model] = None,
    old_instance: Optional[models.Model] = None,
    **kwargs
) -> TriggerContext:
    """Create trigger context with enhanced information"""
    context = TriggerContext(
        event=event,
        model=model,
        instance=instance,
        old_instance=old_instance,
        **kwargs
    )

    # Add request and user if available
    current_request = get_current_request()
    current_user = get_current_user()

    if current_request:
        context.request = current_request

    if current_user:
        context.user = current_user

    return context


# Utility functions for manual trigger execution
def execute_trigger_manually(
    trigger_name: str,
    instance: models.Model,
    event: TriggerEvent = TriggerEvent.CUSTOM,
    user: Any = None,
    metadata: Dict[str, Any] = None
):
    """Manually execute a specific trigger"""
    engine = get_trigger_engine()

    context = TriggerContext(
        event=event,
        model=instance.__class__,
        instance=instance,
        user=user or get_current_user(),
        request=get_current_request(),
        metadata=metadata or {}
    )

    return engine.execute_custom_trigger(trigger_name, context)


def trigger_custom_event(
    event_name: str,
    instance: models.Model,
    user: Any = None,
    metadata: Dict[str, Any] = None
):
    """Trigger a custom event for an instance"""
    engine = get_trigger_engine()

    context = TriggerContext(
        event=TriggerEvent.CUSTOM,
        model=instance.__class__,
        instance=instance,
        user=user or get_current_user(),
        request=get_current_request(),
        metadata={'custom_event': event_name, **(metadata or {})}
    )

    return engine.execute_triggers(TriggerEvent.CUSTOM, context)


# Health check and monitoring
def get_signal_integration_status() -> Dict[str, Any]:
    """Get status of signal integration"""
    handler = get_signal_handler()
    engine = get_trigger_engine()

    return {
        'signal_handler_enabled': handler.enabled,
        'cache_size': len(handler._instance_cache),
        'engine_status': engine.get_engine_stats(),
        'current_request_available': get_current_request() is not None,
        'current_user_available': get_current_user() is not None
    }