class AggregatorError(Exception):
    """Base for all application errors. handlers.py maps these to JSON."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.code.replace("_", " ")
        super().__init__(self.message)


# ---------- Client-facing errors ----------


class AuthenticationError(AggregatorError):
    status_code = 401
    code = "unauthorized"


class ValidationFailed(AggregatorError):
    status_code = 422
    code = "validation_error"


# ---------- Upstream provider errors ----------


class ProviderError(AggregatorError):
    """Base for failures talking to an upstream provider."""

    status_code = 502
    code = "provider_error"

    def __init__(self, provider: str, message: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)
        self.args = (f"[{provider}] {self.message}",)


class ProviderTimeout(ProviderError):
    status_code = 504
    code = "provider_timeout"


class ProviderUnavailable(ProviderError):
    status_code = 503
    code = "provider_unavailable"


class ProviderAuthError(ProviderError):
    # Our credentials to the provider are bad. That's a server problem, not the client's.
    status_code = 502
    code = "provider_auth_error"


class ProviderRateLimited(ProviderError):
    status_code = 429
    code = "provider_rate_limited"


class ProviderNotFound(ProviderError):
    status_code = 404
    code = "provider_not_found"


class ProviderBadResponse(ProviderError):
    status_code = 502
    code = "provider_bad_response"
