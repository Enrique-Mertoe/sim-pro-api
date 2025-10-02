"""
Trigger decorators for easy trigger creation
"""
from functools import wraps
from typing import Union, List, Callable, Optional
from django.db import models

from .trigger_base import (
    TriggerEvent, TriggerPriority, TriggerCondition,
    FunctionTrigger, TriggerContext, TriggerResult
)
from ..registry.trigger_registry import get_global_registry


def trigger(
    event: TriggerEvent,
    model: Union[models.Model, str],
    name: Optional[str] = None,
    conditions: List[TriggerCondition] = None,
    priority: TriggerPriority = TriggerPriority.NORMAL,
    enabled: bool = True,
    max_retries: int = 3,
    timeout_seconds: int = 30,
    description: str = "",
    auto_register: bool = True
):
    """
    Decorator to create triggers from functions

    Usage:
        @trigger(TriggerEvent.POST_SAVE, 'SimCard')
        def update_inventory(context: TriggerContext) -> TriggerResult:
            # Your trigger logic here
            return TriggerResult(success=True, message="Inventory updated")
    """
    def decorator(func: Callable[[TriggerContext], TriggerResult]):
        trigger_name = name or f"{func.__name__}_{event.value}_{model}"

        function_trigger = FunctionTrigger(
            name=trigger_name,
            event=event,
            model=model,
            function=func,
            conditions=conditions or [],
            priority=priority,
            enabled=enabled,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            description=description or func.__doc__ or ""
        )

        # Add function metadata
        function_trigger.metadata.update({
            'function_name': func.__name__,
            'function_module': func.__module__,
            'decorator_type': 'trigger'
        })

        if auto_register:
            registry = get_global_registry()
            registry.register_trigger(function_trigger)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Attach trigger to function for later access
        wrapper._trigger = function_trigger
        return wrapper

    return decorator


def conditional_trigger(
    event: TriggerEvent,
    model: Union[models.Model, str],
    condition_func: Callable[[TriggerContext], bool],
    name: Optional[str] = None,
    priority: TriggerPriority = TriggerPriority.NORMAL,
    enabled: bool = True,
    max_retries: int = 3,
    timeout_seconds: int = 30,
    description: str = "",
    auto_register: bool = True
):
    """
    Decorator to create conditional triggers

    Usage:
        @conditional_trigger(
            TriggerEvent.POST_SAVE,
            'Shop',
            condition_func=lambda ctx: ctx.instance.status == 'active'
        )
        def notify_shop_activation(context: TriggerContext) -> TriggerResult:
            # Your trigger logic here
            return TriggerResult(success=True, message="Notification sent")
    """

    # Create a simple condition wrapper
    class FunctionCondition(TriggerCondition):
        def __init__(self, func, desc="Custom condition"):
            self.func = func
            self.desc = desc

        def evaluate(self, context: TriggerContext) -> bool:
            return self.func(context)

        def description(self) -> str:
            return self.desc

    condition = FunctionCondition(condition_func, f"Custom condition: {condition_func.__name__}")

    def decorator(func: Callable[[TriggerContext], TriggerResult]):
        trigger_name = name or f"{func.__name__}_{event.value}_{model}_conditional"

        function_trigger = FunctionTrigger(
            name=trigger_name,
            event=event,
            model=model,
            function=func,
            conditions=[condition],
            priority=priority,
            enabled=enabled,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            description=description or func.__doc__ or ""
        )

        # Add function metadata
        function_trigger.metadata.update({
            'function_name': func.__name__,
            'function_module': func.__module__,
            'condition_function': condition_func.__name__,
            'decorator_type': 'conditional_trigger'
        })

        if auto_register:
            registry = get_global_registry()
            registry.register_trigger(function_trigger)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Attach trigger to function for later access
        wrapper._trigger = function_trigger
        return wrapper

    return decorator


def pre_save_trigger(
    model: Union[models.Model, str],
    **kwargs
):
    """Shortcut decorator for pre_save triggers"""
    return trigger(TriggerEvent.PRE_SAVE, model, **kwargs)


def post_save_trigger(
    model: Union[models.Model, str],
    **kwargs
):
    """Shortcut decorator for post_save triggers"""
    return trigger(TriggerEvent.POST_SAVE, model, **kwargs)


def pre_delete_trigger(
    model: Union[models.Model, str],
    **kwargs
):
    """Shortcut decorator for pre_delete triggers"""
    return trigger(TriggerEvent.PRE_DELETE, model, **kwargs)


def post_delete_trigger(
    model: Union[models.Model, str],
    **kwargs
):
    """Shortcut decorator for post_delete triggers"""
    return trigger(TriggerEvent.POST_DELETE, model, **kwargs)


def field_changed_trigger(
    model: Union[models.Model, str],
    field_name: str,
    **kwargs
):
    """
    Trigger that fires when a specific field changes

    Usage:
        @field_changed_trigger('Shop', 'status')
        def handle_shop_status_change(context: TriggerContext) -> TriggerResult:
            # Logic for when shop status changes
            return TriggerResult(success=True)
    """

    def field_changed_condition(context: TriggerContext) -> bool:
        if not context.old_instance or not context.instance:
            return False

        old_value = getattr(context.old_instance, field_name, None)
        new_value = getattr(context.instance, field_name, None)
        return old_value != new_value

    return conditional_trigger(
        TriggerEvent.POST_SAVE,
        model,
        condition_func=field_changed_condition,
        **kwargs
    )


def bulk_operation_trigger(
    model: Union[models.Model, str],
    operation: str = 'create',  # 'create', 'update', 'delete'
    **kwargs
):
    """
    Trigger for bulk operations

    Usage:
        @bulk_operation_trigger('SimCard', 'create')
        def handle_bulk_sim_create(context: TriggerContext) -> TriggerResult:
            # Logic for bulk SIM card creation
            return TriggerResult(success=True)
    """
    event_map = {
        'create': TriggerEvent.POST_BULK_CREATE,
        'update': TriggerEvent.POST_BULK_UPDATE,
        'delete': TriggerEvent.POST_BULK_DELETE
    }

    event = event_map.get(operation, TriggerEvent.POST_BULK_CREATE)
    return trigger(event, model, **kwargs)


# Utility functions for trigger management
def get_trigger_from_function(func) -> Optional[FunctionTrigger]:
    """Get the trigger associated with a decorated function"""
    return getattr(func, '_trigger', None)


def enable_trigger(func):
    """Enable a trigger associated with a function"""
    trigger_obj = get_trigger_from_function(func)
    if trigger_obj:
        trigger_obj.enable()


def disable_trigger(func):
    """Disable a trigger associated with a function"""
    trigger_obj = get_trigger_from_function(func)
    if trigger_obj:
        trigger_obj.disable()