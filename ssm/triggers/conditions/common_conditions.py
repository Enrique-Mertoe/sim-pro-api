"""
Common trigger conditions for SSM models
"""
from typing import Any, List, Dict, Union
from django.db import models

from ..base.trigger_base import TriggerCondition, TriggerContext


class FieldValueCondition(TriggerCondition):
    """Condition that checks if a field has a specific value"""

    def __init__(self, field_name: str, value: Any, operator: str = 'eq'):
        self.field_name = field_name
        self.value = value
        self.operator = operator

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance:
            return False

        field_value = getattr(context.instance, self.field_name, None)

        if self.operator == 'eq':
            return field_value == self.value
        elif self.operator == 'ne':
            return field_value != self.value
        elif self.operator == 'gt':
            return field_value > self.value
        elif self.operator == 'gte':
            return field_value >= self.value
        elif self.operator == 'lt':
            return field_value < self.value
        elif self.operator == 'lte':
            return field_value <= self.value
        elif self.operator == 'in':
            return field_value in self.value
        elif self.operator == 'not_in':
            return field_value not in self.value
        elif self.operator == 'contains':
            return self.value in str(field_value)
        elif self.operator == 'startswith':
            return str(field_value).startswith(str(self.value))
        elif self.operator == 'endswith':
            return str(field_value).endswith(str(self.value))

        return False

    def description(self) -> str:
        return f"Field '{self.field_name}' {self.operator} '{self.value}'"


class FieldChangedCondition(TriggerCondition):
    """Condition that checks if a field has changed"""

    def __init__(self, field_name: str, from_value: Any = None, to_value: Any = None):
        self.field_name = field_name
        self.from_value = from_value
        self.to_value = to_value

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance or not context.old_instance:
            return False

        old_value = getattr(context.old_instance, self.field_name, None)
        new_value = getattr(context.instance, self.field_name, None)

        # Check if field changed
        if old_value == new_value:
            return False

        # Check specific from/to values if specified
        if self.from_value is not None and old_value != self.from_value:
            return False

        if self.to_value is not None and new_value != self.to_value:
            return False

        return True

    def description(self) -> str:
        desc = f"Field '{self.field_name}' changed"
        if self.from_value is not None:
            desc += f" from '{self.from_value}'"
        if self.to_value is not None:
            desc += f" to '{self.to_value}'"
        return desc


class MultipleFieldsChangedCondition(TriggerCondition):
    """Condition that checks if multiple fields have changed"""

    def __init__(self, field_names: List[str], require_all: bool = True):
        self.field_names = field_names
        self.require_all = require_all

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance or not context.old_instance:
            return False

        changed_fields = []
        for field_name in self.field_names:
            old_value = getattr(context.old_instance, field_name, None)
            new_value = getattr(context.instance, field_name, None)

            if old_value != new_value:
                changed_fields.append(field_name)

        if self.require_all:
            return len(changed_fields) == len(self.field_names)
        else:
            return len(changed_fields) > 0

    def description(self) -> str:
        fields_str = ", ".join(self.field_names)
        condition = "all" if self.require_all else "any"
        return f"{condition.capitalize()} of fields [{fields_str}] changed"


class RelatedObjectCondition(TriggerCondition):
    """Condition that checks properties of related objects"""

    def __init__(self, relation_field: str, condition_field: str, value: Any, operator: str = 'eq'):
        self.relation_field = relation_field
        self.condition_field = condition_field
        self.value = value
        self.operator = operator

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance:
            return False

        try:
            related_obj = getattr(context.instance, self.relation_field, None)
            if not related_obj:
                return False

            field_value = getattr(related_obj, self.condition_field, None)

            if self.operator == 'eq':
                return field_value == self.value
            elif self.operator == 'ne':
                return field_value != self.value
            elif self.operator == 'gt':
                return field_value > self.value
            elif self.operator == 'gte':
                return field_value >= self.value
            elif self.operator == 'lt':
                return field_value < self.value
            elif self.operator == 'lte':
                return field_value <= self.value
            elif self.operator == 'in':
                return field_value in self.value

        except Exception:
            return False

        return False

    def description(self) -> str:
        return f"Related {self.relation_field}.{self.condition_field} {self.operator} '{self.value}'"


class UserRoleCondition(TriggerCondition):
    """Condition that checks the user's role"""

    def __init__(self, required_roles: Union[str, List[str]]):
        if isinstance(required_roles, str):
            self.required_roles = [required_roles]
        else:
            self.required_roles = required_roles

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.user:
            return False

        # Assuming user has a role attribute or related User model
        user_role = None
        if hasattr(context.user, 'role'):
            user_role = context.user.role
        elif hasattr(context.user, 'user') and hasattr(context.user.user, 'role'):
            user_role = context.user.user.role

        return user_role in self.required_roles

    def description(self) -> str:
        roles_str = ", ".join(self.required_roles)
        return f"User role in [{roles_str}]"


class TimeBasedCondition(TriggerCondition):
    """Condition that checks time-based criteria"""

    def __init__(self, condition_type: str, value: Any):
        self.condition_type = condition_type  # 'business_hours', 'weekend', 'after_hour'
        self.value = value

    def evaluate(self, context: TriggerContext) -> bool:
        from datetime import datetime, time
        now = datetime.now()

        if self.condition_type == 'business_hours':
            # Assuming business hours are 9 AM to 5 PM
            business_start = time(9, 0)
            business_end = time(17, 0)
            return business_start <= now.time() <= business_end

        elif self.condition_type == 'weekend':
            return now.weekday() >= 5  # Saturday and Sunday

        elif self.condition_type == 'after_hour':
            hour_threshold = time(self.value, 0) if isinstance(self.value, int) else self.value
            return now.time() >= hour_threshold

        return False

    def description(self) -> str:
        return f"Time-based condition: {self.condition_type}"


class QuantityThresholdCondition(TriggerCondition):
    """Condition for quantity/count thresholds"""

    def __init__(self, field_name: str, threshold: int, operator: str = 'gte'):
        self.field_name = field_name
        self.threshold = threshold
        self.operator = operator

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance:
            return False

        value = getattr(context.instance, self.field_name, 0)

        if self.operator == 'gt':
            return value > self.threshold
        elif self.operator == 'gte':
            return value >= self.threshold
        elif self.operator == 'lt':
            return value < self.threshold
        elif self.operator == 'lte':
            return value <= self.threshold
        elif self.operator == 'eq':
            return value == self.threshold

        return False

    def description(self) -> str:
        return f"Field '{self.field_name}' {self.operator} {self.threshold}"


class StatusTransitionCondition(TriggerCondition):
    """Condition for specific status transitions"""

    def __init__(self, status_field: str = 'status', transitions: Dict[str, List[str]] = None):
        self.status_field = status_field
        self.transitions = transitions or {}

    def evaluate(self, context: TriggerContext) -> bool:
        if not context.instance or not context.old_instance:
            return False

        old_status = getattr(context.old_instance, self.status_field, None)
        new_status = getattr(context.instance, self.status_field, None)

        if old_status == new_status:
            return False

        # Check if this is a valid transition
        if old_status in self.transitions:
            return new_status in self.transitions[old_status]

        return True  # Allow any transition if not specified

    def description(self) -> str:
        return f"Status transition on field '{self.status_field}'"


class ValidationCondition(TriggerCondition):
    """Condition that runs custom validation logic"""

    def __init__(self, validation_func: callable, description_text: str = "Custom validation"):
        self.validation_func = validation_func
        self.description_text = description_text

    def evaluate(self, context: TriggerContext) -> bool:
        try:
            return self.validation_func(context)
        except Exception:
            return False

    def description(self) -> str:
        return self.description_text


# Convenience functions for creating common conditions
def field_equals(field_name: str, value: Any) -> FieldValueCondition:
    return FieldValueCondition(field_name, value, 'eq')


def field_changed(field_name: str, from_value: Any = None, to_value: Any = None) -> FieldChangedCondition:
    return FieldChangedCondition(field_name, from_value, to_value)


def user_has_role(roles: Union[str, List[str]]) -> UserRoleCondition:
    return UserRoleCondition(roles)


def quantity_above(field_name: str, threshold: int) -> QuantityThresholdCondition:
    return QuantityThresholdCondition(field_name, threshold, 'gt')


def quantity_below(field_name: str, threshold: int) -> QuantityThresholdCondition:
    return QuantityThresholdCondition(field_name, threshold, 'lt')


def status_changed_to(status_field: str, target_status: str) -> FieldChangedCondition:
    return FieldChangedCondition(status_field, to_value=target_status)


def during_business_hours() -> TimeBasedCondition:
    return TimeBasedCondition('business_hours', None)