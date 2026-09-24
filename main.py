from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os

# Supports both `uvicorn backend.main:app` from the project root (also how
# the test suite imports this module) and `cd backend && uvicorn main:app`
# as the README documents - the second form previously crashed with
# "ModuleNotFoundError: No module named 'backend'" because main.py only had
# the absolute-import form, which only resolves when the project root (the
# parent of backend/) is on sys.path.
try:
    from backend.api.routes.train import router as train_router
    from backend.api.routes.trains import router as trains_search_router
    from backend.api.routes.alerts import router as alerts_router
    from backend.api.routes.model import router as model_router
    from backend.api.websocket import router as websocket_router
    from backend.services.train_simulator import run_simulation_loop
    from backend.database.connection import init_db
    from backend.database.seed import seed_known_trains
except ImportError:
    from api.routes.train import router as train_router
    from api.routes.trains import router as trains_search_router
    from api.routes.alerts import router as alerts_router
    from api.routes.model import router as model_router
    from api.websocket import router as websocket_router
    from services.train_simulator import run_simulation_loop
    from database.connection import init_db
    from database.seed import seed_known_trains


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (SQLite locally, or the Postgres instance Render's
    # DATABASE_URL points at) and register every train that ships
    # route+schedule data on disk, so it's searchable immediately.
    init_db()
    seed_known_trains()

    # Ticks every active train simulator on a fixed cadence so telemetry
    # keeps advancing whether or not a websocket client is connected -
    # plain REST polling of /telemetry sees live movement too - and logs
    # each tick to SQL (TelemetryLog).
    task = asyncio.create_task(run_simulation_loop())
    yield
    task.cancel()


app = FastAPI(
    title="YatraSuchak API",
    version="0.2.0",
    description="Dynamic ETA forecasting backend for coaching trains, backed by SQL and a model trained on its own live telemetry.",
    lifespan=lifespan,
)

# CORS: allow the configured frontend origin(s) plus local dev. Set
# FRONTEND_ORIGIN on Render (e.g. to your deployed frontend's URL) to
# tighten this beyond "*" for a real deployment.
_extra_origin = os.environ.get("FRONTEND_ORIGIN")
_allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if _extra_origin:
    _allow_origins.append(_extra_origin)
_allow_origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(train_router)
app.include_router(trains_search_router)
app.include_router(alerts_router)
app.include_router(model_router)
app.include_router(websocket_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "YatraSuchak"}
