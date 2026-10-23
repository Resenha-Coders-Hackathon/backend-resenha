import re
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from core.models.user import User, UserSession

PUBLIC_ROUTES = {
    "csrf",
    "login",
    "login-google",
    "refresh",
    "registration-request",
    "registration-verify",
    "registration-confirm",
    "password-reset-request",
    "password-reset-verify",
    "password-reset-confirm",
    "webhook",
}


def api_routes(patterns, prefix=""):
    for pattern in patterns:
        path = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from api_routes(pattern.url_patterns, path)
        else:
            yield path, pattern


@override_settings(ALLOWED_HOSTS=["testserver"])
class RoutePolicyTests(TestCase):
    def test_authentication_is_the_default(self):
        self.assertEqual(APIView.permission_classes, [IsAuthenticated])

    def test_all_registered_api_methods_require_auth_except_explicit_public_routes(
        self,
    ):
        public = set()
        for path, pattern in api_routes(get_resolver("core.urls").url_patterns):
            view = pattern.callback.cls
            if AllowAny in view.permission_classes:
                public.add(pattern.name)
                self.assertIn(pattern.name, PUBLIC_ROUTES, path)
                self.assertEqual(view.authentication_classes, [], path)
                continue
            url = "/api/v1/" + re.sub(
                r"<(?:(\w+):)?\w+>",
                lambda match: "1" if match[1] == "int" else str(uuid4()),
                path,
            )
            for method in view.http_method_names:
                if method in ("head", "options") or not hasattr(view, method):
                    continue
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 401)
        self.assertEqual(public, PUBLIC_ROUTES)

    def test_docs_require_staff(self):
        self.assertEqual(self.client.get("/api/docs/urls/").status_code, 401)
        self.assertEqual(self.client.get("/api/docs/schema/").status_code, 401)
        client = APIClient()
        user = User.objects.create_user("reader@example.com", "S3cure-pass!")
        client.force_authenticate(user)
        self.assertEqual(client.get("/api/docs/urls/").status_code, 403)
        user.is_staff = True
        self.assertEqual(client.get("/api/docs/urls/").status_code, 200)


@override_settings(ALLOWED_HOSTS=["testserver"])
class CookieSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("secure@example.com", "S3cure-pass!")
        self.client = APIClient(enforce_csrf_checks=True)
        self.credentials = {"email": self.user.email, "password": "S3cure-pass!"}

    def login(self):
        self.client.get("/api/v1/csrf/")
        return self.client.post(
            "/api/v1/login/",
            self.credentials,
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

    def test_login_requires_csrf_even_for_anonymous_user(self):
        response = self.client.post("/api/v1/login/", self.credentials)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserSession.objects.exists())

    def test_login_only_exposes_jwts_in_httponly_cookies_and_rotates_csrf(self):
        self.client.get("/api/v1/csrf/")
        previous_csrf = self.client.cookies["csrftoken"].value
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertTrue(response.cookies["access_token"]["httponly"])
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        self.assertNotEqual(previous_csrf, self.client.cookies["csrftoken"].value)

    def test_google_login_requires_csrf(self):
        response = self.client.post("/api/v1/login/google/", {"credential": "token"})
        self.assertEqual(response.status_code, 403)

    def test_refresh_requires_csrf_and_accepts_missing_access_cookie(self):
        self.login()
        del self.client.cookies["access_token"]
        previous_jti = UserSession.objects.get().refresh_jti
        response = self.client.post("/api/v1/refresh/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(UserSession.objects.get().refresh_jti, previous_jti)
        response = self.client.post(
            "/api/v1/refresh/",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(UserSession.objects.get().refresh_jti, previous_jti)

    def test_untrusted_origin_cannot_write_with_valid_csrf(self):
        self.login()
        response = self.client.post(
            "/api/v1/refresh/",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)

    def test_access_token_must_belong_to_session_owner(self):
        self.login()
        other = User.objects.create_user("other@example.com", "S3cure-pass!")
        token = AccessToken(self.client.cookies["access_token"].value)
        token["user_id"] = str(other.pk)
        self.client.cookies["access_token"] = str(token)
        self.assertEqual(self.client.get("/api/v1/users/me/").status_code, 401)

    def test_revoked_session_cannot_read_or_refresh(self):
        self.login()
        UserSession.objects.update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/users/me/").status_code, 401)
        response = self.client.post(
            "/api/v1/refresh/",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 401)
