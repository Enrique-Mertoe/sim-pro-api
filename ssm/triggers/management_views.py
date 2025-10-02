"""
Trigger management views for Supabase-style API integration
"""
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .base.trigger_engine import TriggerEngine
from .base.signal_integration import get_trigger_engine, get_signal_handler
from .registry.trigger_registry import get_global_registry
from .base.trigger_base import TriggerEvent, TriggerPriority, TriggerContext, TriggerResult

logger = logging.getLogger(__name__)


def require_admin_role(view_func):
    """Decorator to require admin role for trigger management"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        # Check if user has admin role in SSM system
        try:
            from ssm.models import User
            ssm_user = User.objects.get(auth_user=request.user)
            if ssm_user.role != 'admin':
                raise PermissionDenied("Admin role required for trigger management")
        except User.DoesNotExist:
            raise PermissionDenied("User profile not found")

        return view_func(request, *args, **kwargs)
    return wrapper


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@require_admin_role
def get_trigger_registry_status(request):
    """Get trigger registry status and statistics"""
    try:
        registry = get_global_registry()
        engine = get_trigger_engine()
        signal_handler = get_signal_handler()

        status_data = {
            'registry_stats': registry.get_registry_stats(),
            'engine_stats': engine.get_engine_stats(),
            'signal_integration': {
                'enabled': signal_handler.enabled,
                'cache_size': len(signal_handler._instance_cache)
            },
            'health_check': registry.health_check(),
            'timestamp': datetime.now().isoformat()
        }

        return JsonResponse({
            'success': True,
            'data': status_data
        })

    except Exception as e:
        logger.error(f"Error getting trigger registry status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@require_admin_role
def list_triggers(request):
    """List all registered triggers with filtering options"""
    try:
        registry = get_global_registry()

        # Get query parameters for filtering
        enabled_only = request.GET.get('enabled_only', 'false').lower() == 'true'
        model_filter = request.GET.get('model')
        event_filter = request.GET.get('event')
        priority_filter = request.GET.get('priority')

        # Get all triggers
        triggers = registry.get_all_triggers(enabled_only=enabled_only)

        # Apply filters
        if model_filter:
            triggers = [t for t in triggers if registry._get_model_name(t.model) == model_filter.lower()]

        if event_filter:
            try:
                event = TriggerEvent(event_filter)
                triggers = [t for t in triggers if t.event == event]
            except ValueError:
                pass

        if priority_filter:
            try:
                priority = TriggerPriority[priority_filter.upper()]
                triggers = [t for t in triggers if t.priority == priority]
            except (KeyError, AttributeError):
                pass

        # Format trigger data
        trigger_data = []
        for trigger in triggers:
            trigger_info = {
                'id': trigger.id,
                'name': trigger.name,
                'event': trigger.event.value,
                'model': registry._get_model_name(trigger.model),
                'priority': trigger.priority.name,
                'enabled': trigger.enabled,
                'description': trigger.description,
                'conditions_count': len(trigger.conditions),
                'actions_count': len(trigger.actions),
                'execution_stats': {
                    'total_executions': trigger.execution_count,
                    'success_count': trigger.success_count,
                    'failure_count': trigger.failure_count,
                    'success_rate': round((trigger.success_count / trigger.execution_count * 100) if trigger.execution_count > 0 else 0, 2)
                },
                'created_at': trigger.created_at.isoformat(),
                'updated_at': trigger.updated_at.isoformat(),
                'metadata': trigger.metadata
            }
            trigger_data.append(trigger_info)

        # Sort by priority and name
        trigger_data.sort(key=lambda x: (x['priority'], x['name']))

        return JsonResponse({
            'success': True,
            'data': {
                'triggers': trigger_data,
                'total_count': len(trigger_data),
                'filters_applied': {
                    'enabled_only': enabled_only,
                    'model': model_filter,
                    'event': event_filter,
                    'priority': priority_filter
                }
            }
        })

    except Exception as e:
        logger.error(f"Error listing triggers: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@require_admin_role
def get_trigger_details(request, trigger_name):
    """Get detailed information about a specific trigger"""
    try:
        registry = get_global_registry()
        trigger = registry.get_trigger_by_name(trigger_name)

        if not trigger:
            return JsonResponse({
                'success': False,
                'error': f"Trigger '{trigger_name}' not found"
            }, status=404)

        # Get detailed trigger information
        trigger_details = {
            'basic_info': {
                'id': trigger.id,
                'name': trigger.name,
                'event': trigger.event.value,
                'model': registry._get_model_name(trigger.model),
                'priority': trigger.priority.name,
                'enabled': trigger.enabled,
                'description': trigger.description,
                'max_retries': trigger.max_retries,
                'timeout_seconds': trigger.timeout_seconds
            },
            'conditions': [
                {
                    'type': condition.__class__.__name__,
                    'description': condition.description()
                } for condition in trigger.conditions
            ],
            'actions': [
                {
                    'type': action.__class__.__name__,
                    'description': action.description(),
                    'can_retry': getattr(action, 'can_retry', lambda: True)()
                } for action in trigger.actions
            ],
            'execution_stats': trigger.get_stats(),
            'metadata': trigger.metadata,
            'timestamps': {
                'created_at': trigger.created_at.isoformat(),
                'updated_at': trigger.updated_at.isoformat()
            }
        }

        return JsonResponse({
            'success': True,
            'data': trigger_details
        })

    except Exception as e:
        logger.error(f"Error getting trigger details for {trigger_name}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@require_admin_role
def toggle_trigger_status(request, trigger_name):
    """Enable or disable a specific trigger"""
    try:
        registry = get_global_registry()
        trigger = registry.get_trigger_by_name(trigger_name)

        if not trigger:
            return JsonResponse({
                'success': False,
                'error': f"Trigger '{trigger_name}' not found"
            }, status=404)

        # Parse request data
        try:
            data = json.loads(request.body)
            enable = data.get('enable', not trigger.enabled)
        except (json.JSONDecodeError, AttributeError):
            enable = not trigger.enabled

        # Toggle trigger status
        if enable:
            trigger.enable()
            action = 'enabled'
        else:
            trigger.disable()
            action = 'disabled'

        # Log the action
        logger.info(f"Trigger '{trigger_name}' {action} by user {request.user}")

        return JsonResponse({
            'success': True,
            'data': {
                'trigger_name': trigger_name,
                'action': action,
                'enabled': trigger.enabled,
                'timestamp': datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error toggling trigger status for {trigger_name}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@require_admin_role
def execute_trigger_manually(request, trigger_name):
    """Manually execute a specific trigger"""
    try:
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': "Invalid JSON in request body"
            }, status=400)

        # Get required parameters
        model_name = data.get('model')
        instance_id = data.get('instance_id')
        event = data.get('event', 'custom')

        if not model_name or not instance_id:
            return JsonResponse({
                'success': False,
                'error': "model and instance_id are required"
            }, status=400)

        # Get model class
        from django.apps import apps
        try:
            model_class = apps.get_model('ssm', model_name)
            instance = model_class.objects.get(pk=instance_id)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f"Failed to get model instance: {str(e)}"
            }, status=400)

        # Create trigger context
        try:
            trigger_event = TriggerEvent(event)
        except ValueError:
            trigger_event = TriggerEvent.CUSTOM

        from ssm.models import User
        ssm_user = User.objects.get(auth_user=request.user)

        context = TriggerContext(
            event=trigger_event,
            model=model_class,
            instance=instance,
            user=ssm_user,
            request=request,
            metadata=data.get('metadata', {})
        )

        # Execute trigger
        engine = get_trigger_engine()
        results = engine.execute_custom_trigger(trigger_name, context)

        # Format results
        results_data = []
        for result in results:
            result_data = {
                'success': result.success,
                'message': result.message,
                'data': result.data,
                'execution_time': result.execution_time,
                'modified_fields': result.modified_fields
            }
            if result.error:
                result_data['error'] = str(result.error)
            results_data.append(result_data)

        return JsonResponse({
            'success': True,
            'data': {
                'trigger_name': trigger_name,
                'execution_results': results_data,
                'context': {
                    'event': trigger_event.value,
                    'model': model_name,
                    'instance_id': str(instance_id),
                    'executed_by': str(ssm_user)
                },
                'timestamp': datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error executing trigger manually: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@require_admin_role
def toggle_trigger_engine(request):
    """Enable or disable the entire trigger engine"""
    try:
        # Parse request data
        try:
            data = json.loads(request.body)
            enable = data.get('enable')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({
                'success': False,
                'error': "Invalid request data"
            }, status=400)

        engine = get_trigger_engine()
        signal_handler = get_signal_handler()

        if enable:
            engine.enable()
            signal_handler.enable()
            action = 'enabled'
        else:
            engine.disable()
            signal_handler.disable()
            action = 'disabled'

        # Log the action
        logger.info(f"Trigger engine {action} by user {request.user}")

        return JsonResponse({
            'success': True,
            'data': {
                'action': action,
                'engine_enabled': engine.enabled,
                'signal_handler_enabled': signal_handler.enabled,
                'timestamp': datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error toggling trigger engine: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@require_admin_role
def get_trigger_execution_logs(request):
    """Get trigger execution logs and metrics"""
    try:
        # Get query parameters
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))
        trigger_name = request.GET.get('trigger_name')
        model_filter = request.GET.get('model')

        # Get activity logs related to triggers
        from ssm.models import ActivityLog

        logs_query = ActivityLog.objects.filter(
            action_type__in=[
                'trigger_executed',
                'trigger_failed',
                'trigger_enabled',
                'trigger_disabled'
            ]
        ).order_by('-created_at')

        # Apply filters
        if trigger_name:
            logs_query = logs_query.filter(details__trigger_name=trigger_name)

        if model_filter:
            logs_query = logs_query.filter(details__model=model_filter)

        # Get paginated results
        total_count = logs_query.count()
        logs = logs_query[offset:offset + limit]

        # Format log data
        log_data = []
        for log in logs:
            log_info = {
                'id': str(log.id),
                'timestamp': log.created_at.isoformat(),
                'user': str(log.user),
                'action_type': log.action_type,
                'details': log.details,
                'ip_address': log.ip_address
            }
            log_data.append(log_info)

        return JsonResponse({
            'success': True,
            'data': {
                'logs': log_data,
                'pagination': {
                    'total_count': total_count,
                    'offset': offset,
                    'limit': limit,
                    'has_more': offset + limit < total_count
                }
            }
        })

    except Exception as e:
        logger.error(f"Error getting trigger execution logs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@require_admin_role
def clear_trigger_cache(request):
    """Clear trigger-related caches"""
    try:
        engine = get_trigger_engine()
        signal_handler = get_signal_handler()

        # Clear caches
        engine.clear_cache()
        signal_handler.clear_cache()

        # Log the action
        logger.info(f"Trigger caches cleared by user {request.user}")

        return JsonResponse({
            'success': True,
            'data': {
                'message': 'Trigger caches cleared successfully',
                'timestamp': datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error clearing trigger cache: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@require_admin_role
def export_trigger_config(request):
    """Export trigger configuration for backup"""
    try:
        registry = get_global_registry()
        config = registry.export_triggers_config()
        config['metadata']['export_timestamp'] = datetime.now().isoformat()
        config['metadata']['exported_by'] = str(request.user)

        return JsonResponse({
            'success': True,
            'data': config
        })

    except Exception as e:
        logger.error(f"Error exporting trigger config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)