"""Version 1 of the orders API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from reference_service.api.deps import GetOrderDep, PlaceOrderDep
from reference_service.api.errors import problem_response
from reference_service.api.v1.mappers import to_command, to_response
from reference_service.api.v1.schemas import OrderResponse, PlaceOrderRequest
from reference_service.domain.order import OrderId

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
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
    # Not in main.py's global DEFAULT_PROBLEM_RESPONSES: unlike 422 and 500,
    # only this route can actually raise OrderNotFoundError, so documenting
    # 404 here — and nowhere else — is what makes the schema describe what
    # each route actually does, rather than a blanket approximation.
    responses={status.HTTP_404_NOT_FOUND: problem_response("Order not found")},
)
async def get_order(order_id: UUID, fetch: GetOrderDep) -> OrderResponse:
    order = await fetch(OrderId(order_id))
    return to_response(order)
