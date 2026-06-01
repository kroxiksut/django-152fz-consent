import re
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import CertificateRequest, ContactMessage, Course, CourseSignup


class ConsentBootstrapMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        call_command("bootstrap_152fz_sample_documents", verbosity=0)
        call_command("bootstrap_training_center_demo", verbosity=0)


class ContactFormTests(ConsentBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_contact_form_saves_message(self) -> None:
        before = ContactMessage.objects.count()
        response = self.client.post(
            reverse("pages:contact"),
            {
                "full_name": "Demo User",
                "email": "demo@example.com",
                "message": "Need details about schedule",
                "consent_decision": "agree",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), before + 1)

    def test_contact_form_invalid_data_shows_errors(self) -> None:
        before = ContactMessage.objects.count()
        response = self.client.post(
            reverse("pages:contact"),
            {
                "full_name": "",
                "email": "not-an-email",
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is-invalid", html=False)
        self.assertEqual(ContactMessage.objects.count(), before)

    def test_contact_form_decline_consent_does_not_save(self) -> None:
        before = ContactMessage.objects.count()
        response = self.client.post(
            reverse("pages:contact"),
            {
                "full_name": "Decline User",
                "email": "decline@example.com",
                "message": "No consent",
                "consent_decision": "decline",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), before)


class CourseSignupWizardTests(ConsentBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.active_course = Course.objects.create(
            title="Backend Python",
            slug="backend-python",
            short_description="Backend basics",
            description="Backend basics and APIs",
            is_active=True,
        )
        Course.objects.create(
            title="Inactive",
            slug="inactive",
            short_description="Inactive",
            description="Inactive",
            is_active=False,
        )

    @staticmethod
    def _wizard_step_field(html: str) -> str:
        match = re.search(r'name="([^"]*current_step)"', html)
        assert match is not None
        return match.group(1)

    def _run_signup_flow(
        self, *, full_name: str, email: str, phone: str, comment: str
    ) -> None:
        start = self.client.get(reverse("pages:course_signup"))
        self.assertEqual(start.status_code, 200)

        step_field_name = self._wizard_step_field(start.content.decode("utf-8"))
        step_one = self.client.post(
            reverse("pages:course_signup"),
            {
                step_field_name: "details",
                "details-course": str(self.active_course.pk),
                "details-full_name": full_name,
                "details-email": email,
                "details-phone": phone,
                "details-comment": comment,
            },
        )
        self.assertEqual(step_one.status_code, 200)
        self.assertContains(step_one, full_name)
        self.assertContains(step_one, self.active_course.title)

        confirm_step_field = self._wizard_step_field(step_one.content.decode("utf-8"))
        finish = self.client.post(
            reverse("pages:course_signup"),
            {
                confirm_step_field: "confirm",
                "confirm-consent_decision": "agree",
            },
            follow=True,
        )
        self.assertEqual(finish.status_code, 200)

    def test_signup_flow_creates_course_signup(self) -> None:
        before = CourseSignup.objects.count()

        self._run_signup_flow(
            full_name="Wizard User",
            email="wizard@example.com",
            phone="+79990000000",
            comment="Demo",
        )

        self.assertEqual(CourseSignup.objects.count(), before + 1)

    def test_repeated_identical_flow_does_not_duplicate_signup(self) -> None:
        self._run_signup_flow(
            full_name="Repeat User",
            email="repeat@example.com",
            phone="+79991112233",
            comment="Same payload",
        )
        first_count = CourseSignup.objects.count()

        self._run_signup_flow(
            full_name="Repeat User",
            email="repeat@example.com",
            phone="+79991112233",
            comment="Same payload",
        )

        self.assertEqual(CourseSignup.objects.count(), first_count)

    def test_declined_consent_does_not_create_signup(self) -> None:
        before = CourseSignup.objects.count()
        start = self.client.get(reverse("pages:course_signup"))
        step_field_name = self._wizard_step_field(start.content.decode("utf-8"))
        step_one = self.client.post(
            reverse("pages:course_signup"),
            {
                step_field_name: "details",
                "details-course": str(self.active_course.pk),
                "details-full_name": "Decline User",
                "details-email": "decline@example.com",
                "details-phone": "+79990000002",
                "details-comment": "",
            },
        )
        confirm_step_field = self._wizard_step_field(step_one.content.decode("utf-8"))
        finish = self.client.post(
            reverse("pages:course_signup"),
            {
                confirm_step_field: "confirm",
                "confirm-consent_decision": "decline",
            },
        )
        self.assertEqual(finish.status_code, 200)
        self.assertEqual(CourseSignup.objects.count(), before)


class CertificateRequestTests(ConsentBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user_model = get_user_model()
        manager = cast(Any, self.user_model.objects)
        self.user = manager.create_user(
            username="cert_user",
            email="cert@example.com",
            password="StrongPass123!",
            first_name="Иван",
            last_name="Иванов",
        )
        self.course = Course.objects.create(
            title="Python Backend Start",
            slug="python-backend-start-cert",
            short_description="Demo",
            description="Demo",
            is_active=True,
        )
        CourseSignup.objects.create(
            full_name="Иван Иванов",
            email="cert@example.com",
            phone="+79990000003",
            course=self.course,
            comment="Хочу учиться",
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_certificate_request_without_paper_consent_is_blocked(self) -> None:
        before = CertificateRequest.objects.count()
        response = self.client.post(
            reverse("pages:certificate_request"),
            {
                "full_name": "Иван Иванов",
                "birth_date": "1990-01-01",
                "email": "cert@example.com",
                "course_name": self.course.title,
                "comment": "Нужен электронный сертификат",
                "consent_decision": "agree",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(CertificateRequest.objects.count(), before)
        self.assertContains(
            response,
            "требуется бумажное подтверждение согласия",
            status_code=400,
        )

    def test_certificate_request_shows_pdf_download_link_for_verified_flow(
        self,
    ) -> None:
        response = self.client.get(reverse("pages:certificate_request"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "/consent/documents/certificate_issue/sample_certificate_issue_consent/pdf/",
        )

    def test_certificate_request_decline_does_not_create_record(self) -> None:
        before = CertificateRequest.objects.count()
        response = self.client.post(
            reverse("pages:certificate_request"),
            {
                "full_name": "Иван Иванов",
                "birth_date": "1990-01-01",
                "email": "cert@example.com",
                "course_name": self.course.title,
                "comment": "",
                "consent_decision": "decline",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(CertificateRequest.objects.count(), before)


class AllauthFlowTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user_model = get_user_model()

    def test_signup_login_logout_flow(self) -> None:
        signup_response = self.client.post(
            reverse("account_signup"),
            {
                "username": "demo_user",
                "email": "demo_user@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
            follow=True,
        )
        self.assertEqual(signup_response.status_code, 200)
        self.assertTrue(self.user_model.objects.filter(username="demo_user").exists())
        self.assertEqual(
            signup_response.request.get("PATH_INFO"), reverse("pages:profile")
        )

        logout_get = self.client.get(reverse("account_logout"))
        self.assertEqual(logout_get.status_code, 200)
        logout_response = self.client.post(reverse("account_logout"), follow=True)
        self.assertEqual(logout_response.status_code, 200)

        login_response = self.client.post(
            reverse("account_login"),
            {
                "login": "demo_user",
                "password": "StrongPass123!",
            },
            follow=True,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(
            login_response.request.get("PATH_INFO"), reverse("pages:profile")
        )


class LocalizationTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_language_switch_to_english(self) -> None:
        response = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("pages:home")},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Language"), "en")
        self.assertContains(response, "English")

    def test_contact_form_errors_are_english_after_switch(self) -> None:
        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("pages:contact")},
            follow=True,
        )
        response = self.client.post(
            reverse("pages:contact"),
            {
                "full_name": "",
                "email": "bad-email",
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Language"), "en")
        self.assertContains(response, "This field is required.")
