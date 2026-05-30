# main.py
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router, init_db
from app.logger import get_logger

logger = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AI Knowledge Workspace",
    description="Enterprise AI knowledge base for teams",
    version="1.0.0",
    lifespan=lifespan
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request logging middleware ────────────────────────────────────────
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    logger.info("request_started", extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path
    })
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        logger.error("request_failed", extra={
            "request_id": request_id,
            "error": str(e)
        })
        raise
    logger.info("request_completed", extra={
        "request_id": request_id,
        "status_code": status_code,
        "duration_ms": round((time.time() - start) * 1000, 2)
    })
    return response


app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)