"""Custom application exceptions with clear meanings for API handlers."""


class ResourceNotFoundError(Exception):
    """Raise when a requested resource does not exist for the current user."""


class ResourceConflictError(Exception):
    """Raise when a request conflicts with existing application data."""