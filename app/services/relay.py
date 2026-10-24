import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Order
from app.warehouse.client import WarehouseClient

logger = logging.getLogger("order-relay")

RETRYABLE_HTTP_STATUS_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}


def _is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUS_CODES


def _mark_retrying(
    order: Order,
    error_message: str,
) -> None:
    settings = get_settings()

    if order.attempts >= settings.max_attempts:
        order.status = "FAILED"
        order.next_retry_at = None
    else:
        delay_seconds = settings.retry_base_delay_seconds * (
            2 ** (order.attempts - 1)
        )
        order.status = "RETRYING"
        order.next_retry_at = datetime.utcnow() + timedelta(
            seconds=delay_seconds,
        )

    order.last_error = error_message


async def process_due_orders(db: Session) -> None:
    settings = get_settings()
    now = datetime.utcnow()

    orders = (
        db.query(Order)
        .filter(
            Order.status.in_(["PENDING", "RETRYING"]),
            (
                Order.next_retry_at.is_(None)
                | (Order.next_retry_at <= now)
            ),
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    if not orders:
        return

    warehouse_client = WarehouseClient()

    for order in orders:
        order.status = "PROCESSING"
        order.attempts += 1
        db.commit()

        try:
            response = await warehouse_client.send_order(
                payload=order.payload,
                idempotency_key=order.order_id,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            db.refresh(order)
            _mark_retrying(
                order,
                f"Warehouse request failed: {exc.__class__.__name__}",
            )
            db.commit()
            continue

        if 200 <= response.status_code < 300:
            try:
                response_payload = response.json()
                warehouse_reference = response_payload.get(
                    "warehouse_reference",
                )
            except ValueError:
                warehouse_reference = None

            order.status = "SENT"
            order.last_error = None
            order.next_retry_at = None
            order.warehouse_reference = warehouse_reference
            db.commit()
            continue

        if _is_retryable_status(response.status_code):
            db.refresh(order)
            _mark_retrying(
                order,
                f"Warehouse returned retryable HTTP {response.status_code}.",
            )
            db.commit()
            continue

        order.status = "FAILED"
        order.next_retry_at = None
        order.last_error = (
            f"Warehouse returned non-retryable HTTP {response.status_code}."
        )
        db.commit()