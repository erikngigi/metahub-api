"""Application and upstream provider exception hierarchy."""


class AggregatorError(Exception):
    """Base for all application errors. handlers.py maps these to JSON."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str | None = None) -> None:
        """Initialize the exception with an optional message falling back to ``code``."""
        self.message = message or self.code.replace("_", " ")
        super().__init__(self.message)


# ---------- Client-facing errors ----------


class AuthenticationError(AggregatorError):
    """Raised when a client fails authentication (HTTP ``401``)."""

    status_code = 401
    code = "unauthorized"


class ValidationFailed(AggregatorError):
    """Raised when input or domain validation fails (HTTP ``422``)."""

    status_code = 422
    code = "validation_error"


# ---------- Upstream provider errors ----------


class ProviderError(AggregatorError):
    """Base for failures talking to an upstream provider."""

    status_code = 502
    code = "provider_error"

    def __init__(self, provider: str, message: str | None = None) -> None:
        """Initialize a provider error tagged with the provider name."""
        self.provider = provider
        super().__init__(message)
        self.args = (f"[{provider}] {self.message}",)


class ProviderTimeout(ProviderError):
    """Raised when an upstream provider request times out (HTTP ``504``)."""

    status_code = 504
    code = "provider_timeout"


class ProviderUnavailable(ProviderError):
    """Raised when an upstream provider is unreachable or returns ``5xx`` (HTTP ``503``)."""

    status_code = 503
    code = "provider_unavailable"


class ProviderAuthError(ProviderError):
    """Raised when the application's credentials to a provider are invalid (HTTP ``502``)."""

    # Our credentials to the provider are bad. That's a server problem, not the client's.
    status_code = 502
    code = "provider_auth_error"


class ProviderRateLimited(ProviderError):
    """Raised when an upstream provider rate-limits requests (HTTP ``429``)."""

    status_code = 429
    code = "provider_rate_limited"


class ProviderNotFound(ProviderError):
    """Raised when a requested resource is not found on a provider (HTTP ``404``)."""

    status_code = 404
    code = "provider_not_found"


class ProviderBadResponse(ProviderError):
    """Raised when a provider returns an unexpected status or malformed payload (HTTP ``502``)."""

    status_code = 502
    code = "provider_bad_response"
