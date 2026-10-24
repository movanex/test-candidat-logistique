import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.orders import router as orders_router
from app.config import get_settings
from app.db.database import SessionLocal, init_db
from app.services.relay import process_due_orders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-relay")

settings = get_settings()


async def dispatch_pending_orders() -> None:
    while True:
        try:
            with SessionLocal() as db:
                await process_due_orders(db)
        except Exception:
            logger.exception("Unexpected error while processing orders.")

        await asyncio.sleep(settings.dispatch_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    dispatcher_task = asyncio.create_task(dispatch_pending_orders())

    yield

    dispatcher_task.cancel()

    try:
        await dispatcher_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Reliable Order Relay Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(orders_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}