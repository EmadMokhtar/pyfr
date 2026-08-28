"""Version 1 of the orders API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from reference_service.api.deps import GetOrderDep, PlaceOrderDep
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


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: UUID, fetch: GetOrderDep) -> OrderResponse:
    order = await fetch(OrderId(order_id))
    return to_response(order)
