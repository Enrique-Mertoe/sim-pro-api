import json
import logging
import uuid

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ssm.utilities import supabase_response, MODEL_MAP

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def db_select(request):
    """POST /api/db/select"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error={'message': 'Authentication required'},
                status=401
            )

        data = json.loads(request.body)
        table = data.get('table')
        filters = data.get('filters', {})

        if table not in MODEL_MAP:
            return supabase_response(
                error={'message': f'Table {table} not found'},
                status=404
            )

        model = MODEL_MAP[table]
        queryset = model.objects.all()

        # Apply filters
        for key, value in filters.items():
            if hasattr(model, key):
                queryset = queryset.filter(**{key: value})

        # Convert to list of dicts
        results = []
        for obj in queryset:
            obj_dict = {}
            for field in obj._meta.fields:
                field_value = getattr(obj, field.name)
                if hasattr(field_value, 'isoformat'):  # datetime
                    field_value = field_value.isoformat()
                elif isinstance(field_value, uuid.UUID):
                    field_value = str(field_value)
                obj_dict[field.name] = field_value
            results.append(obj_dict)

        return supabase_response(data=results)

    except json.JSONDecodeError:
        return supabase_response(
            error={'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"DB select error: {e}")
        return supabase_response(
            error={'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def db_insert(request):
    """POST /api/db/insert"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                {'message': 'Authentication required'},
                status=401
            )

        data = json.loads(request.body)
        table = data.get('table')
        insert_data = data.get('data')

        if table not in MODEL_MAP:
            return supabase_response(
                {'message': f'Table {table} not found'},
                status=404
            )

        model = MODEL_MAP[table]

        # Handle single record or multiple records
        if isinstance(insert_data, list):
            created_objects = []
            with transaction.atomic():
                for record in insert_data:
                    obj = model.objects.create(**record)
                    created_objects.append(obj)
        else:
            created_objects = [model.objects.create(**insert_data)]

        # Return created objects
        results = []
        for obj in created_objects:
            obj_dict = {}
            for field in obj._meta.fields:
                field_value = getattr(obj, field.name)
                if hasattr(field_value, 'isoformat'):
                    field_value = field_value.isoformat()
                elif isinstance(field_value, uuid.UUID):
                    field_value = str(field_value)
                obj_dict[field.name] = field_value
            results.append(obj_dict)

        return supabase_response(results)

    except json.JSONDecodeError:
        return supabase_response(
            error=
            {'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"DB insert error: {e}")
        return supabase_response(
            error=
            {'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def db_update(request):
    """POST /api/db/update"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error=
                {'message': 'Authentication required'},
                status=401
            )

        data = json.loads(request.body)
        table = data.get('table')
        update_data = data.get('data')
        where = data.get('where', {})

        if table not in MODEL_MAP:
            return supabase_response(
                error=
                {'message': f'Table {table} not found'},
                status=404
            )

        model = MODEL_MAP[table]
        queryset = model.objects.all()

        # Apply where conditions
        for key, value in where.items():
            if hasattr(model, key):
                queryset = queryset.filter(**{key: value})

        # Update records
        updated_count = queryset.update(**update_data)

        # Get updated records
        updated_objects = list(queryset)
        results = []
        for obj in updated_objects:
            obj_dict = {}
            for field in obj._meta.fields:
                field_value = getattr(obj, field.name)
                if hasattr(field_value, 'isoformat'):
                    field_value = field_value.isoformat()
                elif isinstance(field_value, uuid.UUID):
                    field_value = str(field_value)
                obj_dict[field.name] = field_value
            results.append(obj_dict)

        return supabase_response(data={
            'count': updated_count,
            'data': results
        })

    except json.JSONDecodeError:
        return supabase_response(
            error=
            {'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"DB update error: {e}")
        return supabase_response(
            error=
            {'message': str(e)},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def db_delete(request):
    """POST /api/db/delete"""
    try:
        user = get_user_from_token(request)
        if not user:
            return supabase_response(
                error=
                {'message': 'Authentication required'},
                status=401
            )

        data = json.loads(request.body)
        table = data.get('table')
        where = data.get('where', {})

        if table not in MODEL_MAP:
            return supabase_response(
                {'message': f'Table {table} not found'},
                status=404
            )

        model = MODEL_MAP[table]
        queryset = model.objects.all()

        # Apply where conditions
        for key, value in where.items():
            if hasattr(model, key):
                queryset = queryset.filter(**{key: value})

        # Delete records
        deleted_count, _ = queryset.delete()

        return supabase_response({
            'count': deleted_count
        })

    except json.JSONDecodeError:
        return supabase_response(
            error=
            {'message': 'Invalid JSON'},
            status=400
        )
    except Exception as e:
        logger.error(f"DB delete error: {e}")
        return supabase_response(
            error=
            {'message': str(e)},
            status=500
        )