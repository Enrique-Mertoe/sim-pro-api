"""
Trigger Engine - Core execution engine for the trigger system
"""
import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from django.db import transaction
from django.core.cache import cache
from django.conf import settings

from .trigger_base import (
    BaseTrigger, TriggerContext, TriggerResult, TriggerEvent,
    TriggerStatus, TriggerPriority
)

logger = logging.getLogger(__name__)


class TriggerExecutionMetrics:
    """Metrics for trigger execution monitoring"""

    def __init__(self):
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.average_execution_time = 0.0
        self.peak_execution_time = 0.0
        self.last_execution = None

    def record_execution(self, success: bool, execution_time: float):
        """Record execution metrics"""
        self.total_executions += 1

        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

        # Update execution time metrics
        self.average_execution_time = (
            (self.average_execution_time * (self.total_executions - 1) + execution_time) /
            self.total_executions
        )

        if execution_time > self.peak_execution_time:
            self.peak_execution_time = execution_time

        self.last_execution = time.time()

    def get_success_rate(self) -> float:
        """Get success rate percentage"""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'success_rate': round(self.get_success_rate(), 2),
            'average_execution_time': round(self.average_execution_time, 4),
            'peak_execution_time': round(self.peak_execution_time, 4),
            'last_execution': self.last_execution
        }


class TriggerEngine:
    """Core trigger execution engine"""

    def __init__(self, trigger_registry, max_workers: int = 10):
        self.trigger_registry = trigger_registry
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.metrics = TriggerExecutionMetrics()
        self.enabled = True
        self.debug_mode = getattr(settings, 'TRIGGER_DEBUG', False)

    def execute_triggers(
        self,
        event: TriggerEvent,
        context: TriggerContext,
        async_execution: bool = False
    ) -> List[TriggerResult]:
        """Execute all triggers for a given event and context"""
        if not self.enabled:
            return []

        # Get triggers for this event and model
        triggers = self.trigger_registry.get_triggers_for_event(
            event, context.model
        )

        if not triggers:
            return []

        # Sort triggers by priority
        triggers.sort(key=lambda t: t.priority.value)

        if self.debug_mode:
            logger.debug(f"Executing {len(triggers)} triggers for {event.value} on {context.model.__name__}")

        if async_execution:
            return self._execute_triggers_async(triggers, context)
        else:
            return self._execute_triggers_sync(triggers, context)

    def _execute_triggers_sync(
        self,
        triggers: List[BaseTrigger],
        context: TriggerContext
    ) -> List[TriggerResult]:
        """Execute triggers synchronously"""
        all_results = []
        start_time = time.time()

        for trigger in triggers:
            try:
                # Execute with timeout
                future = self.executor.submit(self._execute_single_trigger, trigger, context)
                results = future.result(timeout=trigger.timeout_seconds)
                all_results.extend(results)

                # Stop execution if critical trigger failed
                if (trigger.priority == TriggerPriority.CRITICAL and
                    any(not result.success for result in results)):
                    logger.warning(f"Critical trigger {trigger.name} failed, stopping execution")
                    break

            except TimeoutError:
                logger.error(f"Trigger {trigger.name} timed out after {trigger.timeout_seconds} seconds")
                all_results.append(TriggerResult(
                    success=False,
                    message=f"Trigger execution timed out"
                ))
            except Exception as e:
                logger.error(f"Error executing trigger {trigger.name}: {e}")
                all_results.append(TriggerResult(
                    success=False,
                    message=f"Trigger execution error: {str(e)}",
                    error=e
                ))

        # Record metrics
        execution_time = time.time() - start_time
        success = all(result.success for result in all_results)
        self.metrics.record_execution(success, execution_time)

        return all_results

    def _execute_triggers_async(
        self,
        triggers: List[BaseTrigger],
        context: TriggerContext
    ) -> List[TriggerResult]:
        """Execute triggers asynchronously"""
        futures = []

        for trigger in triggers:
            future = self.executor.submit(self._execute_single_trigger, trigger, context)
            futures.append((trigger, future))

        all_results = []
        for trigger, future in futures:
            try:
                results = future.result(timeout=trigger.timeout_seconds)
                all_results.extend(results)
            except TimeoutError:
                logger.error(f"Trigger {trigger.name} timed out")
                all_results.append(TriggerResult(
                    success=False,
                    message=f"Trigger execution timed out"
                ))
            except Exception as e:
                logger.error(f"Error executing trigger {trigger.name}: {e}")
                all_results.append(TriggerResult(
                    success=False,
                    message=f"Trigger execution error: {str(e)}",
                    error=e
                ))

        return all_results

    def _execute_single_trigger(
        self,
        trigger: BaseTrigger,
        context: TriggerContext
    ) -> List[TriggerResult]:
        """Execute a single trigger with error handling and retries"""
        max_retries = trigger.max_retries
        attempt = 0

        while attempt <= max_retries:
            try:
                if self.debug_mode:
                    logger.debug(f"Executing trigger {trigger.name} (attempt {attempt + 1})")

                # Use database transaction for data consistency
                with transaction.atomic():
                    results = trigger.execute(context)

                # If successful, return results
                if all(result.success for result in results):
                    return results

                # If failed and retries available, continue to retry logic
                if attempt < max_retries:
                    # Check if any action can be retried
                    can_retry = any(
                        action.can_retry() for action in trigger.actions
                        if hasattr(action, 'can_retry')
                    )

                    if not can_retry:
                        break

                    # Calculate retry delay
                    retry_delay = min(2 ** attempt, 300)  # Max 5 minutes
                    logger.warning(f"Trigger {trigger.name} failed, retrying in {retry_delay} seconds")
                    time.sleep(retry_delay)

            except Exception as e:
                logger.error(f"Exception in trigger {trigger.name} (attempt {attempt + 1}): {e}")
                if attempt >= max_retries:
                    return [TriggerResult(
                        success=False,
                        message=f"Trigger failed after {max_retries + 1} attempts: {str(e)}",
                        error=e
                    )]

            attempt += 1

        return [TriggerResult(
            success=False,
            message=f"Trigger failed after {max_retries + 1} attempts"
        )]

    def execute_custom_trigger(
        self,
        trigger_name: str,
        context: TriggerContext
    ) -> List[TriggerResult]:
        """Execute a specific trigger by name"""
        trigger = self.trigger_registry.get_trigger_by_name(trigger_name)
        if not trigger:
            return [TriggerResult(
                success=False,
                message=f"Trigger '{trigger_name}' not found"
            )]

        return self._execute_single_trigger(trigger, context)

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        return {
            'enabled': self.enabled,
            'max_workers': self.max_workers,
            'total_triggers': len(self.trigger_registry.triggers),
            'enabled_triggers': len([t for t in self.trigger_registry.triggers.values() if t.enabled]),
            'metrics': self.metrics.to_dict(),
            'debug_mode': self.debug_mode
        }

    def enable(self):
        """Enable the trigger engine"""
        self.enabled = True
        logger.info("Trigger engine enabled")

    def disable(self):
        """Disable the trigger engine"""
        self.enabled = False
        logger.info("Trigger engine disabled")

    def clear_cache(self):
        """Clear trigger execution cache"""
        cache_key = 'trigger_registry_cache'
        cache.delete(cache_key)
        logger.info("Trigger cache cleared")

    def shutdown(self):
        """Shutdown the trigger engine"""
        self.executor.shutdown(wait=True)
        logger.info("Trigger engine shutdown")

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on trigger engine"""
        healthy = True
        issues = []

        # Check if engine is enabled
        if not self.enabled:
            healthy = False
            issues.append("Engine is disabled")

        # Check success rate
        success_rate = self.metrics.get_success_rate()
        if success_rate < 90 and self.metrics.total_executions > 10:
            healthy = False
            issues.append(f"Low success rate: {success_rate}%")

        # Check average execution time
        if self.metrics.average_execution_time > 5.0:  # 5 seconds threshold
            issues.append(f"High average execution time: {self.metrics.average_execution_time}s")

        return {
            'healthy': healthy,
            'issues': issues,
            'metrics': self.metrics.to_dict(),
            'engine_stats': self.get_engine_stats()
        }