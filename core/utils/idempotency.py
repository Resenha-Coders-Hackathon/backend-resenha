import hashlib
import json
from functools import wraps

from django.core.cache import cache
from rest_framework.response import Response

from core.response_messages import MSG_IDEMPOTENCY_IN_PROGRESS

IDEMPOTENCY_TTL = 60 * 60 * 24


def idempotent_payment(method):
    """Cache successful payments only after DRF authenticates and checks CSRF."""

    @wraps(method)
    def wrapped(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return method(self, request, *args, **kwargs)

        digest = hashlib.sha256(
            f"{request.user.pk}:{request.method}:{request.path}:{key}".encode()
        ).hexdigest()
        body_digest = hashlib.sha256(
            json.dumps(request.data, sort_keys=True, default=str).encode()
        ).hexdigest()
        cache_key, lock_key = f"payment:{digest}", f"payment-lock:{digest}"
        if cached := cache.get(cache_key):
            previous_body, data, status = cached
            if previous_body != body_digest:
                return Response({"detail": MSG_IDEMPOTENCY_IN_PROGRESS}, status=409)
            return Response(
                data, status=status, headers={"Idempotent-Replayed": "true"}
            )

        if not cache.add(lock_key, True, timeout=60):
            return Response({"detail": MSG_IDEMPOTENCY_IN_PROGRESS}, status=409)
        try:
            response = method(self, request, *args, **kwargs)
            if 200 <= response.status_code < 300:
                cache.set(
                    cache_key,
                    (body_digest, response.data, response.status_code),
                    IDEMPOTENCY_TTL,
                )
            return response
        finally:
            cache.delete(lock_key)

    return wrapped
