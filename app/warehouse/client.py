from typing import Any

import httpx

from app.config import get_settings


class WarehouseClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.warehouse_base_url.rstrip("/")
        self._timeout = settings.warehouse_timeout_seconds

    async def send_order(
        self,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(
                f"{self._base_url}/warehouse/orders",
                json=payload,
                headers={
                    "Idempotency-Key": idempotency_key,
                },
            )