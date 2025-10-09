"""
Base classes for the trigger system
"""
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, Generic
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from django.db import models

logger = logging.getLogger(__name__)


class TriggerEvent(Enum):
    """Trigger event types"""
    PRE_SAVE = "pre_save"
    POST_SAVE = "post_save"
    PRE_DELETE = "pre_delete"
    POST_DELETE = "post_delete"
    PRE_BULK_CREATE = "pre_bulk_create"
    POST_BULK_CREATE = "post_bulk_create"
    PRE_BULK_UPDATE = "pre_bulk_update"
    POST_BULK_UPDATE = "post_bulk_update"
    PRE_BULK_DELETE = "pre_bulk_delete"
    POST_BULK_DELETE = "post_bulk_delete"
    CUSTOM = "custom"


class TriggerPriority(Enum):
    """Trigger execution priority"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class TriggerStatus(Enum):
    """Trigger execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


TModel = TypeVar('TModel', bound=models.Model)

@dataclass
class TriggerContext(Generic[TModel]):
    """Context object passed to trigger functions"""
    event: TriggerEvent
    model: type[TModel]
    instance: Optional[TModel] = None
    old_instance: Optional[TModel] = None
    user: Optional[Any] = None
    request: Optional[Any] = None
    created: Optional[bool] = None
    raw: bool = False
    using: Optional[str] = None
    update_fields: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    def get_field_changes(self) -> Dict[str, Dict[str, Any]]:
        """Get changed fields between old and new instance"""
        if not self.instance or not self.old_instance:
            return {}

        changes = {}
        for field in self.model._meta.fields:
            field_name = field.name
            old_value = getattr(self.old_instance, field_name, None)
            new_value = getattr(self.instance, field_name, None)

            if old_value != new_value:
                changes[field_name] = {
                    'old': old_value,
                    'new': new_value,
                    'field_type': field.__class__.__name__
                }

        return changes


@dataclass
class TriggerResult:
    """Result of trigger execution"""
    success: bool
    message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    execution_time: Optional[float] = None
    error: Optional[Exception] = None
    modified_fields: List[str] = field(default_factory=list)

    def __bool__(self):
        return self.success


class TriggerCondition(ABC):
    """Base class for trigger conditions"""

    @abstractmethod
    def evaluate(self, context: TriggerContext) -> bool:
        """Evaluate if the condition is met"""
        pass

    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the condition"""
        pass


class TriggerAction(ABC):
    """Base class for trigger actions"""

    @abstractmethod
    def execute(self, context: TriggerContext) -> TriggerResult:
        """Execute the trigger action"""
        pass

    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the action"""
        pass

    def can_retry(self) -> bool:
        """Whether this action can be retried on failure"""
        return True

    def get_retry_delay(self, attempt: int) -> int:
        """Get delay in seconds before retry (exponential backoff)"""
        return min(2 ** attempt, 300)  # Max 5 minutes


class BaseTrigger:
    """Base trigger class"""

    def __init__(
            self,
            name: str,
            event: TriggerEvent,
            model: Union[models.Model, str],
            conditions: List[TriggerCondition] = None,
            actions: List[TriggerAction] = None,
            priority: TriggerPriority = TriggerPriority.NORMAL,
            enabled: bool = True,
            max_retries: int = 3,
            timeout_seconds: int = 30,
            description: str = "",
            metadata: Dict[str, Any] = None
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.event = event
        self.model = model
        self.conditions = conditions or []
        self.actions = actions or []
        self.priority = priority
        self.enabled = enabled
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.description = description
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0

    def should_execute(self, context: TriggerContext) -> bool:
        """Check if trigger should execute based on conditions"""
        if not self.enabled:
            return False

        # Check if model matches
        if isinstance(self.model, str):
            if context.model.__name__.lower() != self.model.lower():
                return False
        else:
            if not isinstance(context.instance, self.model):
                return False

        # Check if event matches
        if self.event != context.event:
            return False

        # Evaluate all conditions
        for condition in self.conditions:
            try:
                if not condition.evaluate(context):
                    return False
            except Exception as e:
                logger.error(f"Error evaluating condition in trigger {self.name}: {e}")
                return False

        return True

    def execute(self, context: TriggerContext) -> List[TriggerResult]:
        """Execute all trigger actions"""
        if not self.should_execute(context):
            return [TriggerResult(success=True, message="Trigger conditions not met")]

        results = []
        self.execution_count += 1

        for action in self.actions:
            try:
                start_time = datetime.now()
                result = action.execute(context)
                execution_time = (datetime.now() - start_time).total_seconds()
                result.execution_time = execution_time

                if result.success:
                    self.success_count += 1
                else:
                    self.failure_count += 1

                results.append(result)

                # If action failed and is critical, stop execution
                if not result.success and self.priority == TriggerPriority.CRITICAL:
                    break

            except Exception as e:
                logger.error(f"Error executing action in trigger {self.name}: {e}")
                self.failure_count += 1
                results.append(TriggerResult(
                    success=False,
                    message=f"Action execution failed: {str(e)}",
                    error=e
                ))

        self.updated_at = datetime.now()
        return results

    def add_condition(self, condition: TriggerCondition):
        """Add a condition to the trigger"""
        self.conditions.append(condition)
        self.updated_at = datetime.now()

    def add_action(self, action: TriggerAction):
        """Add an action to the trigger"""
        self.actions.append(action)
        self.updated_at = datetime.now()

    def enable(self):
        """Enable the trigger"""
        self.enabled = True
        self.updated_at = datetime.now()

    def disable(self):
        """Disable the trigger"""
        self.enabled = False
        self.updated_at = datetime.now()

    def get_stats(self) -> Dict[str, Any]:
        """Get trigger execution statistics"""
        total_executions = self.execution_count
        success_rate = (self.success_count / total_executions * 100) if total_executions > 0 else 0

        return {
            'id': self.id,
            'name': self.name,
            'enabled': self.enabled,
            'total_executions': total_executions,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': round(success_rate, 2),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'conditions_count': len(self.conditions),
            'actions_count': len(self.actions),
            'priority': self.priority.name,
            'event': self.event.value,
            'model': self.model.__name__ if hasattr(self.model, '__name__') else str(self.model)
        }

    def __str__(self):
        return f"Trigger({self.name}, {self.event.value}, {self.model})"

    def __repr__(self):
        return (f"BaseTrigger(name='{self.name}', event={self.event}, "
                f"model={self.model}, enabled={self.enabled})")


class FunctionTrigger(BaseTrigger):
    """Trigger that executes a simple function"""

    def __init__(
            self,
            name: str,
            event: TriggerEvent,
            model: Union[models.Model, str],
            function: Callable[[TriggerContext], TriggerResult],
            conditions: List[TriggerCondition] = None,
            **kwargs
    ):
        super().__init__(name, event, model, conditions, **kwargs)
        self.function = function

    def execute(self, context: TriggerContext) -> List[TriggerResult]:
        """Execute the function"""
        if not self.should_execute(context):
            return [TriggerResult(success=True, message="Trigger conditions not met")]

        try:
            self.execution_count += 1
            start_time = datetime.now()
            result = self.function(context)
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time

            if result.success:
                self.success_count += 1
            else:
                self.failure_count += 1

            self.updated_at = datetime.now()
            return [result]

        except Exception as e:
            logger.error(f"Error executing function trigger {self.name}: {e}")
            self.failure_count += 1
            return [TriggerResult(
                success=False,
                message=f"Function execution failed: {str(e)}",
                error=e
            )]
