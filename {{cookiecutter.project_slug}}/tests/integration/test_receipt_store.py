"""The S3 receipt store against a real MinIO.

This module carries its own `pytestmark` with `loop_scope="session"`, per
the rule in this directory's conftest.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from reference_service.domain.order import OrderId
from reference_service.infrastructure.errors import StorageUnavailableError
from reference_service.infrastructure.storage.receipt_store import (
    S3ReceiptStore,
    receipt_key,
)
from reference_service.settings import StorageSettings

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_a_receipt_round_trips(receipt_store: S3ReceiptStore) -> None:
    order_id = OrderId(uuid4())
    content = b'{"schema_version":1,"order_id":"x"}'

    await receipt_store.put(order_id, content)

    assert await receipt_store.get(order_id) == content


async def test_an_absent_object_is_none_not_an_error(
    receipt_store: S3ReceiptStore,
) -> None:
    """The distinction the port is built around: None means 'render it',
    an error means 'come back later'. Collapsing them would make an outage
    look like an empty bucket."""
    assert await receipt_store.get(OrderId(uuid4())) is None


async def test_a_put_replaces_an_existing_object(
    receipt_store: S3ReceiptStore,
) -> None:
    order_id = OrderId(uuid4())
    await receipt_store.put(order_id, b"first")

    await receipt_store.put(order_id, b"second")

    assert await receipt_store.get(order_id) == b"second"


async def test_bytes_come_back_byte_identical(
    receipt_store: S3ReceiptStore,
) -> None:
    """A receipt is served as the exact object that was stored. Any
    transcoding — a content-encoding negotiated on the way out, a stray
    decode to str — would show up here."""
    order_id = OrderId(uuid4())
    content = "receipt for € 21,00 — naïve".encode()

    await receipt_store.put(order_id, content)

    assert await receipt_store.get(order_id) == content


async def test_the_key_layout_is_what_the_adapter_documents(
    receipt_store: S3ReceiptStore,
    storage_settings: StorageSettings,
    minio_container: object,
) -> None:
    """Pins the on-disk layout. Objects outlive deployments, so a silent
    change to the key scheme orphans every receipt already written."""
    order_id = OrderId(uuid4())
    await receipt_store.put(order_id, b"{}")

    from testcontainers.community.minio import MinioContainer

    assert isinstance(minio_container, MinioContainer)
    names = [
        obj.object_name
        for obj in minio_container.get_client().list_objects(
            storage_settings.bucket, recursive=True
        )
    ]

    assert receipt_key(order_id) in names
    assert receipt_key(order_id).startswith("receipts/v1/")


async def test_a_missing_bucket_is_an_error_not_an_empty_result(
    storage_settings: StorageSettings,
) -> None:
    """NoSuchBucket must NOT be swallowed as None. If it were, every request
    would re-render and re-attempt a write that cannot succeed, and the
    service would look healthy while storing nothing."""
    from reference_service.infrastructure.storage.client import (
        build_client_config,
        build_s3_session,
    )

    wrong = storage_settings.model_copy(update={"bucket": "does-not-exist"})
    store = S3ReceiptStore(build_s3_session(wrong), build_client_config(wrong), wrong)

    with pytest.raises(StorageUnavailableError):
        await store.get(OrderId(uuid4()))


async def test_an_unreachable_endpoint_raises_storage_unavailable(
    storage_settings: StorageSettings,
) -> None:
    """Port 1 is reserved and never has a listener, so this exercises the
    BotoCoreError branch — connection failures, which share no base class
    with ClientError and would otherwise escape as a 500."""
    from reference_service.infrastructure.storage.client import (
        build_client_config,
        build_s3_session,
    )

    dead = storage_settings.model_copy(update={"endpoint_url": "http://127.0.0.1:1"})
    store = S3ReceiptStore(build_s3_session(dead), build_client_config(dead), dead)

    with pytest.raises(StorageUnavailableError):
        await store.get(OrderId(uuid4()))

    with pytest.raises(StorageUnavailableError):
        await store.put(OrderId(uuid4()), b"{}")
