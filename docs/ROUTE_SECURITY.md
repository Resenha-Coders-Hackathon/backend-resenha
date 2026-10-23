# Server route security

Reviewed on 2026-10-23 after rebasing the working branches onto `origin/dev`.

## Route policy

`app/urls.py` wires Django admin, staff API documentation and the versioned API.
`core/urls.py` wires account endpoints and includes each domain's `urls.py`.
Existing URL paths and names are preserved; `/api/v1/csrf/` is added.

DRF requires `IsAuthenticated` by default. Public endpoints must explicitly set
`authentication_classes = []` and `permission_classes = [AllowAny]`.

| Endpoints | Access and checks |
| --- | --- |
| `GET /api/v1/csrf/` | Public; initializes the CSRF cookie; no-store response |
| `POST /api/v1/login/`, `login/google/` | Public credentials exchange; CSRF and `auth` throttle; JWTs only in HttpOnly cookies; rotates CSRF |
| `POST /api/v1/refresh/` | Refresh cookie plus CSRF; active session belonging to the token's user; atomic rotation with a session row lock; `auth` throttle |
| `POST /api/v1/registration/{request,verify,confirm}/` | Public; one-time codes and `auth` throttle |
| `POST /api/v1/password-reset/{request,verify,confirm}/` | Public; one-time codes and `auth` throttle |
| `POST /api/v1/payments/webhook/` | Public provider callback; validates payload; only looks up known payment IDs; trusts provider state and verifies the local reference and provider ID |
| Remaining `/api/v1/` routes | Valid JWT cookie, active user and active session matching both JWT JTI and user ID; CSRF on writes |
| `/api/docs/{urls,schema}/` | Staff user via JWT or Django admin session |
| `/admin/` | Django staff session and Django CSRF checks |
| `/api/v1/ai/test/` | Staff JWT; registered only with `DEBUG=True` |
| `/ws/` | Cookie authentication and origin validation; revalidates the session before incoming commands and outgoing events; checks current channel access before chat delivery |

CORS uses the trusted-origin allowlist. `CSRF_TRUSTED_ORIGINS` from the environment
extends both CSRF and CORS configuration in all environments. Production settings
require secure cookies when `USE_HTTPS=True`; session cookies use `SameSite=Lax`.

Domain authorization remains in services: organization memberships and role hierarchy,
sector roles inherited through teams, task/checklist/comment/link permissions,
channel participation, and ownership of notifications, devices, payments and sessions.
Chat recipients must still belong to the active organization. Task cards are accepted
and displayed only when every current channel recipient can access their sector.

## Client contract

Before either login method, call `GET /api/v1/csrf/` with credentials, then send
`X-CSRFToken` using the `csrftoken` cookie. After login use the newly rotated cookie.
Refresh also requires that header, even when the access cookie has expired.
The shared frontend auth service bootstraps CSRF; axios already sends the header.
The login response body contains only `detail`; tokens stay in HttpOnly cookies.

CSRF validation on login follows the [DRF authentication guidance](https://www.django-rest-framework.org/api-guide/authentication/).
Token rotation follows [Django's CSRF behavior](https://docs.djangoproject.com/en/6.0/ref/csrf/).

Idempotency is restricted to authenticated payment creation. The decorator executes
after DRF authentication, permission, CSRF and throttle checks. Successful JSON
responses are cached by user, method, path and key for 24 hours; a different request
body with the same key returns 409. Public authentication responses, failures and
AI reports are never cached. Redis is needed to share keys across server processes.

## Verification and deployment

`core/tests/test_route_security.py` enumerates registered API methods to reject
anonymous access and enforce the explicit public-route list. It also exercises
login, Google login, refresh, session ownership, revocation and untrusted origins
with CSRF enforcement enabled. Payment tests cover replay isolation, changed bodies,
revoked sessions, CSRF, malformed callbacks and mismatched payment references.
Chat and WebSocket regression tests cover private cards and removed memberships.

Run the Django suite with `FIREBASE_CREDENTIALS=` and a non-secret test Fernet key.
Deploy backend and frontend together because login now requires CSRF initialization.
No model migration or new dependency is introduced by the security changes.
Dependencies brought by the rebase must be installed from the existing lockfile.

No live payment, Google, Gemini or Firebase request is needed for these checks.
No production deployment or browser acceptance is included. Provider signature
verification is not configured for the webhook; its safety relies on authoritative
provider lookup and matching an existing local payment, with global throttling.
The in-memory Channels layer still supports a single web process only.

Final local checks passed on this revision:

- Django system check and all 259 backend tests (148.850 seconds).
- Ruff check for the whole backend; format check for all 23 changed Python files.
- All 9 focused frontend tests, type check, lint and production/PWA build.
- Live development HTTP checks: CSRF initialization returns 204, anonymous profile
  and schema requests return 401, and login without CSRF returns 403.
- Rebase bases: backend `7f930a1`, frontend `508cf46`; both local `dev` branches
  match their fetched `origin/dev`. Security changes remain uncommitted locally.
