import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.connection import init_database, sync_dataset_aliases
from app.routers import assets, chat, dashboards, datasets, review, spaces, upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_database()
    logging.info("Database initialized")
    n = sync_dataset_aliases()
    if n:
        logging.info(f"Created/refreshed {n} dataset alias view(s)")
    yield
    # Shutdown
    logging.info("Shutting down")


app = FastAPI(
    title="Space Dashboard",
    description="AI-powered workspace for dynamic dashboard creation from Excel data",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(review.router)
app.include_router(datasets.router)
app.include_router(chat.router)
app.include_router(spaces.router)
app.include_router(dashboards.router)
app.include_router(assets.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
