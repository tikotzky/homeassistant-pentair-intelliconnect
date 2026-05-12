"""
Entity package for pentair_pool.

Architecture:
    All platform entities inherit from (PlatformEntity, PentairPoolEntity).
    MRO order matters — platform-specific class first, then the integration base.
    Entities read data from coordinator.data and NEVER call the API client directly.
    Unique IDs follow the pattern: {entry_id}_{description.key}

See entity/base.py for the PentairPoolEntity base class.
"""

from .base import PentairPoolEntity

__all__ = ["PentairPoolEntity"]
