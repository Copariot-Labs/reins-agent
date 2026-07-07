from __future__ import annotations


class WeChatError(Exception):
    """Base error for deterministic WeChat automation."""


class WeChatUnsupportedPlatform(WeChatError):
    """Raised when no deterministic adapter is available for this platform."""


class WeChatDependencyError(WeChatError):
    """Raised when the local OS automation dependency is missing."""
