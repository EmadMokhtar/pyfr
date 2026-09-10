"""FastAPI dependencies.

These read from `app.state`, which the lifespan populated. Tests replace them
with `app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from reference_service.container import Container
from reference_service.domain.payments import PaymentGateway
from reference_service.domain.receipts import ReceiptStore
from reference_service.domain.repositories import OrderRepository
from reference_service.services.order import GetOrder, PlaceOrder
from reference_service.services.receipt import GetReceipt


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_orders(container: ContainerDep) -> OrderRepository:
    return container.orders


OrdersDep = Annotated[OrderRepository, Depends(get_orders)]


def get_payments(container: ContainerDep) -> PaymentGateway:
    return container.payments


PaymentsDep = Annotated[PaymentGateway, Depends(get_payments)]


def get_receipts(container: ContainerDep) -> ReceiptStore:
    return container.receipts


ReceiptStoreDep = Annotated[ReceiptStore, Depends(get_receipts)]


def get_place_order(orders: OrdersDep, payments: PaymentsDep) -> PlaceOrder:
    return PlaceOrder(orders, payments)


def get_get_order(orders: OrdersDep) -> GetOrder:
    return GetOrder(orders)


def get_get_receipt(orders: OrdersDep, receipts: ReceiptStoreDep) -> GetReceipt:
    return GetReceipt(orders, receipts)


PlaceOrderDep = Annotated[PlaceOrder, Depends(get_place_order)]
GetOrderDep = Annotated[GetOrder, Depends(get_get_order)]
GetReceiptDep = Annotated[GetReceipt, Depends(get_get_receipt)]
