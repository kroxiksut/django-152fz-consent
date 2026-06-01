"""Throttling helpers for the public consent API surface."""

from __future__ import annotations

from django_consent_152fz import constants
from django_consent_152fz.settings import get_public_api_settings

from .dependencies import require_drf
from .serializers import AnonymousSubjectSerializer

require_drf()

from rest_framework.throttling import SimpleRateThrottle  # noqa: E402


class PublicApiIpRateThrottle(SimpleRateThrottle):
    """Rate-limit public API calls by client IP."""

    scope = "public_api_ip"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def get_rate(self):
        return get_public_api_settings()[constants.SETTING_PUBLIC_API_THROTTLE_IP_RATE]


class PublicApiIpWriteFloorRateThrottle(PublicApiIpRateThrottle):
    """Always-on floor IP throttle for unauthenticated write operations."""

    scope = "public_api_ip_write_floor"

    def get_rate(self):
        return get_public_api_settings()[
            constants.SETTING_PUBLIC_API_THROTTLE_IP_WRITE_FLOOR_RATE
        ]


class PublicApiAnonymousTokenRateThrottle(SimpleRateThrottle):
    """Rate-limit public API calls by `anonymous_token` when provided."""

    scope = "public_api_anon"

    def get_cache_key(self, request, view):
        raw_token = (
            request.query_params.get("anonymous_token")
            or request.data.get("anonymous_token")
            or ""
        )
        payload = {"anonymous_token": raw_token}
        serializer = AnonymousSubjectSerializer(data=payload)
        serializer.is_valid(raise_exception=False)
        token = str(serializer.validated_data.get("anonymous_token", "")).strip()
        if token:
            ident = f"anon:{token}"
            return self.cache_format % {"scope": self.scope, "ident": ident}
        ident = self.get_ident(request)
        if not ident:
            return None
        fallback_ident = f"ip:{ident}"
        return self.cache_format % {"scope": self.scope, "ident": fallback_ident}

    def get_rate(self):
        return get_public_api_settings()[
            constants.SETTING_PUBLIC_API_THROTTLE_ANON_RATE
        ]
