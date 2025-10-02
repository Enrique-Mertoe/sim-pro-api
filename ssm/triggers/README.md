# SSM Trigger Framework

A sophisticated, production-ready trigger system for Django models that provides declarative event-driven programming with comprehensive monitoring and management capabilities.

## 🚀 Features

### Core Capabilities
- **Event-Driven Architecture**: Pre/Post save, delete, bulk operations, and custom events
- **Conditional Execution**: Rich condition system with field changes, user roles, time-based rules
- **Action Chaining**: Multiple actions per trigger with error handling and retries
- **Performance Monitoring**: Execution metrics, success rates, and performance analytics
- **Management API**: Supabase-compatible REST endpoints for trigger management

### Advanced Features
- **Signal Integration**: Seamless Django signals integration with context preservation
- **Async Execution**: Background trigger execution for non-blocking operations
- **Caching Layer**: Intelligent caching for optimal performance
- **Health Monitoring**: Comprehensive health checks and diagnostics
- **Audit Logging**: Complete audit trail for all trigger activities

## 📁 Architecture

```
ssm/triggers/
├── __init__.py                 # Main exports and initialization
├── apps.py                     # Django app configuration
├── urls.py                     # URL patterns for management API
├── management_views.py         # REST API endpoints
├── initialize.py               # System initialization utilities
├── base/                       # Core framework components
│   ├── trigger_base.py         # Base classes and enums
│   ├── trigger_engine.py       # Execution engine
│   ├── trigger_decorator.py    # Decorators for easy trigger creation
│   └── signal_integration.py   # Django signals integration
├── registry/                   # Trigger registry and management
│   └── trigger_registry.py     # Central trigger registry
├── conditions/                 # Conditional logic components
│   └── common_conditions.py    # Pre-built condition classes
├── actions/                    # Action implementations
│   └── common_actions.py       # Pre-built action classes
└── models/                     # Model-specific triggers
    ├── sim_card_triggers.py    # SIM card related triggers
    └── shop_triggers.py        # Shop management triggers
```

## 🎯 Quick Start

### 1. Basic Trigger with Decorator

```python
from ssm.triggers import post_save_trigger, TriggerContext, TriggerResult

@post_save_trigger(
    'SimCard',
    name='sim_card_activation',
    description='Handle SIM card activation'
)
def handle_sim_activation(context: TriggerContext) -> TriggerResult:
    sim_card = context.instance

    if sim_card.status == 'ACTIVE':
        # Send activation notification
        send_notification(
            user=sim_card.assigned_to_user,
            message=f"SIM {sim_card.serial_number} activated successfully"
        )

    return TriggerResult(success=True, message="Activation handled")
```

### 2. Conditional Trigger

```python
from ssm.triggers import conditional_trigger

@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'Shop',
    condition_func=lambda ctx: ctx.instance.status == 'active',
    name='shop_activation_handler'
)
def handle_shop_activation(context: TriggerContext) -> TriggerResult:
    shop = context.instance

    # Initialize shop operations
    setup_shop_inventory(shop)
    notify_stakeholders(shop)

    return TriggerResult(success=True, message="Shop activated")
```

### 3. Field Change Trigger

```python
from ssm.triggers import field_changed_trigger

@field_changed_trigger(
    'SimCard',
    'fraud_flag',
    name='fraud_alert_trigger'
)
def handle_fraud_detection(context: TriggerContext) -> TriggerResult:
    sim_card = context.instance

    if sim_card.fraud_flag:
        # Send immediate alert
        send_fraud_alert(
            sim_card=sim_card,
            reason=sim_card.fraud_reason
        )

    return TriggerResult(success=True, message="Fraud alert sent")
```

## 🔧 Configuration

### Django Settings

Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'ssm.triggers',
]
```

### Middleware Configuration

Add trigger middleware for request context:

```python
MIDDLEWARE = [
    # ... other middleware
    'ssm.triggers.base.signal_integration.TriggerRequestMiddleware',
]
```

### Optional Settings

```python
# Trigger system configuration
TRIGGER_DEBUG = False                    # Enable debug logging
TRIGGER_CACHE_TIMEOUT = 300             # Cache timeout in seconds
TRIGGER_MAX_WORKERS = 10                # Thread pool size
TRIGGER_DEFAULT_TIMEOUT = 30            # Default trigger timeout
```

## 🌐 Management API

All endpoints follow Supabase-compatible patterns and are available at `/rest/v1/triggers/`

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status/` | Get system status and statistics |
| GET | `/list/` | List all triggers with filtering |
| GET | `/details/{name}/` | Get detailed trigger information |
| POST | `/toggle/{name}/` | Enable/disable specific trigger |
| POST | `/execute/{name}/` | Manually execute trigger |
| POST | `/engine/toggle/` | Enable/disable entire engine |
| GET | `/logs/` | Get execution logs |
| POST | `/cache/clear/` | Clear system caches |
| GET | `/config/export/` | Export configuration |

### Example API Usage

```javascript
// Get trigger status
const response = await fetch('/rest/v1/triggers/status/', {
    headers: { 'Authorization': `Bearer ${token}` }
});

// List all triggers
const triggers = await fetch('/rest/v1/triggers/list/?enabled_only=true');

// Execute trigger manually
await fetch('/rest/v1/triggers/execute/sim_card_activation/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        model: 'SimCard',
        instance_id: 'uuid-here',
        event: 'custom'
    })
});
```

## 📊 Monitoring & Analytics

### System Health Check

```python
from ssm.triggers import get_system_status

status = get_system_status()
print(f"System healthy: {status['system_healthy']}")
print(f"Total triggers: {status['total_triggers']}")
```

### Performance Metrics

```python
from ssm.triggers import get_trigger_performance_metrics

metrics = get_trigger_performance_metrics()
print(f"Overall success rate: {metrics['overall_stats']['overall_success_rate']}%")
```

### Trigger Listing

```python
from ssm.triggers import list_all_triggers

triggers = list_all_triggers()
for trigger in triggers['triggers']:
    print(f"{trigger['name']}: {trigger['execution_stats']['success_rate']}%")
```

## 🎨 Advanced Usage

### Custom Conditions

```python
from ssm.triggers.base.trigger_base import TriggerCondition

class BusinessHoursCondition(TriggerCondition):
    def evaluate(self, context):
        from datetime import datetime
        now = datetime.now()
        return 9 <= now.hour <= 17

    def description(self):
        return "During business hours (9 AM - 5 PM)"

# Use in trigger
@conditional_trigger(
    TriggerEvent.POST_SAVE,
    'Shop',
    condition_func=BusinessHoursCondition(),
    name='business_hours_trigger'
)
def business_hours_handler(context):
    # Only executes during business hours
    pass
```

### Custom Actions

```python
from ssm.triggers.base.trigger_base import TriggerAction

class SlackNotificationAction(TriggerAction):
    def __init__(self, webhook_url, message_template):
        self.webhook_url = webhook_url
        self.message_template = message_template

    def execute(self, context):
        # Send Slack notification
        message = self.message_template.format(
            model=context.model.__name__,
            instance_id=context.instance.pk
        )
        # ... send to Slack
        return TriggerResult(success=True, message="Slack notification sent")

    def description(self):
        return f"Send Slack notification to {self.webhook_url}"
```

### Programmatic Trigger Creation

```python
from ssm.triggers.base.trigger_base import BaseTrigger, TriggerEvent, TriggerPriority
from ssm.triggers.conditions.common_conditions import field_equals
from ssm.triggers.actions.common_actions import log_info

# Create trigger programmatically
trigger = BaseTrigger(
    name='custom_trigger',
    event=TriggerEvent.POST_SAVE,
    model='SimCard',
    conditions=[field_equals('status', 'ACTIVE')],
    actions=[log_info('SIM card activated')],
    priority=TriggerPriority.HIGH,
    description='Custom programmatic trigger'
)

# Register trigger
from ssm.triggers import trigger_registry
trigger_registry.register_trigger(trigger)
```

## 🛠️ Built-in Triggers

### SIM Card Triggers
- **sim_card_quality_update**: Updates quality statistics when SIM quality changes
- **sim_card_status_notification**: Sends notifications on status changes
- **sim_card_fraud_alert**: Sends alerts when fraud is detected
- **sim_card_assignment_tracking**: Tracks SIM assignments and updates inventory
- **sim_card_registration_completion**: Handles registration completion

### Shop Management Triggers
- **shop_status_change_handler**: Handles shop status changes and notifications
- **shop_sales_performance_update**: Updates performance metrics on sales
- **shop_inventory_sale_tracking**: Tracks inventory sales and financials
- **shop_transfer_workflow**: Manages transfer workflow stages

## 🔍 Debugging & Troubleshooting

### Enable Debug Mode

```python
# In settings.py
TRIGGER_DEBUG = True

# Or programmatically
from ssm.triggers import get_trigger_engine
engine = get_trigger_engine()
engine.debug_mode = True
```

### Check Trigger Health

```python
from ssm.triggers import trigger_registry

health = trigger_registry.health_check()
if not health['healthy']:
    print("Issues found:", health['issues'])
```

### View Execution Logs

```bash
# In Django shell
from ssm.models import ActivityLog

# Get trigger-related logs
logs = ActivityLog.objects.filter(
    action_type__in=['trigger_executed', 'trigger_failed']
).order_by('-created_at')[:10]

for log in logs:
    print(f"{log.created_at}: {log.details}")
```

## 🚦 Production Considerations

### Performance Tips
1. **Use async execution** for non-critical triggers
2. **Monitor success rates** and disable problematic triggers
3. **Set appropriate timeouts** to prevent blocking
4. **Use caching** for frequently accessed data

### Security Guidelines
1. **Restrict management API** to admin users only
2. **Validate trigger inputs** to prevent injection attacks
3. **Log all trigger activities** for audit purposes
4. **Use HTTPS** for all management endpoints

### Monitoring Checklist
- [ ] System health checks pass
- [ ] Success rates above 95%
- [ ] Average execution time under 1 second
- [ ] No memory leaks in trigger cache
- [ ] Error logs reviewed regularly

## 📝 License

This trigger framework is part of the SSM Backend API system and follows the same licensing terms.

## 🤝 Contributing

1. Follow existing code patterns and decorators
2. Add comprehensive tests for new triggers
3. Update documentation for new features
4. Ensure backward compatibility
5. Test with various Django model scenarios

---

For more information, see the inline documentation in each module or contact the development team.