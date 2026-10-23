from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User, UserSession


@override_settings(ALLOWED_HOSTS=["testserver"])
class PaymentIdempotencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("payer@example.com", "S3cure-pass!")
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.get("/api/v1/csrf/")
        self.client.post(
            "/api/v1/login/",
            {"email": self.user.email, "password": "S3cure-pass!"},
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.csrf = self.client.cookies["csrftoken"].value
        self.create = patch(
            "core.modules.payments.views.payment.PaymentService.create_pix_payment",
            return_value={"id": "payment-id", "qr_code": "pix-code"},
        ).start()
        self.addCleanup(patch.stopall)

    def pay(self, **headers):
        return self.client.post(
            "/api/v1/payments/",
            {"title": "Subscription", "cpf": "12345678901", "name": "A User"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="one-payment",
            **headers,
        )

    def test_retry_replays_success_after_authentication(self):
        first = self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        second = self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.create.assert_called_once()

    def test_cached_response_requires_csrf(self):
        self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(self.pay().status_code, 403)
        self.create.assert_called_once()

    def test_form_payment_with_csrf_can_be_retried(self):
        for _ in range(2):
            response = self.client.post(
                "/api/v1/payments/",
                {"title": "Subscription", "cpf": "12345678901", "name": "A User"},
                HTTP_IDEMPOTENCY_KEY="form-payment",
                HTTP_X_CSRFTOKEN=self.csrf,
            )
            self.assertEqual(response.status_code, 201)
        self.create.assert_called_once()

    def test_revoked_session_cannot_replay_cached_payment(self):
        self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        UserSession.objects.update(is_active=False)
        self.assertEqual(self.pay(HTTP_X_CSRFTOKEN=self.csrf).status_code, 401)
        self.create.assert_called_once()

    def test_another_user_cannot_replay_payment(self):
        self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        other = User.objects.create_user("other@example.com", "S3cure-pass!")
        self.client.force_authenticate(other)
        self.assertEqual(self.pay().status_code, 201)
        self.assertEqual(self.create.call_count, 2)

    def test_same_key_with_changed_body_is_rejected(self):
        self.pay(HTTP_X_CSRFTOKEN=self.csrf)
        response = self.client.post(
            "/api/v1/payments/",
            {"title": "different"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="one-payment",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 409)
        self.create.assert_called_once()

    def test_public_login_response_is_never_cached(self):
        for _ in range(2):
            response = self.client.post(
                "/api/v1/login/",
                {"email": self.user.email, "password": "S3cure-pass!"},
                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
                HTTP_IDEMPOTENCY_KEY="same-login",
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("access_token", response.cookies)
            self.assertNotIn("Idempotent-Replayed", response)
