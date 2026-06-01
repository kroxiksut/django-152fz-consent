"""Exception hierarchy for the package.

The package keeps its own exception tree so integrators can catch a single
base error without mixing package failures with unrelated Python or Django
exceptions.
"""


class ConsentError(Exception):
    """Basic consent package exception."""


class ConsentConfigurationError(ConsentError):
    """Configuration error in the package or its optional modules."""


class ConsentIntegrationError(ConsentError):
    """External integration or missing dependency error."""


class ConsentAccessDenied(ConsentError):
    """Access denied error raised by a computed `ConsentAccessPolicy`.

    The `result` field stores the normalized policy evaluation result. This
    lets callers inspect not only the denial itself, but also the reason,
    reaction mode, and target document or purpose for a redirect.
    """

    def __init__(self, message: str, *, result: dict | None = None) -> None:
        super().__init__(message)
        # Copy the dictionary so callers cannot mutate exception state after raising.
        self.result = dict(result or {})
