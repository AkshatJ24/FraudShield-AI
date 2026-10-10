# FraudShield — frontend

React 18 + TypeScript + Vite, Tailwind CSS for layout and styling, Chakra UI v2 for the drawer, tooltips, toasts and colour mode. Built from `FraudShield Dashboard.dc.html` (the approved prototype).

## Run

```bash
cd frontend
cp .env.example .env
npm install
npm run dev            # http://localhost:5173
```

Backend first (from the repo root): `docker compose up -d db`, then `uvicorn app.main:app --reload --port 8000` from `backend/`.

No backend? Set `VITE_DATA_SOURCE=mock` in `.env`. The in-browser generator emits the same payload as the live stream.

## Environment

| Variable | Default | |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | FastAPI base URL |
| `VITE_API_PREFIX` | `/api/v1` | Must match `API_V1_PREFIX` |
| `VITE_DATA_SOURCE` | `live` | `live` or `mock` |
| `VITE_DECISION_COLORS` | `blue` | `blue` or `semantic` (green / amber / red) |
| `VITE_MOCK_RATE` | `demo` | Mock only: `demo` or `realistic` |

## How it talks to the API

Startup pipeline (each step held on screen for at least 850 ms so the sequence reads):

1. **FastAPI** — `GET /health`, fails if `status == "down"`
2. **Model** — `model_loaded` and `n_trees` from the same health response
3. **PostgreSQL** — `GET /health/db` (`SELECT 1`; 503 when the database is unreachable)
4. **SSE stream** — opens `EventSource(/api/v1/stream)`, then `POST /api/v1/simulate/start`

A failed step stops the pipeline and shows the error with a Retry button.

Each stream event is a `ScoreResponse` plus `true_label`, `scored_at` and the request fields the tables show (`TransactionAmt`, `ProductCD`, `card1`, `card4`, `card6`, `P_emaildomain`, `DeviceType`). The simulator sends each holdout transaction's full raw row to the scorer: every `ScoreRequest` field, including the anonymised C, D, V and id columns. `features.parquet` keeps categoricals only in encoded form and amounts as float32, so the raw strings and amounts are joined back from `data/raw/train_*.csv`. Rows the downsampled demo skips still go through the card-history store, so simulated scores match `holdout_predictions.parquet` exactly (`backend/tests/test_simulator_parity.py`). Device is blank for the ~87% of transactions that have no identity row.

Simulator controls:

| Call | What it does |
| --- | --- |
| `POST /simulate/start` | Starts, or **resumes where the last stop left off** |
| `POST /simulate/stop` | Pauses; the replay position is kept |
| `POST /simulate/reset` | Rewinds to the first row and reloads the card history (the ↺ button in the sidebar card) |
| `GET /simulate/status` | `{running, position, total, warmed_up, loading}`, polled every 4 s for the progress bar |

The first start loads the replay set (`data/replay/`) and its card-history snapshot (a few seconds). Both stay cached for the life of the API process. A rewind reloads the snapshot, so re-scored rows don't see their own history. The Overview shows "Waiting for the first transaction…" until the first event arrives.

On a free host that sleeps when idle, the FastAPI step keeps retrying `GET /health` for up to 3 minutes and shows a "waking up" note before giving up.

## Metrics page

`GET /api/v1/metrics`, polled every 10 s while the app is open. Thresholds and the Model card on the Overview also read from it, falling back to the constants in `config.ts` until it answers.

| Section | Source |
| --- | --- |
| Headline tiles (PR-AUC, ROC-AUC, recall @ 1% FPR, ECE, cost saved + 90% CI) | `holdout_result.json`, `phase4_holdout_result.json` |
| Precision vs. recall (holdout and validation, shipped thresholds marked) | `cost_curve.json`, decision bands |
| Cost vs. threshold slider | `cost_curve.json` (holdout) |
| Decision bands, cost breakdown, strategy comparison | `phase4_holdout_result.json` |
| Live stream: decision mix, latency p50/p95/p99, precision/recall against `true_label`, review queue | PostgreSQL `transactions` |
| What drives the score | `shap_global.json` |

The artifacts are read once per API process, so restart the API after retraining. In mock mode the page uses `src/api/metricsSnapshot.json`, a snapshot of the same response with the live section empty.

## Structure

```
src/
  config.ts                 env, thresholds (Review ≥ 5, Block ≥ 16), holdout metrics, repo URL
  theme.ts                  Chakra theme (fonts, tooltip); colours come from CSS variables
  index.css                 light / dark / semantic palettes as CSS variables, shared by Tailwind and Chakra
  api/
    types.ts                ScoreResponse, Reason, Health, StreamEvent, Metrics, SimStatus (mirror the backend)
    client.ts               fetch wrappers for /health, /health/db, /metrics, /simulate/*
    metricsSnapshot.json    /metrics snapshot for mock mode
    source.ts               DataSource interface; live (FastAPI + SSE) and mock implementations
    mock.ts                 in-browser event generator
  state/FraudShield.tsx     provider: phase, startup pipeline, transaction buffer (400), selection, toggles, metrics, simulator status
  lib/format.ts             money, time, card labels, decision colour tokens
  components/
    StartScreen.tsx         Start / Test, GitHub link
    BootPipeline.tsx        4-step startup with error + retry
    Sidebar.tsx             nav, "Soon" items, simulator card (collapses under 1180 px)
    Header.tsx              live status, ground-truth toggle, GitHub link, light / dark switch
    StatsStrip.tsx          scored / approved / review / blocked / latency
    PulseRingCard.tsx       60-second radial pulse ring
    FlaggedCard.tsx         stacked Review / Block cards
    FeedTable.tsx           compact (Overview) and full (Live Feed) tables
    ModelCard.tsx           holdout metrics and thresholds (from /metrics)
    charts.tsx              SVG LineChart (crosshair + tooltip), Legend, HBar
    TransactionDrawer.tsx   score gauge, reasons, ground truth, request / response inspector
    ui.tsx                  GitHubLink, LinkButton, CardTitle
  pages/
    Overview.tsx
    LiveFeed.tsx
    Metrics.tsx
```

## Notes

- Tailwind's preflight is off; Chakra's CSS reset is the only reset.
- Light / dark uses Chakra's `useColorMode`; `App.tsx` mirrors it to `data-theme` on `<html>` so the CSS variables switch.
- CORS is already open (`allow_origins=["*"]`) in `backend/app/main.py`; tighten it before deploying.
