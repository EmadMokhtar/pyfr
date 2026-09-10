"""Version 1 of the orders API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from reference_service.api.deps import GetOrderDep, GetReceiptDep, PlaceOrderDep
from reference_service.api.errors import problem_response
from reference_service.api.v1.mappers import to_command, to_response
from reference_service.api.v1.schemas import (
    OrderResponse,
    PlaceOrderRequest,
    ReceiptResponse,
)
from reference_service.domain.order import OrderId
from reference_service.domain.receipt_render import RECEIPT_MEDIA_TYPE

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_402_PAYMENT_REQUIRED: problem_response("Payment declined"),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_response(
            "Payment provider unavailable"
        ),
    },
)
async def place_order(
    request: PlaceOrderRequest,
    place: PlaceOrderDep,
    response: Response,
) -> OrderResponse:
    order = await place(to_command(request))
    response.headers["Location"] = f"/api/v1/orders/{order.id}"
    return to_response(order)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    # main.py's global DEFAULT_PROBLEM_RESPONSES already documents a 404 —
    # but that one is "no route matched this path at all", reachable under
    # any prefix, from api/errors.py's `_http_exception` handler. THIS 404
    # is a different thing: "this specific order id does not exist",
    # raised only here, by OrderNotFoundError, and carrying a different
    # `type` (`.../order_not_found` vs the global one's `.../http_error`).
    # Only this route can raise it, so documenting it here — on top of,
    # not instead of, the global entry — is what makes the schema describe
    # what THIS route actually does. See api/errors.py's
    # DEFAULT_PROBLEM_RESPONSES comment for the other half of this pair.
    responses={status.HTTP_404_NOT_FOUND: problem_response("Order not found")},
)
async def get_order(order_id: UUID, fetch: GetOrderDep) -> OrderResponse:
    order = await fetch(OrderId(order_id))
    return to_response(order)


@router.get(
    "/{order_id}/receipt",
    # A raw Response, not a response_model. The endpoint returns the exact
    # bytes that were stored; handing them to a response_model would
    # re-serialise the document and the receipt a client reads would no
    # longer be the object that was written. `responses` below is what
    # publishes the shape instead.
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "model": ReceiptResponse,
            "description": "The receipt for this order",
            "content": {RECEIPT_MEDIA_TYPE: {}},
        },
        status.HTTP_404_NOT_FOUND: problem_response("Order not found"),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_response(
            "Receipt storage unavailable"
        ),
    },
)
async def get_receipt(order_id: UUID, fetch: GetReceiptDep) -> Response:
    """Serve the receipt, rendering and storing it on the first request.

    Deliberately not a redirect to a presigned URL. A presigned URL is
    signed for the storage endpoint's own hostname, which inside compose is
    `minio:9000` — a name that resolves only on the compose network, so the
    link would be dead in a browser on the host. Streaming works identically
    from a laptop, a container and a test.
    """
    content = await fetch(OrderId(order_id))
    return Response(content=content, media_type=RECEIPT_MEDIA_TYPE)
