import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Order
from app.schemas import OrderCreate, OrderDetailResponse, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_202_ACCEPTED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
) -> OrderResponse:
    existing_order = (
        db.query(Order)
        .filter(Order.order_id == payload.order_id)
        .one_or_none()
    )

    if existing_order is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An order with this order_id already exists.",
        )

    order = Order(
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        payload=payload.model_dump(),
        status="PENDING",
        attempts=0,
    )

    db.add(order)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An order with this order_id already exists.",
        ) from exc

    db.refresh(order)
    return OrderResponse.model_validate(order)


@router.get("/{order_internal_id}", response_model=OrderDetailResponse)
def get_order(
    order_internal_id: str,
    db: Session = Depends(get_db),
) -> OrderDetailResponse:
    order = db.get(Order, order_internal_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    return OrderDetailResponse.model_validate(order)


@router.get("", response_model=list[OrderDetailResponse])
def list_orders(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
) -> list[OrderDetailResponse]:
    query = db.query(Order)

    if status_filter is not None:
        query = query.filter(Order.status == status_filter.upper())

    orders = query.order_by(Order.created_at.desc()).all()
    return [OrderDetailResponse.model_validate(order) for order in orders]


@router.post("/{order_internal_id}/retry", response_model=OrderResponse)
def retry_order(
    order_internal_id: str,
    db: Session = Depends(get_db),
) -> OrderResponse:
    order = db.get(Order, order_internal_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    if order.status not in {"FAILED", "RETRYING"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed or retrying orders can be retried manually.",
        )

    order.status = "PENDING"
    order.next_retry_at = None
    order.last_error = None

    db.commit()
    db.refresh(order)

    return OrderResponse.model_validate(order)