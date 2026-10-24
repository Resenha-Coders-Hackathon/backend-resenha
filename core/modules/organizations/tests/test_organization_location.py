from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.organizations.models.organization import Organization


class OrganizationLocationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="location@example.invalid", password="Location-test!2026"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_location_is_saved_and_returned(self):
        location = {"latitude": -26.3044, "longitude": -48.8464}
        response = self.client.post(
            "/api/v1/organizations/",
            {"name": "Located", "location": location},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        organization = Organization.objects.get(pk=response.json()["id"])
        self.assertEqual(organization.location, location)
        detail = self.client.get(f"/api/v1/organizations/{organization.pk}/")
        self.assertEqual(detail.json()["location"], location)
        incomplete = self.client.patch(
            f"/api/v1/organizations/{organization.pk}/",
            {"location": {"latitude": 0}},
            format="json",
        )
        self.assertEqual(incomplete.status_code, 400, incomplete.content)
        cleared = self.client.patch(
            f"/api/v1/organizations/{organization.pk}/",
            {"location": None},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        organization.refresh_from_db()
        self.assertIsNone(organization.location)

    def test_undefined_location_is_optional(self):
        for payload in ({"name": "Legacy"}, {"name": "Undefined", "location": None}):
            response = self.client.post(
                "/api/v1/organizations/", payload, format="json"
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertIsNone(response.json()["location"])

    def test_invalid_or_incomplete_coordinates_are_rejected(self):
        for location in (
            {},
            {"latitude": 0},
            {"longitude": 0},
            {"latitude": 91, "longitude": 0},
            {"latitude": 0, "longitude": -181},
            {"latitude": "NaN", "longitude": 0},
            {"latitude": None, "longitude": 0},
            "invalid",
        ):
            with self.subTest(location=location):
                response = self.client.post(
                    "/api/v1/organizations/",
                    {"name": "Invalid", "location": location},
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.content)

    def test_zero_coordinates_are_valid(self):
        response = self.client.post(
            "/api/v1/organizations/",
            {"name": "Zero", "location": {"latitude": 0, "longitude": 0}},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
