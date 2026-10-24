from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShippingAddress(BaseModel):
    line1: str
    postal_code: str
    city: str
    country: str


class OrderItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    order_id: str
    customer_id: str
    items: list[OrderItem]
    shipping_address: ShippingAddress


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    status: str
    attempts: int


class OrderDetailResponse(OrderResponse):
    last_error: str | None
    warehouse_reference: str | None
    next_retry_at: datetime | None
    created_at: datetime
    updated_at: datetime