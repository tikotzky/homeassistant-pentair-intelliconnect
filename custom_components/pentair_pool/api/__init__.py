"""
API package for pentair_pool.

Architecture:
    Three-layer data flow: Entities → Coordinator → API Client.
    Only the coordinator should call the API client. Entities must never
    import or call the API client directly.

Exception hierarchy:
    PentairPoolApiClientError (base)
    ├── PentairPoolApiClientCommunicationError (network/timeout)
    └── PentairPoolApiClientAuthenticationError (401/403)

Coordinator exception mapping:
    ApiClientAuthenticationError → ConfigEntryAuthFailed (triggers reauth)
    ApiClientCommunicationError → UpdateFailed (auto-retry)
    ApiClientError             → UpdateFailed (auto-retry)
"""

from .client import (
    PentairPoolApiClient,
    PentairPoolApiClientAuthenticationError,
    PentairPoolApiClientCommunicationError,
    PentairPoolApiClientError,
)

__all__ = [
    "PentairPoolApiClient",
    "PentairPoolApiClientAuthenticationError",
    "PentairPoolApiClientCommunicationError",
    "PentairPoolApiClientError",
]
