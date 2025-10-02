"""
Trigger system initialization module
"""
import logging
from typing import Dict, Any

from .registry.trigger_registry import get_global_registry
from .base.trigger_engine import TriggerEngine
from .base.signal_integration import get_trigger_engine, get_signal_handler

logger = logging.getLogger(__name__)


def initialize_trigger_system() -> Dict[str, Any]:
    """
    Initialize the complete trigger system

    Returns:
        Dict containing initialization status and statistics
    """
    initialization_results = {
        'success': False,
        'errors': [],
        'warnings': [],
        'statistics': {},
        'components_initialized': []
    }

    try:
        # 1. Initialize registry
        registry = get_global_registry()
        initialization_results['components_initialized'].append('registry')
        logger.info("Trigger registry initialized")

        # 2. Initialize engine
        engine = get_trigger_engine()
        initialization_results['components_initialized'].append('engine')
        logger.info("Trigger engine initialized")

        # 3. Initialize signal handler
        signal_handler = get_signal_handler()
        initialization_results['components_initialized'].append('signal_handler')
        logger.info("Signal handler initialized")

        # 4. Import and register all triggers
        _import_all_triggers()
        initialization_results['components_initialized'].append('triggers_imported')
        logger.info("All trigger modules imported")

        # 5. Validate system health
        health_check = registry.health_check()
        if not health_check['healthy']:
            initialization_results['warnings'].extend(health_check['issues'])

        # 6. Collect statistics
        initialization_results['statistics'] = {
            'registry': registry.get_registry_stats(),
            'engine': engine.get_engine_stats(),
            'signal_handler': {
                'enabled': signal_handler.enabled,
                'cache_size': len(signal_handler._instance_cache)
            },
            'health': health_check
        }

        initialization_results['success'] = True
        logger.info("Trigger system initialization completed successfully")

    except Exception as e:
        error_msg = f"Trigger system initialization failed: {str(e)}"
        initialization_results['errors'].append(error_msg)
        logger.error(error_msg, exc_info=True)

    return initialization_results


def _import_all_triggers():
    """Import all trigger modules to ensure decorators are registered"""
    trigger_modules = [
        'ssm.triggers.models.sim_card_triggers',
        'ssm.triggers.models.shop_triggers',
    ]

    for module_name in trigger_modules:
        try:
            __import__(module_name)
            logger.debug(f"Imported trigger module: {module_name}")
        except ImportError as e:
            logger.error(f"Failed to import trigger module {module_name}: {e}")
            raise


def create_default_triggers():
    """Create additional programmatic triggers that aren't decorator-based"""
    from .base.trigger_base import BaseTrigger, TriggerEvent, TriggerPriority
    from .conditions.common_conditions import field_changed, user_has_role
    from .actions.common_actions import create_audit_log, send_notification

    registry = get_global_registry()

    # System-level triggers for critical operations
    system_triggers = [
        {
            'name': 'critical_data_change_audit',
            'event': TriggerEvent.POST_SAVE,
            'model': 'User',
            'conditions': [user_has_role(['admin'])],
            'actions': [create_audit_log('admin_data_change')],
            'priority': TriggerPriority.CRITICAL,
            'description': 'Audit all changes made by admin users'
        },
        {
            'name': 'system_notification_handler',
            'event': TriggerEvent.CUSTOM,
            'model': 'Config',
            'actions': [send_notification('System Update', 'System configuration has been updated')],
            'priority': TriggerPriority.HIGH,
            'description': 'Handle system-wide notifications'
        }
    ]

    for trigger_config in system_triggers:
        try:
            trigger = BaseTrigger(**trigger_config)
            registry.register_trigger(trigger)
            logger.info(f"Created default trigger: {trigger.name}")
        except Exception as e:
            logger.error(f"Failed to create default trigger {trigger_config['name']}: {e}")


def get_system_status() -> Dict[str, Any]:
    """Get comprehensive system status"""
    try:
        registry = get_global_registry()
        engine = get_trigger_engine()
        signal_handler = get_signal_handler()

        return {
            'system_healthy': True,
            'registry_status': registry.health_check(),
            'engine_status': engine.get_engine_stats(),
            'signal_handler_status': {
                'enabled': signal_handler.enabled,
                'cache_size': len(signal_handler._instance_cache)
            },
            'total_triggers': len(registry.triggers),
            'enabled_triggers': len([t for t in registry.triggers.values() if t.enabled]),
            'trigger_statistics': registry.get_registry_stats()
        }

    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {
            'system_healthy': False,
            'error': str(e)
        }


def shutdown_trigger_system():
    """Gracefully shutdown the trigger system"""
    try:
        engine = get_trigger_engine()
        signal_handler = get_signal_handler()

        # Disable components
        engine.disable()
        signal_handler.disable()

        # Shutdown engine
        engine.shutdown()

        # Clear caches
        signal_handler.clear_cache()

        logger.info("Trigger system shutdown completed")

    except Exception as e:
        logger.error(f"Error during trigger system shutdown: {e}")


def reset_trigger_system():
    """Reset the trigger system (mainly for testing)"""
    try:
        from .registry.trigger_registry import reset_global_registry

        # Reset registry
        reset_global_registry()

        # Re-initialize
        return initialize_trigger_system()

    except Exception as e:
        logger.error(f"Error resetting trigger system: {e}")
        return {'success': False, 'error': str(e)}


# Utility functions for monitoring and debugging
def list_all_triggers() -> Dict[str, Any]:
    """List all registered triggers with detailed information"""
    registry = get_global_registry()
    triggers_info = []

    for trigger in registry.get_all_triggers():
        trigger_info = {
            'name': trigger.name,
            'event': trigger.event.value,
            'model': registry._get_model_name(trigger.model),
            'enabled': trigger.enabled,
            'priority': trigger.priority.name,
            'conditions_count': len(trigger.conditions),
            'actions_count': len(trigger.actions),
            'execution_stats': trigger.get_stats(),
            'description': trigger.description
        }
        triggers_info.append(trigger_info)

    return {
        'total_triggers': len(triggers_info),
        'triggers': sorted(triggers_info, key=lambda x: (x['priority'], x['name']))
    }


def get_trigger_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics for all triggers"""
    registry = get_global_registry()
    engine = get_trigger_engine()

    total_executions = sum(t.execution_count for t in registry.triggers.values())
    total_successes = sum(t.success_count for t in registry.triggers.values())
    total_failures = sum(t.failure_count for t in registry.triggers.values())

    performance_metrics = {
        'overall_stats': {
            'total_executions': total_executions,
            'total_successes': total_successes,
            'total_failures': total_failures,
            'overall_success_rate': round((total_successes / total_executions * 100) if total_executions > 0 else 0, 2)
        },
        'engine_metrics': engine.metrics.to_dict(),
        'top_performers': [],
        'underperformers': []
    }

    # Identify top performers and underperformers
    for trigger in registry.triggers.values():
        if trigger.execution_count > 0:
            success_rate = (trigger.success_count / trigger.execution_count) * 100

            trigger_perf = {
                'name': trigger.name,
                'success_rate': round(success_rate, 2),
                'execution_count': trigger.execution_count,
                'avg_execution_time': getattr(trigger, 'avg_execution_time', 0)
            }

            if success_rate >= 95 and trigger.execution_count >= 10:
                performance_metrics['top_performers'].append(trigger_perf)
            elif success_rate < 80:
                performance_metrics['underperformers'].append(trigger_perf)

    # Sort by performance
    performance_metrics['top_performers'].sort(key=lambda x: x['success_rate'], reverse=True)
    performance_metrics['underperformers'].sort(key=lambda x: x['success_rate'])

    return performance_metrics