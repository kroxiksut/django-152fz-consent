"""Best-effort inventory hints for cookie/script integrations.

This module intentionally provides advisory heuristics only.
It does not perform legal classification and must always be treated as
an operator-assist layer with mandatory manual verification.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
# Reason: Introspection payloads are normalized dynamically.
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

from django_cookies_152fz.models import CookieCategory, CookieRegistryItem

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "necessary",
        (
            "recaptcha",
            "hcaptcha",
            "cloudflare",
            "csrf",
            "security",
            "session",
        ),
    ),
    (
        "functional",
        (
            "intercom",
            "crisp",
            "zendesk",
            "chat",
            "support",
            "widget",
        ),
    ),
    (
        "analytics",
        (
            "google-analytics",
            "googletagmanager",
            "gtag",
            "metrika",
            "analytics",
            "segment",
            "amplitude",
            "mixpanel",
            "hotjar",
        ),
    ),
    (
        "marketing",
        (
            "facebook",
            "doubleclick",
            "ads",
            "adservice",
            "tiktok",
            "mytarget",
            "pixel",
            "remarketing",
        ),
    ),
)


def build_best_effort_inventory_hints(
    *,
    found_integrations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return advisory category hints for discovered integrations."""
    hints: list[dict[str, Any]] = []
    by_category: Counter[str] = Counter()
    for item in found_integrations:
        hint = _build_one_hint(item)
        hints.append(hint)
        by_category[hint["suggested_category"]] += 1
    return {
        "mode": "best_effort_advisory",
        "requires_manual_verification": True,
        "total_integrations": len(hints),
        "summary_by_category": dict(by_category),
        "hints": hints,
    }


def build_inventory_hints_for_registry_items() -> dict[str, Any]:
    """Analyze active CookieRegistryItem records and build advisory hints."""
    items = (
        CookieRegistryItem.objects.filter(is_active=True)
        .select_related("category")
        .order_by("code")
    )
    found_integrations = [
        {
            "code": item.code,
            "provider": item.provider,
            "purpose": item.purpose,
            "src_url": item.src_url,
            "cookie_names": list(item.cookie_names),
            "current_category_code": item.category.code,
        }
        for item in items
    ]
    report = build_best_effort_inventory_hints(found_integrations=found_integrations)
    report["registry_mapping_review_queue"] = (
        build_registry_mapping_review_queue_from_report(report=report)
    )
    report["source"] = "cookie_registry_items"
    return report


def build_registry_mapping_review_queue_from_report(
    *, report: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Build operator review queue for CookieRegistryItem category mapping.

    This queue is advisory-only: it does not write to DB and must be reviewed
    by an operator before any manual category changes.
    """

    categories_by_code = {
        item.code: item.id
        for item in CookieCategory.objects.filter(is_active=True).only("id", "code")
    }
    queue: list[dict[str, Any]] = []
    for hint in report.get("hints", []):
        current_category_code = str(hint.get("current_category_code") or "")
        suggested_category = str(hint.get("suggested_category") or "")
        suggested_category_exists = suggested_category in categories_by_code
        mapping_status = (
            "aligned"
            if current_category_code == suggested_category
            else "requires_manual_review"
        )
        queue.append(
            {
                "integration_code": str(hint.get("integration_code") or ""),
                "current_category_code": current_category_code,
                "suggested_category": suggested_category,
                "suggested_category_id": categories_by_code.get(suggested_category),
                "suggested_category_exists": suggested_category_exists,
                "mapping_status": mapping_status,
                "requires_manual_verification": True,
                "auto_apply_allowed": False,
                "reasons": list(hint.get("reasons", [])),
                "confidence": str(hint.get("confidence") or "low"),
            }
        )
    return queue


def _build_one_hint(item: Mapping[str, Any]) -> dict[str, Any]:
    code = str(item.get("code") or "").strip()
    provider = str(item.get("provider") or "").strip().lower()
    purpose = str(item.get("purpose") or "").strip().lower()
    src_url = str(item.get("src_url") or "").strip().lower()
    host = _extract_host(src_url)
    cookie_names = [str(name).strip().lower() for name in item.get("cookie_names", [])]
    searchable = " ".join(
        [code.lower(), provider, purpose, src_url, host, *cookie_names]
    )

    reasons: list[str] = []
    for category_code, tokens in _CATEGORY_RULES:
        matched_tokens = [token for token in tokens if token in searchable]
        if matched_tokens:
            reasons = [f"matched tokens: {', '.join(sorted(set(matched_tokens)))}"]
            confidence = "medium" if len(matched_tokens) >= 2 else "low"
            return {
                "integration_code": code,
                "current_category_code": str(item.get("current_category_code") or ""),
                "suggested_category": category_code,
                "confidence": confidence,
                "reasons": reasons,
                "requires_manual_verification": True,
            }

    return {
        "integration_code": code,
        "current_category_code": str(item.get("current_category_code") or ""),
        "suggested_category": "functional",
        "confidence": "low",
        "reasons": ["no strong signature matched, fallback suggestion"],
        "requires_manual_verification": True,
    }


def _extract_host(src_url: str) -> str:
    if not src_url:
        return ""
    parsed = urlparse(src_url)
    return str(parsed.netloc or "").strip().lower()
