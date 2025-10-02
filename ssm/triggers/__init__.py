"""
SSM Trigger Framework

A sophisticated trigger system for Django models that provides:
- Pre/Post operation triggers
- Conditional execution
- Action chaining
- Event logging
- Performance monitoring
- Integration with existing Supabase-style API
"""

from .registry.trigger_registry import TriggerRegistry, get_global_registry
from .base.trigger_engine import TriggerEngine
from .base.trigger_decorator import trigger, conditional_trigger, field_changed_trigger
from .base.signal_integration import get_trigger_engine, get_signal_handler
from .initialize import (
    initialize_trigger_system,
    get_system_status,
    list_all_triggers,
    get_trigger_performance_metrics
)

# Initialize global trigger registry
trigger_registry = get_global_registry()
trigger_engine = get_trigger_engine()

# Expose main interfaces
__all__ = [
    'trigger_registry',
    'trigger_engine',
    'trigger',
    'conditional_trigger',
    'field_changed_trigger',
    'get_trigger_engine',
    'get_signal_handler',
    'initialize_trigger_system',
    'get_system_status',
    'list_all_triggers',
    'get_trigger_performance_metrics',
]