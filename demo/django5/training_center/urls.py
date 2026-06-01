from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("consents/", views.consents, name="consents"),
    path("courses/", views.course_list, name="course_list"),
    path("courses/signup/", views.course_signup, name="course_signup"),
    path("certificate-request/", views.certificate_request, name="certificate_request"),
    path("contact/", views.contact, name="contact"),
    path("profile/", views.profile, name="profile"),
    path(
        "verified-paper-consent/",
        views.verified_paper_consent,
        name="verified_paper_consent",
    ),
]
