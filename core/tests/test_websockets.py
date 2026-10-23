from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.sessions import CookieMiddleware
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase

from core.models.user import User, UserSession
from core.utils.cookies import get_auth_cookie_name
from core.websockets.auth import JWTCookieAuthMiddleware
from core.websockets.consumers import send_to_user
from core.websockets.routing import websocket_urlpatterns

application = CookieMiddleware(
    JWTCookieAuthMiddleware(URLRouter(websocket_urlpatterns))
)


class UserConsumerTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.access = self.client.cookies[get_auth_cookie_name()].value

    def communicator(self, cookie=""):
        return WebsocketCommunicator(
            application, "/ws/", headers=[(b"cookie", cookie.encode())]
        )

    async def test_anonymous_is_rejected(self):
        connected, code = await self.communicator().connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4401)

    async def test_logged_user_receives_pushes(self):
        ws = self.communicator(f"{get_auth_cookie_name()}={self.access}")
        connected, _ = await ws.connect()
        self.assertTrue(connected)

        await sync_to_async(send_to_user)(self.user.pk, {"title": "hi"})
        self.assertEqual(await ws.receive_json_from(), {"title": "hi"})
        await ws.disconnect()

    async def test_open_socket_stops_receiving_after_session_revocation(self):
        ws = self.communicator(f"{get_auth_cookie_name()}={self.access}")
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        await sync_to_async(UserSession.objects.filter(user=self.user).update)(
            is_active=False
        )
        await sync_to_async(send_to_user)(self.user.pk, {"title": "private"})
        event = await ws.receive_output(timeout=5)
        self.assertEqual(event, {"type": "websocket.close", "code": 4401})
        await ws.disconnect()
