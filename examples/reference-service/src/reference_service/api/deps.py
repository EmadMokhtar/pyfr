"""FastAPI dependencies.

These read from `app.state`, which the lifespan populated. Tests replace them
with `app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from reference_service.container import Container
from reference_service.domain.repositories import OrderRepository
from reference_service.service.order import GetOrder, PlaceOrder


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_orders(container: ContainerDep) -> OrderRepository:
    return container.orders


OrdersDep = Annotated[OrderRepository, Depends(get_orders)]


def get_place_order(orders: OrdersDep) -> PlaceOrder:
    return PlaceOrder(orders)


def get_get_order(orders: OrdersDep) -> GetOrder:
    return GetOrder(orders)


PlaceOrderDep = Annotated[PlaceOrder, Depends(get_place_order)]
GetOrderDep = Annotated[GetOrder, Depends(get_get_order)]
