"""
RPC (Remote Procedure Call) views for Supabase-compatible API
These views handle dynamic function calls from the SDK
"""
import json
import logging
import traceback

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ssm.supabase_views import serialize_model_instance
from ssm.utilities import get_user_from_token, supabase_response

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def rpc_handler(request, function_name):
    """POST /rest/v1/rpc/{function_name} - Handle RPC function calls"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        # Parse request body
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except json.JSONDecodeError:
            return supabase_response(
                error={'message': 'Invalid JSON in request body'},
                status=400
            )

        # Import RPC functions dynamically
        try:
            from .rpc_functions import functions as rpc_functions
            if function_name not in rpc_functions:
                return supabase_response(
                    error={'message': f'Function "{function_name}" not found'},
                    status=404
                )

            # Call the RPC function with user context and arguments
            result = rpc_functions[function_name](user, **data)

            # Handle different response types
            if hasattr(result, '_meta'):  # Django model instance
                result = serialize_model_instance(result)
            elif hasattr(result, '__iter__') and not isinstance(result, (str, dict)):  # QuerySet or list
                if hasattr(result, 'model'):  # QuerySet
                    result = [serialize_model_instance(item) for item in result]
            return supabase_response(data=result)

        except ImportError:
            return supabase_response(
                error={'message': 'RPC functions not configured'},
                status=500
            )
        except TypeError as e:
            return supabase_response(
                error={'message': f'Invalid arguments for function "{function_name}": {str(e)}'},
                status=400
            )
        except Exception as e:

            logger.error(f'RPC function "{function_name}" error: {e}')
            traceback.print_exc()
            return supabase_response(
                error={'message': f'Function execution error: {str(e)}'},
                status=500
            )

    except Exception as e:
        logger.error(f"RPC handler error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )
