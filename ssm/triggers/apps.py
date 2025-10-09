"""
Django app configuration for the trigger system
"""
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class TriggersConfig(AppConfig):
    """Configuration for the triggers app"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ssm.triggers'
    verbose_name = 'SSM Trigger System'

    def ready(self):
        """Initialize trigger system when Django starts"""
        try:
            # Import trigger modules to register decorators
            self._import_trigger_modules()

            # Initialize trigger system
            self._initialize_trigger_system()

            logger.info("SSM Trigger System initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SSM Trigger System: {e}")

    def _import_trigger_modules(self):
        """Import all trigger modules to ensure decorators are registered"""
        try:
            # Import all model-specific trigger modules
            from . import models
            from .base import signal_integration

            logger.debug("Trigger modules imported successfully")

        except ImportError as e:
            logger.error(f"Failed to import trigger modules: {e}")

    def _initialize_trigger_system(self):
        """Initialize the trigger system components"""
        try:
            # Get global registry and engine
            from .registry.trigger_registry import get_global_registry
            from .base.trigger_engine import TriggerEngine
            from .base.signal_integration import get_trigger_engine, get_signal_handler

            registry = get_global_registry()
            engine = get_trigger_engine()
            signal_handler = get_signal_handler()

            # Log initialization status
            logger.info(f"Trigger registry initialized with {len(registry.triggers)} triggers")
            logger.info(f"Trigger engine initialized (enabled: {engine.enabled})")
            logger.info(f"Signal handler initialized (enabled: {signal_handler.enabled})")


            # Perform health check
            health_status = registry.health_check()
            if not health_status['healthy']:
                logger.warning(f"Trigger system health issues detected: {health_status['issues']}")

        except Exception as e:
            logger.error(f"Failed to initialize trigger system components: {e}")
            raise