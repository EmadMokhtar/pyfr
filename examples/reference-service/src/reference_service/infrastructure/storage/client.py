"""The S3 session and its client configuration.

Construction only, mirroring infrastructure/db/engine.py and
infrastructure/cache/client.py. The adapter beside it holds only storage
behaviour.

aioboto3's Session does NOT hold a connection: `session.client(...)` is an
async context manager that opens and closes one per use. That shapes
S3ReceiptStore — see its module docstring.
"""

from __future__ import annotations

import aioboto3
from botocore.config import Config

from reference_service.settings import StorageSettings


def build_s3_session(settings: StorageSettings) -> aioboto3.Session:
    """Build the session. Credentials come from settings, never the ambient
    environment.

    Passing them explicitly rather than letting botocore discover them means
    a misconfigured deployment fails with "no credentials configured"
    instead of silently picking up an unrelated instance role and writing
    receipts into somebody else's bucket.
    """
    return aioboto3.Session(
        aws_access_key_id=settings.access_key_id.get_secret_value(),
        aws_secret_access_key=settings.secret_access_key.get_secret_value(),
        region_name=settings.region,
    )


def build_client_config(settings: StorageSettings) -> Config:
    """Deadlines and retry policy for every S3 call.

    botocore's defaults are 60 seconds for both timeouts and a retry mode
    that keeps trying — numbers chosen for batch jobs, not for a request a
    person is waiting on. Left alone, a single unreachable bucket would hold
    an HTTP handler open for minutes.

    `max_attempts=2` is one retry, not none: an S3 call crosses a network
    and a single dropped connection is common enough to be worth one more
    try. More than that belongs behind a circuit breaker, which this
    dependency does not have — and unlike the payment gateway, an
    unavailable store costs one endpoint rather than the ability to take
    money.

    `s3={"addressing_style": "path"}` is what makes MinIO work. The default,
    virtual-host addressing, sends requests to
    `<bucket>.<endpoint>` — a hostname that does not resolve for MinIO,
    which serves buckets as PATHS under one host. Real S3 accepts both, so
    path style is correct for every provider rather than a local-only
    workaround.
    """
    return Config(
        connect_timeout=settings.connect_timeout_seconds,
        read_timeout=settings.read_timeout_seconds,
        retries={"max_attempts": 2, "mode": "standard"},
        s3={"addressing_style": "path"},
    )
