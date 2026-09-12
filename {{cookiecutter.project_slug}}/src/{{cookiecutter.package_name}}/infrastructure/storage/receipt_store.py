"""The S3-compatible receipt store.

One adapter for every S3-compatible provider — Amazon S3, MinIO, Cloudflare
R2, Ceph, Backblaze B2 — distinguished only by StorageSettings.endpoint_url
(spec 9.1). There is deliberately no provider branch anywhere below.

A client per operation, not one held for the process's lifetime. That looks
wasteful and is not: aioboto3's `session.client()` is an async context
manager whose exit closes the underlying aiohttp connector, and a client
created once at startup outlives the event loop it was bound to, which
surfaces later as `RuntimeError: Event loop is closed` on the first call
after a reconnect. botocore pools sockets underneath, so the per-call cost
is object construction rather than a new TCP connection. The alternative —
an `AsyncExitStack` held on the container — was considered and rejected: it
buys a small saving and costs a lifetime that has to be correct across
startup, shutdown and every test fixture.
"""

from __future__ import annotations

import aioboto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from {{ cookiecutter.package_name }}.domain.order import OrderId
from {{ cookiecutter.package_name }}.infrastructure.errors import StorageUnavailableError
from {{ cookiecutter.package_name }}.settings import StorageSettings

_logger = structlog.get_logger(__name__)

# The `v1` is a schema generation, matching the cache's key prefix and
# RECEIPT_SCHEMA_VERSION. A receipt's shape can change; bumping this makes
# the next request render the new shape under a new key instead of serving
# a stored document that no longer matches the published contract.
KEY_PREFIX = "receipts/v1/"


def receipt_key(order_id: OrderId) -> str:
    return f"{KEY_PREFIX}{order_id}.json"


class S3ReceiptStore:
    def __init__(
        self,
        session: aioboto3.Session,
        config: Config,
        settings: StorageSettings,
    ) -> None:
        self._session = session
        self._config = config
        self._bucket = settings.bucket
        self._endpoint_url = (
            str(settings.endpoint_url) if settings.endpoint_url is not None else None
        )

    def _client(self):
        return self._session.client(
            "s3", endpoint_url=self._endpoint_url, config=self._config
        )

    async def get(self, order_id: OrderId) -> bytes | None:
        key = receipt_key(order_id)
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body: bytes = await response["Body"].read()
                return body
        except ClientError as exc:
            # A missing object is NOT an error — it is the ordinary state of
            # every order nobody has asked about, and the port says so by
            # returning None. Two distinct codes mean "not there": NoSuchKey
            # for an absent object, and 404 for a HEAD-shaped response.
            # NoSuchBucket deliberately does NOT land here: a missing bucket
            # is a deployment fault, not an empty one, and returning None
            # for it would make every request re-render and silently
            # re-attempt a write that cannot succeed.
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404"}:
                return None
            _logger.warning("storage.get_failed", key=key, code=code, exc_info=True)
            raise StorageUnavailableError(f"could not read receipt {key}") from exc
        except BotoCoreError as exc:
            # Connection failures, timeouts, DNS — everything below the HTTP
            # layer. BotoCoreError and ClientError share no base class other
            # than Exception, so both clauses are required; catching only
            # ClientError would let a connection timeout escape as itself and
            # reach the catch-all handler as a 500.
            _logger.warning("storage.get_failed", key=key, exc_info=True)
            raise StorageUnavailableError(f"could not read receipt {key}") from exc

    async def put(self, order_id: OrderId, content: bytes) -> None:
        key = receipt_key(order_id)
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentType="application/json",
                )
        except (BotoCoreError, ClientError) as exc:
            _logger.warning("storage.put_failed", key=key, exc_info=True)
            raise StorageUnavailableError(f"could not write receipt {key}") from exc
