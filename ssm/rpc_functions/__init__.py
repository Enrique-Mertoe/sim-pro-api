"""
RPC Functions Registry
This module dynamically imports and registers all RPC functions
"""
from .auth_functions import functions as auth_functions
from .team_functions import functions as team_functions
from .simcard_functions import functions as simcard_functions
from .batch_functions import functions as batch_functions
from .user_functions import functions as user_functions
from .team_membership_functions import functions as team_membership_functions
from .onboarding_functions import functions as onboarding_functions
from .analytics_functions import functions as analytics_functions
from .reports_functions import functions as reports_functions
from .settings_functions import functions as settings_functions
from .admin_rpc_functions import functions as admin_functions
from .picklist_rpc_function import functions as picklist_rpc_function
from .dashboard_functions import functions as dashboard_functions
from .shop_rpc_functions import functions as shop_rpc_functions
from .payment_functions import functions as payment_functions

# Combine all function registries
functions = {
    **auth_functions,
    **team_functions,
    **simcard_functions,
    **batch_functions,
    **user_functions,
    **team_membership_functions,
    **onboarding_functions,
    **analytics_functions,
    **reports_functions,
    **settings_functions,
    **picklist_rpc_function,
    **admin_functions,
    **dashboard_functions,
    **shop_rpc_functions,
    **payment_functions
}
