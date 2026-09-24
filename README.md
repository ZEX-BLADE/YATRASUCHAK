# YatraSuchak — SIH 2026 Starter Project

Problem Statement: **Dynamic Forecast of Expected Time of Arrival (ETA) for Coaching Trains**  
Architecture: GNSS/RTIS + signalling + historical data → validation/data fusion → delay features → ML ETA → passenger/station/control-room dashboard.

## Included

- FastAPI backend, with real-time telemetry persisted to SQL (Postgres or SQLite)
- REST endpoints
  - `GET /health`
  - `POST /api/train/start`
  - `GET /api/train/{train_no}/telemetry`
  - `GET /api/train/{train_no}/schedule`
  - `GET /api/train/{train_no}/route`
  - `GET /api/train/{train_no}/eta`
  - `GET /api/train/{train_no}/eta/stations`
  - `POST /api/train/{train_no}/event`
  - `GET /api/trains/search`, `GET /api/trains`, `GET /api/trains/{train_no}`, `GET /api/trains/{train_no}/history`
  - `GET /api/model/status`, `POST /api/model/retrain`
- WebSocket: `ws://localhost:8000/ws/telemetry/{train_no}`
- Synthetic railway dataset + a training pipeline that also learns from the backend's own logged telemetry
- XGBoost training scripts (synthetic CSV and live SQL data)
- Model evaluation script
- React + Vite + Leaflet frontend
- Demo route and train data
- `render.yaml` for one-click Render deployment (web service + managed Postgres)

## 1. Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open: http://localhost:8000/docs

## 2. Train the ML model

From the repository root:

```bash
pip install -r requirements.txt
python ml/training/train_xgboost.py
```

The trained model is saved to:

`ml/models/eta_xgboost.joblib`

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL, usually http://localhost:5173

## Demo train

Use train number:

`12301`

## Example prediction input

- speed: 92 km/h
- current delay: 8 min
- distance to next station: 38 km
- historical travel time: 31 min
- previous delay: 6 min
- congestion: 0.4
- expected dwell: 3 min

The starter backend can use the trained model if present. If the model has not been trained yet, it falls back to a deterministic ETA estimator so the demo still runs.

## Suggested next steps

Replace the synthetic dataset with authenticated railway/RTIS/signalling feeds, add a persistent database, validate data-quality rules, add authentication/authorization, and retrain the model with route-specific historical data.

## Enhancements / fixes applied to this backend

**Fixed**
- `cd backend && uvicorn main:app` (as instructed above) crashed with
  `ModuleNotFoundError: No module named 'backend'`, because `main.py` and
  several service files used absolute imports (`from backend.x import y`)
  that only resolve when launched from the project root - which is also
  what the test suite (`from backend.main import app`) requires. Every
  cross-package import in the backend now tries the absolute form first
  and falls back to the relative form, so both invocation styles work.
- The demo route file (`data/routes/12301_route.geojson`) only marked one
  of the three scheduled stations as a named point, and the whole route
  spanned about 2.5 km total while the schedule assumed real inter-city
  timings - so a simulated train would converge to a near-crawl. It now
  has geographically realistic coordinates for all three stations
  (Sealdah, Howrah Jn, Barddhaman), consistent with the schedule's pace.

**Enhanced - telemetry is now actually dynamic**
Previously `current_delay_min` stayed frozen at whatever `/start` set it
to, `next_station` was hardcoded to `"Howrah Jn"` everywhere (backend
*and* the React `Dashboard.jsx`, now also fixed), and the simulated
lat/lon just jittered randomly instead of moving anywhere.
`backend/services/train_simulator.py` is new: for any train with a route
+ schedule on disk (currently just demo train 12301), it builds a real
multi-station journey and simulates it every tick - moving along the
actual route polyline, evolving speed/delay from live signalling-style
factors (signal delay, maintenance blocks, level-crossing delay,
congestion), advancing through Sealdah → Howrah Jn → Barddhaman with a
simulated dwell at each stop, and finally piping the result through
`fuse_sources()` → `validate_telemetry()` - the fusion/validation
services that already existed in this starter but nothing had ever
called. Trains with no route/schedule file keep the original static
fallback, so arbitrary train numbers still work.

The simulator runs on its own background loop (started in `main.py`'s
lifespan handler), so both REST polling of `/telemetry` and the
websocket see live movement - not just the websocket as before.

**New endpoints**
- `GET /api/train/{train_no}/eta/stations` - live predicted arrival/delay
  for every stop on the route (the dynamic counterpart to the static
  `/schedule` endpoint).
- `POST /api/train/{train_no}/event?event=<name>&minutes=<n>` - inject a
  delay-causing event for a live demo. `event` is one of `signal_delay`,
  `maintenance_block`, `level_crossing`, `congestion`.

All original endpoints, the WebSocket contract, and the 4 existing tests
(`pytest` from the project root) are unchanged and still pass.

## SQL persistence, train search, and a model trained on real telemetry

**Every train is now backed by SQL, not just an in-memory dict.**
`backend/database/models_db.py` defines two tables: `trains` (the
registry - train number, name, origin/destination, whether it has real
route data) and `telemetry_log` (one row per simulated tick - the actual
real-time data history). Works against Postgres via `DATABASE_URL` (what
Render injects when you attach a database) or a local SQLite file
(`data/yatrasuchak.db`) when `DATABASE_URL` isn't set - no code changes
either way.

**"Find a train" now reflects throughout the backend.** Whichever
endpoint a train number is first looked up through -
`GET /api/trains/search?q=...`, `GET /api/trains/{no}`,
`POST /api/train/start`, or any `GET /api/train/{no}/...` - that lookup
upserts a `Train` row via `backend/database/repository.py`. From then on
every other endpoint keyed by that same train number is reading the same
persisted record, and it shows up in future searches/listings. Demo train
`12301` is auto-registered at startup from its route/schedule files
(`backend/database/seed.py`); any other train number you look up gets
registered the same way, just without live route simulation.

New endpoints:
- `GET /api/trains/search?q=<text>` - find trains by number or name
- `GET /api/trains` - list every known train
- `GET /api/trains/{train_no}` - look up (and register, if new) one train
- `GET /api/trains/{train_no}/history?limit=200` - its real telemetry
  history, read back from SQL

**The ETA model can now be trained on the backend's own live data**,
not just the synthetic CSV. Every simulator tick is logged to
`telemetry_log`; `ml/training/train_from_sql.py` reconstructs training
labels from that log itself - for each logged row, "how long did it
actually take to reach the station it was heading to" is recovered by
looking at the subsequent rows where `next_station` changes - and trains
the same XGBoost model on those (feature set, output path, and therefore
`eta_predictor.py`'s pickup of it are all unchanged). Trigger it via:

- `GET /api/model/status` - whether a trained model exists yet, and how
  many telemetry rows have been logged so far
- `POST /api/model/retrain` - retrain now (needs ~30+ logged rows; returns
  a 409 with a clear message if there isn't enough data yet - let the
  simulation run a bit longer, e.g. by opening the websocket or polling
  `/telemetry`, then retry)

## Deploying to Render

1. Push this repo to GitHub/GitLab.
2. In Render, choose **New +** → **Blueprint**, point it at the repo.
   `render.yaml` at the project root provisions both the web service and
   a free Postgres database, and wires `DATABASE_URL` between them
   automatically.
3. First deploy will build with `pip install -r requirements.txt` and
   start with `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, run
   from the project root - matching how the code's imports and the test
   suite both expect it to run.
4. Once you deploy a frontend, set the `FRONTEND_ORIGIN` env var on the
   Render service to its URL (currently unset, so CORS defaults to
   allowing all origins - fine for a demo, worth tightening once you
   have a real frontend URL).
5. The database starts empty; demo train `12301` is seeded automatically
   on first boot. `POST /api/model/retrain` needs some live telemetry
   logged first - hit `/api/train/start` and let the simulator run for a
   minute or two (or open the websocket) before retraining.

No Docker needed for the Blueprint path above, but `deployment/Dockerfile`
and `docker-compose.yml` are also kept up to date (respecting `$PORT`) if
you'd rather deploy as a Docker web service.

