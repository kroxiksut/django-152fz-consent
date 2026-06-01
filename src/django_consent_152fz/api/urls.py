"""URL routes for the internal API app."""

from __future__ import annotations

from django.urls import path

from .views import (
    AcceptConsentApiView,
    AttachAnonymousConsentsApiView,
    ConsentApiRootView,
    ConsentStatusApiView,
    DocumentRevisionApiView,
    RequirementsApiView,
    VerifiedArtifactConfirmApiView,
    VerifiedArtifactDetailApiView,
    VerifiedArtifactRejectApiView,
    WithdrawConsentApiView,
)

app_name = "django_consent_152fz_api"

urlpatterns = [
    path("", ConsentApiRootView.as_view(), name="root"),
    path("requirements/", RequirementsApiView.as_view(), name="requirements"),
    path("status/", ConsentStatusApiView.as_view(), name="status"),
    path(
        "attach-anonymous/",
        AttachAnonymousConsentsApiView.as_view(),
        name="attach_anonymous",
    ),
    path("accept/", AcceptConsentApiView.as_view(), name="accept"),
    path("withdraw/", WithdrawConsentApiView.as_view(), name="withdraw"),
    path("documents/<str:code>/", DocumentRevisionApiView.as_view(), name="documents"),
    path(
        "verified/artifacts/<int:consent_record_id>/",
        VerifiedArtifactDetailApiView.as_view(),
        name="verified_artifact_detail",
    ),
    path(
        "verified/artifacts/<int:consent_record_id>/confirm/",
        VerifiedArtifactConfirmApiView.as_view(),
        name="verified_artifact_confirm",
    ),
    path(
        "verified/artifacts/<int:consent_record_id>/reject/",
        VerifiedArtifactRejectApiView.as_view(),
        name="verified_artifact_reject",
    ),
]
