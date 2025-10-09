"""
Advanced Supabase-style select parser for relationship queries
Supports: *, columns, relationships, aliases, nested queries
"""
import re
from typing import Dict, List, Any, Optional, Union
from django.db import models

class SelectField:
    """Represents a parsed select field"""
    def __init__(self, name: str, alias: Optional[str] = None, nested: Optional['SelectQuery'] = None):
        self.name = name
        self.alias = alias or name
        self.nested = nested
        self.is_wildcard = name == '*'

class SelectQuery:
    """Represents a parsed select query with fields and relationships"""
    def __init__(self, fields: List[SelectField]):
        self.fields = fields

    def has_wildcard(self) -> bool:
        return any(field.is_wildcard for field in self.fields)

    def get_direct_fields(self) -> List[str]:
        """Get direct field names (non-relationship)"""
        return [field.name for field in self.fields if not field.nested and not field.is_wildcard]

    def get_relationship_fields(self) -> Dict[str, 'SelectQuery']:
        """Get relationship fields with their nested queries"""
        return {field.name: field.nested for field in self.fields if field.nested}

class SelectParser:
    """Parser for Supabase-style select queries"""

    @staticmethod
    def parse(select_string: str) -> SelectQuery:
        """
        Parse a Supabase-style select string into a SelectQuery

        Examples:
        - '*' -> SelectQuery with wildcard
        - 'id,name,email' -> SelectQuery with direct fields
        - '*, team(*)' -> SelectQuery with wildcard + team relationship
        - 'id,name,team(name,region)' -> SelectQuery with fields + nested team fields
        - 'user:user_id(name,email)' -> SelectQuery with aliased relationship
        """
        if not select_string or select_string.strip() == '':
            select_string = '*'

        fields = SelectParser._parse_fields(select_string)
        return SelectQuery(fields)

    @staticmethod
    def _parse_fields(select_string: str) -> List[SelectField]:
        """Parse comma-separated fields, handling nested parentheses"""
        fields = []
        current_field = ""
        paren_depth = 0

        for char in select_string:
            if char == ',' and paren_depth == 0:
                # End of current field
                if current_field.strip():
                    fields.append(SelectParser._parse_single_field(current_field.strip()))
                current_field = ""
            else:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                current_field += char

        # Add the last field
        if current_field.strip():
            fields.append(SelectParser._parse_single_field(current_field.strip()))

        return fields

    @staticmethod
    def _parse_single_field(field_str: str) -> SelectField:
        """
        Parse a single field which can be:
        - 'name' -> direct field
        - '*' -> wildcard
        - 'team(*)' -> relationship with nested query
        - 'user:user_id(name,email)' -> aliased relationship
        """
        field_str = field_str.strip()

        # Check for alias (alias:field_name)
        alias = None
        if ':' in field_str and '(' not in field_str.split(':')[0]:
            alias, field_str = field_str.split(':', 1)
            alias = alias.strip()
            field_str = field_str.strip()

        # Check for nested query (field_name(...))
        paren_match = re.match(r'^([^(]+)\((.+)\)$', field_str)
        if paren_match:
            field_name = paren_match.group(1).strip()
            nested_query_str = paren_match.group(2).strip()
            nested_query = SelectParser.parse(nested_query_str)
            return SelectField(field_name, alias, nested_query)

        # Simple field or wildcard
        return SelectField(field_str, alias)

class RelationshipResolver:
    """Resolves Django model relationships for select queries"""

    @staticmethod
    def get_model_fields(model: models.Model) -> Dict[str, Any]:
        """Get all field information for a model including reverse relations"""
        fields = {}
        for field in model._meta.get_fields():
            if hasattr(field, 'name'):
                # Detect if it's a reverse relation (OneToMany or ManyToMany from the other side)
                is_reverse = (
                    field.auto_created and
                    field.is_relation and
                    (field.one_to_many or field.many_to_many)
                )

                # For reverse relations, we need to check both the field name and related_name
                field_names = [field.name]
                if hasattr(field, 'related_name') and field.related_name and field.related_name != '+':
                    field_names.append(field.related_name)

                # Add smart pluralization for reverse relations without related_name
                # E.g., user_set -> also allow 'users'
                if is_reverse and field.name.endswith('_set'):
                    base_name = field.name.replace('_set', '')
                    plural_name = RelationshipResolver._pluralize(base_name)
                    if plural_name != base_name:  # Only add if actually pluralized
                        field_names.append(plural_name)

                # Register the field under all its accessible names
                field_info = {
                    'type': type(field).__name__,
                    'is_relation': field.is_relation if hasattr(field, 'is_relation') else False,
                    'is_reverse': is_reverse,
                    'is_many': is_reverse or (hasattr(field, 'many_to_many') and field.many_to_many),
                    'related_model': field.related_model if hasattr(field, 'related_model') else None,
                    'field_obj': field,  # Keep reference to original field
                    'actual_field_name': field.name,  # Store the actual Django field name
                }

                for fname in field_names:
                    fields[fname] = field_info.copy()

        return fields

    @staticmethod
    def resolve_relationship(instance: models.Model, field_name: str, actual_field_name: str = None) -> Any:
        """Resolve a relationship field on a model instance (forward or reverse)"""
        # Use actual_field_name if provided (for pluralized aliases like 'users' -> 'user_set')
        lookup_name = actual_field_name if actual_field_name else field_name

        try:
            # Try to get the field (works for forward relations and direct fields)
            field = instance._meta.get_field(lookup_name)

            if field.is_relation:
                related = getattr(instance, lookup_name)

                # Check if it's a manager (reverse relation or M2M)
                # Managers have 'all()' method
                if hasattr(related, 'all'):
                    return list(related.all())  # Convert queryset to list

                return related  # Single object (forward FK)

            return None

        except Exception:
            # Field doesn't exist as a direct field - try as attribute (for reverse relations)
            # This handles cases where related_name is used
            if hasattr(instance, lookup_name):
                related = getattr(instance, lookup_name)

                # If it's a related manager, get all items
                if hasattr(related, 'all'):
                    return list(related.all())

                return related

            return None

    @staticmethod
    def _pluralize(word: str) -> str:
        """
        Simple English pluralization rules
        Converts singular model names to plural forms
        Examples: user -> users, person -> people, address -> addresses
        """
        # Special cases (irregular plurals)
        irregular = {
            'person': 'people',
            'child': 'children',
            'man': 'men',
            'woman': 'women',
            'tooth': 'teeth',
            'foot': 'feet',
            'mouse': 'mice',
            'goose': 'geese',
        }

        word_lower = word.lower()
        if word_lower in irregular:
            return irregular[word_lower]

        # Words ending in s, x, z, ch, sh -> add 'es'
        if word_lower.endswith(('s', 'x', 'z', 'ch', 'sh')):
            return word + 'es'

        # Words ending in consonant + y -> ies
        if len(word) > 1 and word_lower.endswith('y') and word[-2] not in 'aeiou':
            return word[:-1] + 'ies'

        # Words ending in consonant + o -> oes (with exceptions)
        if len(word) > 1 and word_lower.endswith('o') and word[-2] not in 'aeiou':
            # Common exceptions that just add 's'
            exceptions = ['photo', 'piano', 'halo']
            if word_lower not in exceptions:
                return word + 'es'

        # Words ending in f or fe -> ves
        if word_lower.endswith('f'):
            return word[:-1] + 'ves'
        if word_lower.endswith('fe'):
            return word[:-2] + 'ves'

        # Default: just add 's'
        return word + 's'

    @staticmethod
    def build_select_data(instance: models.Model, select_query: SelectQuery, model_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Build response data based on select query"""
        result = {}

        # Handle wildcard - include all direct fields
        if select_query.has_wildcard():
            for field_name, field_info in model_fields.items():
                if not field_info['is_relation']:
                    result[field_name] = RelationshipResolver._format_field_value(getattr(instance, field_name, None))

        # Handle direct fields (with aliases)
        for field in select_query.fields:
            if not field.nested and not field.is_wildcard:
                if field.name in model_fields:
                    field_value = RelationshipResolver._format_field_value(getattr(instance, field.name, None))
                    result[field.alias] = field_value  # Use alias as key

        # Handle relationship fields (with aliases) - BOTH forward and reverse
        for field in select_query.fields:
            if field.nested:
                if field.name in model_fields and model_fields[field.name]['is_relation']:
                    # Get the actual field name (important for pluralized aliases like 'users' -> 'user_set')
                    actual_field_name = model_fields[field.name].get('actual_field_name')
                    related_data = RelationshipResolver.resolve_relationship(
                        instance,
                        field.name,
                        actual_field_name
                    )

                    if related_data is not None:
                        # Check if it's a many relation (list) - reverse relations or M2M
                        if model_fields[field.name].get('is_many', False) or isinstance(related_data, list):
                            # Reverse relation or M2M - returns list of objects
                            related_model = model_fields[field.name]['related_model']
                            related_model_fields = RelationshipResolver.get_model_fields(related_model)

                            result[field.alias] = [
                                RelationshipResolver.build_select_data(
                                    item,
                                    field.nested,
                                    related_model_fields
                                )
                                for item in related_data
                            ]
                        else:
                            # Forward relation - single object
                            related_model_fields = RelationshipResolver.get_model_fields(related_data)
                            result[field.alias] = RelationshipResolver.build_select_data(
                                related_data, field.nested, related_model_fields
                            )
                    else:
                        # Handle null relations
                        # Return empty list for many relations, None for single relations
                        if model_fields[field.name].get('is_many', False):
                            result[field.alias] = []
                        else:
                            result[field.alias] = None

        return result

    # @staticmethod
    # def _format_field_value(value: Any) -> Any:
    #     """Format field values for JSON serialization"""
    #     if hasattr(value, 'isoformat'):  # datetime objects
    #         return value.isoformat()
    #     elif hasattr(value, '__str__') and not isinstance(value, (str, int, float, bool)):
    #         return str(value)
    #     return value
    @staticmethod
    def _format_field_value(value: Any) -> Any:
        """Format field values for JSON serialization"""
        if value is None:
            return None
        if hasattr(value, 'isoformat'):  # datetime objects
            return value.isoformat()
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)


def build_response_with_select(queryset, select_string: str) -> List[Dict[str, Any]]:
    """
    Build response data using advanced select parsing

    Args:
        queryset: Django queryset
        select_string: Supabase-style select string

    Returns:
        List of dictionaries with selected fields and relationships
    """
    if not queryset:
        return []

    # Parse the select query
    select_query = SelectParser.parse(select_string)

    # Get model information
    model = queryset.model
    model_fields = RelationshipResolver.get_model_fields(model)

    # Build response data
    result = []
    for instance in queryset:
        item_data = RelationshipResolver.build_select_data(instance, select_query, model_fields)
        result.append(item_data)

    return result