"""
Trigger Registry - Central registry for managing triggers
"""
import logging
from typing import Dict, List, Optional, Union, Any
from collections import defaultdict
from threading import RLock
from django.db import models
from django.core.cache import cache
from django.conf import settings

from ..base.trigger_base import BaseTrigger, TriggerEvent, TriggerPriority

logger = logging.getLogger(__name__)


class TriggerRegistry:
    """Central registry for managing triggers"""

    def __init__(self):
        self.triggers: Dict[str, BaseTrigger] = {}
        self.event_triggers: Dict[TriggerEvent, List[str]] = defaultdict(list)
        self.model_triggers: Dict[str, List[str]] = defaultdict(list)
        self._lock = RLock()
        self.cache_timeout = getattr(settings, 'TRIGGER_CACHE_TIMEOUT', 300)  # 5 minutes

    def register_trigger(self, trigger: BaseTrigger) -> bool:
        """Register a new trigger"""
        with self._lock:
            try:
                if trigger.name in self.triggers:
                    logger.warning(f"Trigger '{trigger.name}' already exists, replacing...")

                self.triggers[trigger.name] = trigger

                # Update event index
                if trigger.name not in self.event_triggers[trigger.event]:
                    self.event_triggers[trigger.event].append(trigger.name)

                # Update model index
                model_name = self._get_model_name(trigger.model)
                if trigger.name not in self.model_triggers[model_name]:
                    self.model_triggers[model_name].append(trigger.name)

                # Clear cache
                self._clear_cache()

                logger.info(f"Registered trigger: {trigger.name}")
                return True

            except Exception as e:
                logger.error(f"Failed to register trigger {trigger.name}: {e}")
                return False

    def unregister_trigger(self, trigger_name: str) -> bool:
        """Unregister a trigger"""
        with self._lock:
            try:
                if trigger_name not in self.triggers:
                    logger.warning(f"Trigger '{trigger_name}' not found for unregistration")
                    return False

                trigger = self.triggers[trigger_name]

                # Remove from main registry
                del self.triggers[trigger_name]

                # Remove from event index
                if trigger_name in self.event_triggers[trigger.event]:
                    self.event_triggers[trigger.event].remove(trigger_name)

                # Remove from model index
                model_name = self._get_model_name(trigger.model)
                if trigger_name in self.model_triggers[model_name]:
                    self.model_triggers[model_name].remove(trigger_name)

                # Clear cache
                self._clear_cache()

                logger.info(f"Unregistered trigger: {trigger_name}")
                return True

            except Exception as e:
                logger.error(f"Failed to unregister trigger {trigger_name}: {e}")
                return False

    def get_trigger_by_name(self, trigger_name: str) -> Optional[BaseTrigger]:
        """Get a trigger by name"""
        return self.triggers.get(trigger_name)

    def get_triggers_for_event(
        self,
        event: TriggerEvent,
        model: Union[models.Model, str, None] = None
    ) -> List[BaseTrigger]:
        """Get all triggers for a specific event and optionally model"""
        cache_key = f"trigger_names_{event.value}_{self._get_model_name(model) if model else 'all'}"

        # Try to get trigger names from cache first
        cached_trigger_names = cache.get(cache_key)

        with self._lock:
            if cached_trigger_names is not None:
                # Retrieve actual trigger objects from memory using cached names
                triggers = []
                for trigger_name in cached_trigger_names:
                    trigger = self.triggers.get(trigger_name)
                    if trigger and trigger.enabled:
                        triggers.append(trigger)
                return triggers

            triggers = []
            trigger_names_to_cache = []

            # Get all triggers for this event
            trigger_names = self.event_triggers.get(event, [])

            for trigger_name in trigger_names:
                trigger = self.triggers.get(trigger_name)
                if not trigger or not trigger.enabled:
                    continue

                # Filter by model if specified
                if model:
                    trigger_model_name = self._get_model_name(trigger.model)
                    request_model_name = self._get_model_name(model)

                    if trigger_model_name != request_model_name:
                        continue

                triggers.append(trigger)
                trigger_names_to_cache.append(trigger_name)

            # Cache only the trigger names, not the trigger objects
            cache.set(cache_key, trigger_names_to_cache, self.cache_timeout)
            return triggers

    def get_triggers_for_model(self, model: Union[models.Model, str]) -> List[BaseTrigger]:
        """Get all triggers for a specific model"""
        model_name = self._get_model_name(model)
        cache_key = f"model_trigger_names_{model_name}"

        # Try to get trigger names from cache first
        cached_trigger_names = cache.get(cache_key)

        with self._lock:
            if cached_trigger_names is not None:
                # Retrieve actual trigger objects from memory using cached names
                triggers = []
                for trigger_name in cached_trigger_names:
                    trigger = self.triggers.get(trigger_name)
                    if trigger and trigger.enabled:
                        triggers.append(trigger)
                return triggers

            triggers = []
            trigger_names_to_cache = []
            trigger_names = self.model_triggers.get(model_name, [])

            for trigger_name in trigger_names:
                trigger = self.triggers.get(trigger_name)
                if trigger and trigger.enabled:
                    triggers.append(trigger)
                    trigger_names_to_cache.append(trigger_name)

            # Cache only the trigger names, not the trigger objects
            cache.set(cache_key, trigger_names_to_cache, self.cache_timeout)
            return triggers

    def get_all_triggers(self, enabled_only: bool = False) -> List[BaseTrigger]:
        """Get all triggers"""
        with self._lock:
            if enabled_only:
                return [trigger for trigger in self.triggers.values() if trigger.enabled]
            return list(self.triggers.values())

    def enable_trigger(self, trigger_name: str) -> bool:
        """Enable a specific trigger"""
        trigger = self.get_trigger_by_name(trigger_name)
        if trigger:
            trigger.enable()
            self._clear_cache()
            logger.info(f"Enabled trigger: {trigger_name}")
            return True
        return False

    def disable_trigger(self, trigger_name: str) -> bool:
        """Disable a specific trigger"""
        trigger = self.get_trigger_by_name(trigger_name)
        if trigger:
            trigger.disable()
            self._clear_cache()
            logger.info(f"Disabled trigger: {trigger_name}")
            return True
        return False

    def enable_all_triggers(self):
        """Enable all triggers"""
        with self._lock:
            for trigger in self.triggers.values():
                trigger.enable()
            self._clear_cache()
            logger.info("Enabled all triggers")

    def disable_all_triggers(self):
        """Disable all triggers"""
        with self._lock:
            for trigger in self.triggers.values():
                trigger.disable()
            self._clear_cache()
            logger.info("Disabled all triggers")

    def clear_registry(self):
        """Clear all triggers from registry"""
        with self._lock:
            self.triggers.clear()
            self.event_triggers.clear()
            self.model_triggers.clear()
            self._clear_cache()
            logger.info("Cleared trigger registry")

    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        with self._lock:
            total_triggers = len(self.triggers)
            enabled_triggers = len([t for t in self.triggers.values() if t.enabled])
            disabled_triggers = total_triggers - enabled_triggers

            # Count by event type
            event_counts = {}
            for event, trigger_names in self.event_triggers.items():
                event_counts[event.value] = len(trigger_names)

            # Count by model
            model_counts = {}
            for model_name, trigger_names in self.model_triggers.items():
                model_counts[model_name] = len(trigger_names)

            # Count by priority
            priority_counts = defaultdict(int)
            for trigger in self.triggers.values():
                priority_counts[trigger.priority.name] += 1

            return {
                'total_triggers': total_triggers,
                'enabled_triggers': enabled_triggers,
                'disabled_triggers': disabled_triggers,
                'events': event_counts,
                'models': model_counts,
                'priorities': dict(priority_counts)
            }

    def export_triggers_config(self) -> Dict[str, Any]:
        """Export trigger configuration for backup/restore"""
        with self._lock:
            config = {
                'triggers': [],
                'metadata': {
                    'total_count': len(self.triggers),
                    'export_timestamp': None  # Will be set by caller
                }
            }

            for trigger in self.triggers.values():
                trigger_config = {
                    'name': trigger.name,
                    'event': trigger.event.value,
                    'model': self._get_model_name(trigger.model),
                    'priority': trigger.priority.name,
                    'enabled': trigger.enabled,
                    'max_retries': trigger.max_retries,
                    'timeout_seconds': trigger.timeout_seconds,
                    'description': trigger.description,
                    'metadata': trigger.metadata,
                    'stats': trigger.get_stats()
                }
                config['triggers'].append(trigger_config)

            return config

    def validate_trigger(self, trigger: BaseTrigger) -> List[str]:
        """Validate a trigger configuration"""
        errors = []

        # Check required fields
        if not trigger.name:
            errors.append("Trigger name is required")

        if not trigger.event:
            errors.append("Trigger event is required")

        if not trigger.model:
            errors.append("Trigger model is required")

        # Check for name conflicts
        if trigger.name in self.triggers and self.triggers[trigger.name] != trigger:
            errors.append(f"Trigger name '{trigger.name}' already exists")

        # Validate timeout
        if trigger.timeout_seconds <= 0:
            errors.append("Timeout seconds must be positive")

        # Validate max retries
        if trigger.max_retries < 0:
            errors.append("Max retries cannot be negative")

        return errors

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on trigger registry"""
        with self._lock:
            healthy = True
            issues = []

            # Check for duplicate names
            if len(self.triggers) != len(set(self.triggers.keys())):
                healthy = False
                issues.append("Duplicate trigger names detected")

            # Check for orphaned triggers in indexes
            all_indexed_triggers = set()
            for trigger_names in self.event_triggers.values():
                all_indexed_triggers.update(trigger_names)
            for trigger_names in self.model_triggers.values():
                all_indexed_triggers.update(trigger_names)

            registered_triggers = set(self.triggers.keys())
            orphaned = all_indexed_triggers - registered_triggers
            if orphaned:
                healthy = False
                issues.append(f"Orphaned triggers in indexes: {orphaned}")

            # Check trigger health
            unhealthy_triggers = []
            for trigger in self.triggers.values():
                if hasattr(trigger, 'failure_count') and trigger.failure_count > trigger.success_count:
                    unhealthy_triggers.append(trigger.name)

            if unhealthy_triggers:
                issues.append(f"Triggers with high failure rate: {unhealthy_triggers}")

            return {
                'healthy': healthy,
                'issues': issues,
                'stats': self.get_registry_stats()
            }

    def _get_model_name(self, model: Union[models.Model, str, None]) -> str:
        """Get model name from model class or string"""
        if model is None:
            return 'unknown'
        if isinstance(model, str):
            return model.lower()
        if hasattr(model, '__name__'):
            return model.__name__.lower()
        if hasattr(model, '_meta'):
            return model._meta.model_name
        return str(model).lower()

    def _clear_cache(self):
        """Clear trigger-related cache"""
        # Clear all trigger-related cache keys
        cache_patterns = [
            'triggers_*',
            'model_triggers_*',
            'trigger_registry_*'
        ]
        # Note: Django's cache doesn't support pattern deletion by default
        # This would need to be implemented based on your cache backend
        pass


# Global registry instance
_global_registry = None


def get_global_registry() -> TriggerRegistry:
    """Get the global trigger registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = TriggerRegistry()
    return _global_registry


def reset_global_registry():
    """Reset the global registry (mainly for testing)"""
    global _global_registry
    _global_registry = TriggerRegistry()