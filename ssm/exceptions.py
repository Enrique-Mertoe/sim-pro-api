class RequiredValueError(Exception):
    """Raised when a required value is missing."""
    pass

class InvalidStatusError(Exception):
    """Raised when a model has an invalid status."""
    pass
