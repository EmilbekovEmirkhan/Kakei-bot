from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.init_db import init_db
from app.db.connection import close_pool
from app.services.line_service import init_http_client, close_http_client
from app.routers.webhook import router as webhook_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_http_client()
    yield
    await close_http_client()
    await close_pool()

app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)