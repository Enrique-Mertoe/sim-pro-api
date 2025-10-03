from .user_rpc import functions as user_functions
from .team_rpc import functions as team_functions

functions = {
    **user_functions,
    **team_functions
}