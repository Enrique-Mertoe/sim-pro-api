from .tl_dashboard import functions as tl_dashboard_functions
from .ba_dashboard import functions as ba_dashboard_functions

functions = {
    **tl_dashboard_functions,
    **ba_dashboard_functions
}
