from __future__ import annotations

from django.http import JsonResponse


def api_root_stub(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "consents": f"{base}/api/consents/",
            "consents_v1": f"{base}/api/consents/v1/",
            "consents_public_v1": f"{base}/api/consents/public/v1/",
        }
    )


def api_consents_root_stub(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "v1": f"{base}/api/consents/v1/",
            "public_v1": f"{base}/api/consents/public/v1/",
        }
    )


def api_consents_v1_stub(request):
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "root": f"{base}/api/consents/v1/",
            "requirements": f"{base}/api/consents/v1/requirements/",
            "status": f"{base}/api/consents/v1/status/",
            "accept": f"{base}/api/consents/v1/accept/",
            "withdraw": f"{base}/api/consents/v1/withdraw/",
            "documents": f"{base}/api/consents/v1/documents/{{document_code}}/",
        }
    )


def api_not_found_stub(request, subpath: str = ""):
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "detail": "Такого API-адреса нет.",
            "requested_path": request.path,
            "allowed": {
                "api_root": f"{base}/api/",
                "consents_root": f"{base}/api/consents/",
                "consents_v1": f"{base}/api/consents/v1/",
                "consents_public_v1": f"{base}/api/consents/public/v1/",
            },
        },
        status=404,
    )
