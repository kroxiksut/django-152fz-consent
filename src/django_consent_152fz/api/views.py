"""Views for the consent API layer."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.apps import apps
from django.core.cache import cache
from django.http import Http404
from django.utils.module_loading import import_string

from django_consent_152fz import constants
from django_consent_152fz.core.models import (
    ConsentEvent,
    ConsentRecord,
    DocumentRevision,
)
from django_consent_152fz.core.services import (
    accept_consent,
    attach_anonymous_consents_to_user,
    build_audit_context,
    get_consent_status,
    get_current_requirements,
    withdraw_consent,
)
from django_consent_152fz.exceptions import ConsentAccessDenied, ConsentError
from django_consent_152fz.request import (
    ANONYMOUS_TOKEN_COOKIE_NAME,
    build_request_audit_context,
    ensure_anonymous_token_is_usable,
    get_request_anonymous_token,
    get_request_consent_subject,
    persist_anonymous_token,
)
from django_consent_152fz.settings import (
    get_api_setting,
    get_public_api_settings,
    is_api_app_installed,
    use_api,
)

from .dependencies import require_drf
from .permissions import (
    IsStaffOrPersonalDataManager,
    can_access_verified_consent_record,
)
from .serializers import (
    AcceptConsentRequestSerializer,
    AcceptConsentResponseSerializer,
    AttachAnonymousConsentsRequestSerializer,
    ConsentStatusQuerySerializer,
    ConsentStatusResponseSerializer,
    DocumentLookupSerializer,
    DocumentRevisionSerializer,
    PublicConsentStatusRequestSerializer,
    RequirementsQuerySerializer,
    RequirementsResponseSerializer,
    VerifiedArtifactConfirmRequestSerializer,
    VerifiedArtifactRejectRequestSerializer,
    WithdrawConsentRequestSerializer,
    WithdrawConsentResponseSerializer,
)
from .throttling import (
    PublicApiAnonymousTokenRateThrottle,
    PublicApiIpRateThrottle,
    PublicApiIpWriteFloorRateThrottle,
)

require_drf()

from rest_framework.exceptions import (  # noqa: E402
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402


class BaseConsentApiView(APIView):
    """Shared behavior for consent API views."""

    api_authentication_classes: list[type[Any]] | None = None
    api_permission_classes: list[type[Any]] | None = None
    api_throttle_classes: list[type[Any]] | None = None
    enforce_public_ip_write_floor_throttle: bool = False

    def initial(self, request, *args, **kwargs):
        if not is_api_app_installed() or not use_api():
            raise Http404
        super().initial(request, *args, **kwargs)

    def get_authenticators(self):
        """Resolve the authenticators configured for the API view."""
        if self.api_authentication_classes is not None:
            return [klass() for klass in self.api_authentication_classes]
        classes = _load_rest_classes(constants.SETTING_API_AUTH_CLASSES)
        return [klass() for klass in classes]

    def get_permissions(self):
        """Resolve the permissions configured for the API view."""
        if self.api_permission_classes is not None:
            return [klass() for klass in self.api_permission_classes]
        classes = _load_rest_classes(constants.SETTING_API_PERMISSION_CLASSES)
        return [klass() for klass in classes]

    def get_throttles(self):
        if self.api_throttle_classes is None:
            return super().get_throttles()
        public_settings = get_public_api_settings()
        if (
            self.api_throttle_classes
            and all(
                klass in {PublicApiIpRateThrottle, PublicApiAnonymousTokenRateThrottle}
                for klass in self.api_throttle_classes
            )
            and not bool(public_settings[constants.SETTING_PUBLIC_API_THROTTLE_ENABLED])
        ):
            if self.enforce_public_ip_write_floor_throttle:
                return [PublicApiIpWriteFloorRateThrottle()]
            return []
        return [klass() for klass in self.api_throttle_classes]

    def _validate_query(self, serializer_class: type[Any]) -> dict[str, Any]:
        """Validate query parameters with the given serializer class."""
        serializer = serializer_class(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _validate_body(self, serializer_class: type[Any]) -> dict[str, Any]:
        """Validate request body data with the given serializer class."""
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _resolve_subject(
        self,
        *,
        anonymous_token: str | None = None,
        ensure_anonymous_token: bool = False,
        allow_query_anonymous_token: bool = True,
    ):
        """Resolve the current subject from request auth or anonymous token."""
        request = self.request._request
        user = getattr(request, "user", None)
        token = get_request_anonymous_token(
            request,
            anonymous_token=anonymous_token,
            ensure_anonymous_token=(
                ensure_anonymous_token and not getattr(user, "is_authenticated", False)
            ),
            strict_validation=bool(anonymous_token),
            allow_query_token=allow_query_anonymous_token,
        )
        if getattr(user, "is_authenticated", False):
            if anonymous_token:
                raise ValidationError(
                    detail={
                        "anonymous_token": [
                            "anonymous_token is not allowed for authenticated requests."
                        ]
                    }
                )
            return user, ""

        return get_request_consent_subject(
            request,
            anonymous_token=token,
            ensure_anonymous_token=False,
        )

    def _resolve_attachable_anonymous_token(
        self,
        *,
        explicit_token: str | None = None,
    ) -> str:
        request = self.request._request
        cookie_token = str(
            request.COOKIES.get(ANONYMOUS_TOKEN_COOKIE_NAME, "") or ""
        ).strip()
        header_token = str(request.headers.get("X-Anonymous-Token", "") or "").strip()
        body_token = str(explicit_token or "").strip()
        token = body_token or header_token or cookie_token
        if not token:
            raise ValidationError(
                detail={
                    "anonymous_token": [
                        "anonymous_token is required in body or X-Anonymous-Token header."
                    ]
                }
            )
        if not cookie_token or token != cookie_token:
            raise ValidationError(
                detail={
                    "anonymous_token": [
                        "anonymous_token must match current session cookie."
                    ]
                }
            )
        try:
            ensure_anonymous_token_is_usable(token)
        except ConsentError as exc:
            raise ValidationError(detail={"anonymous_token": [str(exc)]}) from exc
        return token

    def _build_api_audit_context(
        self,
        *,
        source: str,
        anonymous_token: str | None,
        payload_audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an audit context payload for API requests."""
        request_audit_context = build_request_audit_context(
            self.request._request,
            source=source,
            anonymous_token=anonymous_token,
        )
        if not payload_audit_context:
            return request_audit_context
        return build_audit_context(
            audit_context=request_audit_context,
            occurred_at=payload_audit_context.get("occurred_at"),
            extra_meta=payload_audit_context.get("extra_meta"),
        )

    def _response(
        self,
        data: Any,
        *,
        anonymous_token: str = "",
        status_code: int = 200,
    ):
        """Create a DRF response and persist the anonymous token when needed."""
        response = Response(data, status=status_code)
        if anonymous_token and not getattr(
            self.request.user,
            "is_authenticated",
            False,
        ):
            persist_anonymous_token(response, anonymous_token=anonymous_token)
        return response

    def _raise_api_error(self, exc: ConsentError) -> None:
        """Convert domain errors to DRF exceptions."""
        if isinstance(exc, ConsentAccessDenied):
            raise PermissionDenied(detail=str(exc)) from exc
        raise ValidationError(detail=str(exc)) from exc


class RequirementsApiView(BaseConsentApiView):
    """Return current consent requirements for the caller."""

    api_permission_classes = [IsAuthenticated]

    def get(self, request):
        validated = self._validate_query(RequirementsQuerySerializer)
        user, anonymous_token = self._resolve_subject(
            anonymous_token=validated.get("anonymous_token"),
        )
        payload = get_current_requirements(
            user=user,
            anonymous_token=anonymous_token or None,
        )
        serializer = RequirementsResponseSerializer(instance=payload)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class ConsentStatusApiView(BaseConsentApiView):
    """Return consent status for the current caller."""

    api_permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.query_params.get("anonymous_token"):
            raise ValidationError(
                detail={
                    "anonymous_token": [
                        "anonymous_token in query string is not allowed for status requests."
                    ]
                }
            )
        validated = self._validate_query(ConsentStatusQuerySerializer)
        user, anonymous_token = self._resolve_subject(
            anonymous_token=validated.get("anonymous_token"),
            allow_query_anonymous_token=False,
        )
        try:
            payload = get_consent_status(
                purpose_code=validated["purpose_code"],
                document_code=validated.get("document_code"),
                user=user,
                anonymous_token=anonymous_token or None,
            )
        except ConsentError as exc:
            self._raise_api_error(exc)
        serializer = ConsentStatusResponseSerializer(instance=payload)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class AttachAnonymousConsentsApiView(BaseConsentApiView):
    """Attach anonymous consent records to the authenticated user."""

    api_permission_classes = [IsAuthenticated]

    def post(self, request):
        validated = self._validate_body(AttachAnonymousConsentsRequestSerializer)
        token = self._resolve_attachable_anonymous_token(
            explicit_token=validated.get("anonymous_token")
        )
        records = attach_anonymous_consents_to_user(
            user=request.user,
            anonymous_token=token,
        )
        return Response(
            {
                "attached_count": len(records),
                "attached_record_ids": [record.pk for record in records],
            },
            status=200,
        )


class AcceptConsentApiView(BaseConsentApiView):
    """Accept consent through the internal API."""

    api_permission_classes = [IsAuthenticated]

    def post(self, request):
        validated = self._validate_body(AcceptConsentRequestSerializer)
        user, anonymous_token = self._resolve_subject(
            anonymous_token=validated.get("anonymous_token"),
            ensure_anonymous_token=True,
        )
        try:
            record = accept_consent(
                purpose_code=validated["purpose_code"],
                document_code=validated.get("document_code"),
                user=user,
                anonymous_token=anonymous_token or None,
                subject_ref=validated.get("subject_ref", ""),
                fields_snapshot=validated.get("fields_snapshot"),
                confirmation_method=ConsentRecord.ConfirmationMethod.API_ACCEPT,
                audit_context=self._build_api_audit_context(
                    source="api.accept",
                    anonymous_token=anonymous_token,
                    payload_audit_context=validated.get("audit_context"),
                ),
            )
        except ConsentError as exc:
            self._raise_api_error(exc)
        serializer = AcceptConsentResponseSerializer(instance=record)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class WithdrawConsentApiView(BaseConsentApiView):
    """Withdraw consent through the internal API."""

    api_permission_classes = [IsAuthenticated]

    def post(self, request):
        validated = self._validate_body(WithdrawConsentRequestSerializer)
        user, anonymous_token = self._resolve_subject(
            anonymous_token=validated.get("anonymous_token"),
        )
        try:
            record = withdraw_consent(
                purpose_code=validated["purpose_code"],
                document_code=validated.get("document_code"),
                user=user,
                anonymous_token=anonymous_token or None,
                audit_context=self._build_api_audit_context(
                    source="api.withdraw",
                    anonymous_token=anonymous_token,
                    payload_audit_context=validated.get("audit_context"),
                ),
            )
        except ConsentError as exc:
            self._raise_api_error(exc)
        serializer = WithdrawConsentResponseSerializer(instance=record)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class DocumentRevisionApiView(BaseConsentApiView):
    """Return a document revision by code."""

    api_permission_classes = [IsAuthenticated]

    def get(self, request, code: str):
        validated = self._validate_query(DocumentLookupSerializer)
        revision = _get_document_revision(
            document_code=code,
            purpose_code=validated.get("purpose_code"),
        )
        serializer = DocumentRevisionSerializer(
            instance=revision,
            context={"request": request},
        )
        return Response(serializer.data)


class ConsentApiRootView(BaseConsentApiView):
    """Expose the internal API root payload."""

    api_permission_classes = []

    def get(self, request):
        base_url = request.build_absolute_uri()
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        payload = {
            "requirements": f"{base_url}requirements/",
            "status": f"{base_url}status/",
            "attach_anonymous": f"{base_url}attach-anonymous/",
            "accept": f"{base_url}accept/",
            "withdraw": f"{base_url}withdraw/",
            "documents": f"{base_url}documents/{{document_code}}/",
        }
        if _can_expose_verified_routes(request=request):
            payload.update(
                {
                    "verified_artifact_detail": (
                        f"{base_url}verified/artifacts/{{consent_record_id}}/"
                    ),
                    "verified_artifact_confirm": (
                        f"{base_url}verified/artifacts/{{consent_record_id}}/confirm/"
                    ),
                    "verified_artifact_reject": (
                        f"{base_url}verified/artifacts/{{consent_record_id}}/reject/"
                    ),
                }
            )
        return Response(payload)


class PublicFormConsentAcceptApiView(BaseConsentApiView):
    """Accept consent through the public form API."""

    api_permission_classes = []
    api_throttle_classes = [
        PublicApiIpRateThrottle,
        PublicApiAnonymousTokenRateThrottle,
    ]
    enforce_public_ip_write_floor_throttle = True

    def post(self, request, purpose_code: str):
        _assert_public_purpose_allowed(purpose_code)
        validated = self._validate_body(AcceptConsentRequestSerializer)
        try:
            user, anonymous_token = self._resolve_subject(
                anonymous_token=validated.get("anonymous_token"),
                ensure_anonymous_token=True,
            )
            record = accept_consent(
                purpose_code=purpose_code,
                document_code=validated.get("document_code"),
                user=user,
                anonymous_token=anonymous_token or None,
                subject_ref=validated.get("subject_ref", ""),
                fields_snapshot=validated.get("fields_snapshot"),
                confirmation_method=ConsentRecord.ConfirmationMethod.API_ACCEPT,
                audit_context=self._build_api_audit_context(
                    source="api.public.accept",
                    anonymous_token=anonymous_token,
                    payload_audit_context=validated.get("audit_context"),
                ),
            )
        except ConsentError as exc:
            _raise_public_api_error(exc)
        serializer = AcceptConsentResponseSerializer(instance=record)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class PublicApiRootView(BaseConsentApiView):
    """Expose the public API root payload."""

    api_permission_classes = []
    api_throttle_classes = [
        PublicApiIpRateThrottle,
        PublicApiAnonymousTokenRateThrottle,
    ]

    def get(self, request):
        public_api_settings = get_public_api_settings()
        if not bool(public_api_settings[constants.SETTING_PUBLIC_API_SHOW_ROOT]):
            raise Http404
        base_url = request.build_absolute_uri()
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        return Response(
            {
                "form_accept": f"{base_url}forms/{{purpose_code}}/accept/",
                "form_status": f"{base_url}forms/{{purpose_code}}/status/",
                "form_document": (
                    f"{base_url}forms/{{purpose_code}}/documents/{{document_code}}/"
                ),
            }
        )


class PublicFormConsentStatusApiView(BaseConsentApiView):
    """Return consent status through the public form API."""

    api_permission_classes = []
    api_throttle_classes = [
        PublicApiIpRateThrottle,
        PublicApiAnonymousTokenRateThrottle,
    ]

    def post(self, request, purpose_code: str):
        _assert_public_purpose_allowed(purpose_code)
        if request.query_params.get("anonymous_token"):
            raise ValidationError(
                detail={
                    "anonymous_token": [
                        "anonymous_token in query string is not allowed for status requests."
                    ]
                }
            )
        validated = self._validate_body(PublicConsentStatusRequestSerializer)
        raw_anonymous_token = str(validated.get("anonymous_token") or "").strip()
        _check_public_status_fail_limit(
            request=request,
            anonymous_token=raw_anonymous_token,
        )
        try:
            user, anonymous_token = self._resolve_subject(
                anonymous_token=validated.get("anonymous_token"),
                allow_query_anonymous_token=False,
            )
            payload = get_consent_status(
                purpose_code=purpose_code,
                document_code=validated.get("document_code"),
                user=user,
                anonymous_token=anonymous_token or None,
            )
        except ConsentError as exc:
            _register_public_status_failure(
                request=request,
                anonymous_token=raw_anonymous_token or None,
            )
            _raise_public_api_error(exc)
        except ValidationError:
            _register_public_status_failure(
                request=request,
                anonymous_token=raw_anonymous_token or None,
            )
            raise
        _reset_public_status_failures(
            request=request,
            anonymous_token=raw_anonymous_token or None,
        )
        serializer = ConsentStatusResponseSerializer(instance=payload)
        return self._response(serializer.data, anonymous_token=anonymous_token)


class PublicFormDocumentApiView(BaseConsentApiView):
    """Return a document revision through the public form API."""

    api_permission_classes = []
    api_throttle_classes = [
        PublicApiIpRateThrottle,
        PublicApiAnonymousTokenRateThrottle,
    ]

    def get(self, request, purpose_code: str, document_code: str):
        _assert_public_purpose_allowed(purpose_code)
        revision = _get_document_revision(
            document_code=document_code,
            purpose_code=purpose_code,
        )
        serializer = DocumentRevisionSerializer(
            instance=revision,
            context={"request": request},
        )
        return Response(serializer.data)


class VerifiedArtifactDetailApiView(BaseConsentApiView):
    """Return the verified-artifact detail payload."""

    api_permission_classes = [IsAuthenticated, IsStaffOrPersonalDataManager]

    def get(self, request, consent_record_id: int):
        consent_record, artifact = _get_verified_artifact_or_404(
            consent_record_id=consent_record_id,
            actor_user=request.user,
        )
        return Response(
            _build_verified_artifact_payload(
                consent_record=consent_record,
                artifact=artifact,
            )
        )


class VerifiedArtifactConfirmApiView(BaseConsentApiView):
    """Confirm a verified artifact via the API."""

    api_permission_classes = [IsAuthenticated, IsStaffOrPersonalDataManager]

    def post(self, request, consent_record_id: int):
        validated = self._validate_body(VerifiedArtifactConfirmRequestSerializer)
        consent_record, _ = _get_verified_artifact_or_404(
            consent_record_id=consent_record_id,
            actor_user=request.user,
        )
        from django_consent_152fz.verified_consents.services import (
            confirm_verified_consent,
        )

        try:
            record = confirm_verified_consent(
                consent_record=consent_record,
                confirmed_by=request.user,
                confirmation_method=validated.get("confirmation_method")
                or ConsentRecord.ConfirmationMethod.EMPLOYEE_CONFIRMED,
                confirmation_note=validated.get("confirmation_note", ""),
                audit_context=self._build_api_audit_context(
                    source="api.verified.confirm",
                    anonymous_token="",
                    payload_audit_context=validated.get("audit_context"),
                ),
            )
        except ConsentError as exc:
            self._raise_api_error(exc)
        serializer = AcceptConsentResponseSerializer(instance=record)
        return self._response(serializer.data)


class VerifiedArtifactRejectApiView(BaseConsentApiView):
    """Reject a verified artifact via the API."""

    api_permission_classes = [IsAuthenticated, IsStaffOrPersonalDataManager]

    def post(self, request, consent_record_id: int):
        validated = self._validate_body(VerifiedArtifactRejectRequestSerializer)
        consent_record, _ = _get_verified_artifact_or_404(
            consent_record_id=consent_record_id,
            actor_user=request.user,
        )
        from django_consent_152fz.verified_consents.services import (
            reject_verified_consent,
        )

        try:
            record = reject_verified_consent(
                consent_record=consent_record,
                rejected_by=request.user,
                actor_type=(
                    ConsentEvent.ActorType.ADMIN
                    if getattr(request.user, "is_superuser", False)
                    else ConsentEvent.ActorType.EMPLOYEE
                ),
                rejection_note=validated["rejection_note"],
                audit_context=self._build_api_audit_context(
                    source="api.verified.reject",
                    anonymous_token="",
                    payload_audit_context=validated.get("audit_context"),
                ),
            )
        except ConsentError as exc:
            self._raise_api_error(exc)
        serializer = WithdrawConsentResponseSerializer(instance=record)
        return self._response(serializer.data)


def _load_rest_classes(setting_name: str) -> list[type[Any]]:
    """Load DRF classes from a settings value."""
    raw_value = get_api_setting(setting_name) or []
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise ValidationError(detail=f"{setting_name} must be a list or tuple.")

    classes: list[type] = []
    for item in raw_value:
        if isinstance(item, str):
            classes.append(import_string(item))
            continue
        classes.append(item)
    return classes


def _get_document_revision(
    *,
    document_code: str,
    purpose_code: str | None = None,
) -> DocumentRevision:
    """Resolve the requested document revision."""
    qs = DocumentRevision.objects.select_related("document").filter(
        document__code=document_code,
        document__is_active=True,
        is_active=True,
    )
    if purpose_code:
        qs = qs.filter(purpose_code=purpose_code)

    revisions = list(qs.order_by("-published_at", "-created_at", "-id")[:2])
    if not revisions:
        raise NotFound(
            detail=f"No active document revision found for '{document_code}'."
        )
    if len(revisions) > 1 and not purpose_code:
        raise ValidationError(
            detail={
                "purpose_code": [
                    "Specify purpose_code when document is used in multiple flows."
                ]
            }
        )
    return revisions[0]


def _get_public_allowed_purposes() -> set[str]:
    raw = get_api_setting(constants.SETTING_PUBLIC_API_ALLOWED_PURPOSES) or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValidationError(
            detail=(
                f"{constants.SETTING_PUBLIC_API_ALLOWED_PURPOSES} "
                "must be a list or tuple."
            )
        )
    return {str(item).strip() for item in raw if str(item).strip()}


def _assert_public_purpose_allowed(purpose_code: str) -> None:
    allowed = _get_public_allowed_purposes()
    if purpose_code not in allowed:
        raise NotFound(detail="Public consent API is not enabled for this purpose.")


def _raise_public_api_error(exc: ConsentError) -> None:
    if isinstance(exc, ConsentAccessDenied):
        raise PermissionDenied() from exc
    raise ValidationError() from exc


def _get_verified_artifact_or_404(
    *,
    consent_record_id: int,
    actor_user: Any | None = None,
):
    not_found_detail = "Verified consent artifact not found."
    try:
        from django_consent_152fz.verified_consents.models import (
            VerifiedConsentArtifact,
        )
    except ModuleNotFoundError as exc:
        raise NotFound(detail=not_found_detail) from exc

    consent_record = (
        ConsentRecord.objects.select_related("purpose", "document_revision__document")
        .filter(pk=consent_record_id)
        .first()
    )
    if consent_record is None:
        raise NotFound(detail=not_found_detail)
    if actor_user is not None and not can_access_verified_consent_record(
        user=actor_user,
        consent_record=consent_record,
    ):
        raise NotFound(detail=not_found_detail)

    artifact = (
        VerifiedConsentArtifact.objects.select_related("policy")
        .filter(consent_record_id=consent_record.pk)
        .first()
    )
    if artifact is None:
        raise NotFound(detail=not_found_detail)
    return consent_record, artifact


def _can_expose_verified_routes(*, request) -> bool:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return False
    if not apps.is_installed(constants.VERIFIED_CONSENTS_APP):
        return False
    permission = IsStaffOrPersonalDataManager()
    return permission.has_permission(request, ConsentApiRootView())


def _build_verified_artifact_payload(*, consent_record: ConsentRecord, artifact):
    artifact_file_url = ""
    if getattr(artifact, "file", None):
        artifact_file_url = str(getattr(artifact.file, "url", "") or "")
    return {
        "consent_record_id": consent_record.pk,
        "consent_status": consent_record.status,
        "purpose_code": consent_record.purpose.code,
        "document_code": consent_record.document_revision.document.code,
        "artifact_id": artifact.pk,
        "artifact_type": artifact.artifact_type,
        "subject_signed_at": artifact.subject_signed_at,
        "artifact_file_url": artifact_file_url,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _public_status_fail_cache_key(*, ip: str, token: str) -> str:
    return f"dz152fz:public_status_fail:{ip}:{token}"


def _check_public_status_fail_limit(*, request, anonymous_token: str) -> None:
    if not anonymous_token:
        return
    public_api_settings = get_public_api_settings()
    limit = int(public_api_settings[constants.SETTING_PUBLIC_STATUS_FAIL_LIMIT])
    if limit <= 0:
        return
    ip = _resolve_request_ip(request)
    fails = int(
        cache.get(_public_status_fail_cache_key(ip=ip, token=anonymous_token)) or 0
    )
    if fails >= limit:
        raise PermissionDenied(detail="Too many unsuccessful status checks.")


def _register_public_status_failure(*, request, anonymous_token: str | None) -> None:
    token = str(anonymous_token or "").strip()
    if not token:
        return
    public_api_settings = get_public_api_settings()
    window_seconds = int(
        public_api_settings[constants.SETTING_PUBLIC_STATUS_FAIL_WINDOW_SECONDS]
    )
    if window_seconds <= 0:
        return
    ip = _resolve_request_ip(request)
    key = _public_status_fail_cache_key(ip=ip, token=token)
    try:
        fails = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return
    cache.set(key, fails, timeout=window_seconds)


def _reset_public_status_failures(*, request, anonymous_token: str | None) -> None:
    token = str(anonymous_token or "").strip()
    if not token:
        return
    ip = _resolve_request_ip(request)
    cache.delete(_public_status_fail_cache_key(ip=ip, token=token))


def _resolve_request_ip(request) -> str:
    if hasattr(request, "META"):
        meta = request.META
    else:
        meta = request._request.META
    return str(meta.get("REMOTE_ADDR") or "unknown")
