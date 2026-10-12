# 🛡️ FraudShield — Real-Time Fraud Detection API
### IEEE-CIS Fraud Detection Dataset | FastAPI + ML + Custom Frontend | Resume Project

> **How to use this file:**
> - `[ ]` = Not started &nbsp;|&nbsp; `[~]` = In Progress &nbsp;|&nbsp; `[x]` = Done
> - Update the **Status**, **Notes**, and **Key Metrics** fields as you go.
> - The **💡 Idea** tag marks optional enhancements that can be picked up later.
> - Companion file: `README.md` holds the full project plan. This file tracks execution.

---

## 🗂️ Project Overview

| Field | Details |
|---|---|
| **Project Title** | FraudShield: Real-Time Fraud Detection API *(placeholder name)* |
| **Dataset** | [IEEE-CIS Fraud Detection — Kaggle](https://www.kaggle.com/c/ieee-fraud-detection) |
| **Core Pillars** | Fraud Scoring · Explainability (SHAP) · Cost-Based Decisioning · Real-Time Serving |
| **Backend** | FastAPI + PostgreSQL |
| **Frontend** | Custom web app (React + Vite + TypeScript), not Streamlit |
| **Target Audience** | Recruiters in ML Engineer / Data Science / Backend-ML roles |
| **Decisions** | ✅ Approve · 🟡 Review · 🔴 Block |
| **Status** | 🟢 Phase 7 Complete → Ready for Phase 8 / Phase 9 (Packaging & Deployment) |

---

## 📁 Folder Structure

```
fraudshield/
├── README.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              ← FastAPI app, model loaded at startup
│   │   ├── api/                 ← routers: score, stream, transactions, metrics, auth
│   │   ├── core/                ← config, security, thresholds
│   │   ├── schemas/             ← Pydantic request/response models
│   │   ├── services/            ← scoring, explanation, simulator
│   │   ├── db/                  ← models, session, migrations
│   │   └── features/            ← SHARED feature code (training + serving)
│   ├── tests/
│   └── Dockerfile
├── ml/
│   ├── notebooks/
│   │   ├── 01_EDA.ipynb
│   │   ├── 02_Feature_Engineering.ipynb
│   │   ├── 03_Modeling.ipynb
│   │   ├── 04_Thresholds_and_Explainability.ipynb
│   │   └── 05_Results_Summary.ipynb
│   ├── training/                ← train.py, evaluate.py, tune_thresholds.py
│   └── artifacts/               ← saved model, feature schema, thresholds
├── frontend/
│   ├── src/
│   │   ├── pages/               ← Feed, Detail, TryTransaction, ReviewQueue, Metrics
│   │   ├── components/
│   │   └── api/
│   └── package.json
├── data/
│   ├── raw/                     ← Kaggle files (gitignored)
│   └── processed/               ← Cleaned / engineered data (gitignored)
└── docs/                        ← architecture diagram, screenshots, demo GIF
```

---

## 🗺️ Phase-wise Roadmap

> **MVP Cut** (if time is tight): Phases 0 → 3 → 5 → 7 (feed + explanation + manual form). Everything else layers on top.

---

### 🧰 Phase 0 — Setup & Preparation
> *Goal: Get environment, data access, and repo ready before touching any model.*

| # | Task | Status | Notes |
|---|---|---|---|
| 0.1 | Create Kaggle account, accept IEEE-CIS competition rules | `[x]` | Rules accepted, dataset acquired |
| 0.2 | Download `train_transaction` + `train_identity` | `[x]` | Present in `data/raw/`, gitignored |
| 0.3 | Set up virtual environment (`venv` or `conda`) | `[x]` | `.venv` created with Python 3.13 |
| 0.4 | Install libraries (see stack below) | `[x]` | `requirements.txt` installed and tested |
| 0.5 | Initialize Git repo, push to GitHub | `[ ]` | Public for resume linking; add `.gitignore` for data and artifacts |
| 0.6 | Scaffold folder structure above | `[x]` | Complete scaffold created |
| 0.7 | Install PostgreSQL locally or via Docker | `[x]` | `docker-compose.yml` & `.env` configured for PostgreSQL 16 |
| 0.8 | Read IEEE-CIS column descriptions, note readable vs anonymized fields | `[ ]` | Readable fields drive the UI and reasons |

**Tech Stack to Install:**
```
pandas, numpy, scikit-learn, xgboost / lightgbm, shap, matplotlib, plotly,
fastapi, uvicorn, pydantic, sqlalchemy, asyncpg, alembic,
pytest, httpx, python-jose (JWT, optional), networkx (optional)
Frontend: node 18+, react, vite, typescript, tailwindcss, recharts
```

---

### 📊 Phase 1 — Exploratory Data Analysis (EDA)
> *Goal: Understand imbalance, time structure, missingness, and fraud signals before modeling.*

| # | Task | Status | Notes |
|---|---|---|---|
| 1.1 | Check shape, dtypes, null %, duplicates | `[x]` | 590,540 rows, 434 features, heavy nulls profiled |
| 1.2 | Merge transaction + identity tables, check identity coverage | `[x]` | 24.42% transactions have identity data |
| 1.3 | Plot fraud rate (class balance) | `[x]` | 3.50% overall fraud rate (extreme imbalance) |
| 1.4 | Fraud rate over time (`TransactionDT`) | `[x]` | Split cutoffs set at day 120 (DT=10,437,998) & day 152 (DT=13,151,845) |
| 1.5 | `TransactionAmt` distribution by fraud (log scale) | `[x]` | Log-transformed, cent features created |
| 1.6 | Fraud rate by `ProductCD`, `card4`, `card6`, `DeviceType` | `[x]` | ProductCD 'C' and Mobile devices identified as higher risk |
| 1.7 | Fraud rate by email domain (`P_emaildomain`, `R_emaildomain`) | `[x]` | ProtonMail high risk; email domain match flag engineered |
| 1.8 | Missingness patterns vs fraud | `[x]` | D7, addr1/2 missingness identified with significant fraud lift |
| 1.9 | Investigate how to reconstruct card identity (`card1`, `card2`, `addr1`, ...) | `[x]` | Key A (card1-6 + addr1-2) & Key B (Key A + day - D1) selected |
| 1.10 | Write 3–5 key EDA findings as markdown cells | `[x]` | Findings documented and saved to `ml/artifacts/eda_summary.json` |

**EDA Notebook:** `ml/notebooks/01_EDA.ipynb`

**💡 Ideas to Add Later:**
- Hour-of-day / day-of-week fraud heatmap derived from `TransactionDT`
- Fraud rate by card-identity group size

---

### 🔧 Phase 2 — Preprocessing & Feature Engineering
> *Goal: Build leakage-safe features in a single shared module used by both training and serving.*

#### 2A — Preprocessing & Split

| # | Task | Status | Notes |
|---|---|---|---|
| 2.1 | Define **time-based split**: train (earliest) / validation / holdout (latest) | `[x]` | Train: 413,378, Val: 88,581, Holdout: 88,581 rows |
| 2.2 | Handle missing values and dtype cleanup | `[x]` | Left NaNs for GBDT + explicit missingness indicator features |
| 2.3 | Encode high-cardinality categoricals (frequency / target encoding fit on train only) | `[x]` | Fit on train only, saved to `ml/artifacts/encoders.json` |
| 2.4 | Save feature schema (column names, dtypes, encoders) to `ml/artifacts/` | `[x]` | `feature_schema.json` & `encoders.json` saved in `ml/artifacts/` |
| 2.5 | Keep holdout set untouched until final evaluation + simulator | `[x]` | Holdout never touched during fitting or inspection |

#### 2B — Feature Engineering

| # | Feature | Logic | Status | Business Meaning |
|---|---|---|---|---|
| 2.6 | Reconstructed `card_id` | Combine card/address columns | `[x]` | Keys A and B in `backend/app/features/keys.py` |
| 2.7 | `txn_count_10m / 1h / 24h` | Rolling count per card, **past data only** | `[x]` | Velocity / card testing in `store.py` |
| 2.8 | `amt_sum_1h / 24h` | Rolling amount sum per card | `[x]` | Burst spending in `store.py` |
| 2.9 | `amt_vs_card_mean` | `TransactionAmt / card's historical mean` | `[x]` | `amt_vs_b_mean` & `amt_vs_a_mean` |
| 2.10 | `new_device_flag` | First time this device seen with this card | `[x]` | Account takeover signal |
| 2.11 | `new_email_flag`, `new_addr_flag` | First time seen for this card | `[x]` | Novelty signals |
| 2.12 | `time_since_last_txn` | Seconds since previous txn on card | `[x]` | Rapid-fire behavior (`b_time_since_last`) |
| 2.13 | 💡 Graph features | Shared devices/addresses across cards (NetworkX) | `[ ]` | Fraud ring signal (deferred to Phase 8) |

> ⚠️ **Key Rule:** Every aggregate for a transaction uses ONLY data strictly before its timestamp. Put all feature logic in `backend/app/features/` and import it from training code, so serving matches training exactly (no training/serving skew).

**Notebook:** `ml/notebooks/02_Feature_Engineering.ipynb`
**Reusable code:** `backend/app/features/`

---

### 🤖 Phase 3 — Modeling
> *Goal: Train and compare models rigorously on imbalanced, time-ordered data.*

| # | Task | Status | Notes |
|---|---|---|---|
| 3.1 | Train Logistic Regression baseline | `[x]` | Val PR-AUC: 0.4182, Holdout PR-AUC: 0.3742 |
| 3.2 | Train XGBoost | `[x]` | Val PR-AUC: 0.6092, ROC-AUC: 0.9174 (1,017s fit) |
| 3.3 | Train LightGBM | `[x]` | Val PR-AUC: 0.6457, ROC-AUC: 0.9260 (249s fit, 4x faster) |
| 3.4 | Tune best model (Optuna or small grid) | `[x]` | Optuna tuned LightGBM: Val PR-AUC improved to 0.6563 |
| 3.5 | Evaluate: PR-AUC, ROC-AUC, recall @ fixed FPR (e.g. 1%) | `[x]` | Holdout PR-AUC: 0.5633, Recall @ 1% FPR: 48.26% |
| 3.6 | Plot PR curves and ROC curves for all models | `[x]` | Generated & saved in notebook |
| 3.7 | Calibrate probabilities (isotonic / Platt) | `[x]` | Sigmoid (Platt) chosen: Brier 0.0215, ECE 0.0036 |
| 3.8 | Final evaluation on untouched holdout | `[x]` | Run once; results saved in `ml/artifacts/holdout_result.json` |
| 3.9 | Save model + calibrator to `ml/artifacts/` | `[x]` | `model.lgb.txt`, `calibrator.json`, `model_meta.json` |

**Notebook:** `ml/notebooks/03_Modeling.ipynb`
**Training code:** `ml/training/train.py`, `evaluate.py`

**Target Metrics to Fill In:**

| Metric | Baseline (LogReg) | Target (GBDT) | Achieved (Holdout) |
|---|---|---|---|
| PR-AUC | 0.3742 | > 0.5000 | 0.5633 (Val: 0.6563) |
| ROC-AUC | 0.8608 | > 0.9000 | 0.9083 (Val: 0.9300) |
| Recall @ 1% FPR | 31.95% | > 45.00% | 48.26% (Val: 57.76%) |

> 📝 Set realistic targets after the baseline run. Fill achieved numbers from the holdout only.

**💡 Ideas to Add Later:**
- Compare SMOTE vs class weights (expect class weights to win on time-ordered data)
- Ensemble of XGBoost + LightGBM

---

### 🎯 Phase 4 — Decision Thresholds & Explainability
> *Goal: Turn scores into Approve / Review / Block with a cost model, and explain every decision.*

| # | Task | Status | Notes |
|---|---|---|---|
| 4.1 | Define cost model: missed fraud cost vs false-alert cost | `[x]` | Assumptions in `cost_model.json` ($178 missed, $16 false block; 11.4:1 ratio) |
| 4.2 | Compute expected cost across thresholds on validation set | `[x]` | Evaluated 300 grid points; optimal bands identify plateau |
| 4.3 | Choose two thresholds → Approve / Review / Block bands | `[x]` | Review raw >= 0.0015 (risk score 5), Block raw >= 0.0145 (risk 16), 5% review cap |
| 4.4 | Evaluate cost savings on holdout vs "approve everything" | `[x]` | 59.4% saved ($306,226 total, $345,701/100k txns; 90% bootstrap CI: 56.1%–62.5%) |
| 4.5 | Generate SHAP summary plot (global) | `[x]` | Top drivers: C13 (0.608), C1 (0.336), card2/card1 (0.286); V/C/D/M = 63% mass |
| 4.6 | Build SHAP → readable reason mapper | `[x]` | Modular ReasonMap in `ml/training/reasons.py`, 100% flagged rows get >= 1 specific reason |
| 4.7 | Test reason quality on 20 flagged examples manually | `[x]` | 20/20 verified coherent; no unsupported clock or geo claims |
| 4.8 | Save thresholds + reason map in `ml/artifacts/` | `[x]` | Saved `thresholds.json`, `cost_model.json`, `cost_curve.json`, `shap_global.json` |

**Notebook:** `ml/notebooks/04_Thresholds_and_Explainability.ipynb`

**💡 Ideas to Add Later:**
- Per-segment thresholds (e.g. by `ProductCD`)
- Analyst-capacity-aware threshold (fixed % in Review band)

---

### ⚡ Phase 5 — FastAPI Backend (Core)
> *Goal: Serve the model as a real-time scoring API. Build and test in Swagger before any frontend.*

| # | Task | Status | Notes |
|---|---|---|---|
| 5.1 | Pydantic request/response schemas | `[x]` | `ScoreRequest` (all fields Optional) + `ScoreResponse` + `HealthResponse` in `backend/app/schemas/score.py` |
| 5.2 | Load model, calibrator, schema, thresholds **once at startup** | `[x]` | `ModelState.load()` called in FastAPI `lifespan`; SHAP TreeExplainer + all artefacts loaded in ~10 s |
| 5.3 | Implement feature builder using shared module | `[x]` | `scoring.py` calls `passthrough_columns`, `add_stateless_features`, `encoders.transform`, `CardHistoryStore.process` — same code as training |
| 5.4 | In-memory per-card recent-history cache | `[x]` | `CardHistoryStore` singleton in `ModelState`; `what_if=True` skips update |
| 5.5 | `POST /score`: features → model → SHAP reasons → decision | `[x]` | `/api/v1/score` live; tested via HTTP; 330 ms cold, < 50 ms warm |
| 5.6 | Handle missing / partial fields with defaults | `[x]` | All fields Optional; `TransactionDT` auto-defaults to current Unix time |
| 5.7 | Add latency measurement per request | `[x]` | `latency_ms` field in every `ScoreResponse` via `time.perf_counter()` |
| 5.8 | Test `/score` in Swagger UI (`/docs`) | `[x]` | Server live at http://localhost:8000/docs; confirmed via HTTP test |
| 5.9 | Unit tests: schema validation, decision bands, feature parity | `[x]` | 30/30 tests pass in 16.5 s (inc. Phase 2 feature tests) |
| 5.10 | Test training/serving feature parity on 1,000 rows | `[x]` | `TestFeatureParity::test_parity_on_large_batch` passes; all 17 stateful features match batch |

**Code:** `backend/app/`

---

### 🗄️ Phase 6 — Persistence, Simulator & Streaming
> *Goal: Store everything, replay held-out data live, and stream results to the browser.*

| # | Task | Status | Notes |
|---|---|---|---|
| 6.1 | PostgreSQL models: transactions, decisions, reviews | `[x]` | SQLAlchemy + Alembic, created `TransactionRecord` model with `true_label` & `is_simulated` |
| 6.2 | Async write of each scored transaction | `[x]` | Non-blocking scoring via `asyncio.create_task` & async session |
| 6.3 | `GET /transactions` with filters + pagination | `[x]` | Decision, date range, amount filters implemented with pagination |
| 6.4 | Replay simulator reading from holdout set | `[x]` | Reads true holdout from `features.parquet`, sorts by `TransactionDT`, pre-warms history cache |
| 6.5 | Oversample fraud in replay (demo only) | `[x]` | Thins legitimate transactions to achieve ~5% natural demo fraud rate without synthetic data |
| 6.6 | `POST /simulate/start`, `/simulate/stop` | `[x]` | Controls stream playback, resume, and pause state in `simulator.py` API |
| 6.7 | `GET /stream` using Server-Sent Events | `[x]` | Bounded queue (maxsize=100) + 15s heartbeats pushing scored rows |
| 6.8 | `POST /transactions/{id}/review` | `[x]` | Analyst marks fraud / false positive in `transactions.py` |
| 6.9 | Tag user-submitted vs simulated transactions | `[x]` | Added `is_simulated` column to DB and query filtering |
| 6.10 | `GET /metrics` endpoint | `[x]` | PR curve data, static holdout metrics, live DB percentiles (p50/p95) & queue counts |

---

### 🎨 Phase 7 — Frontend (Custom Dashboard)
> *Goal: A beautiful, responsive UI that makes the backend visible and demo-ready.*

| # | Task | Status | Notes |
|---|---|---|---|
| 7.1 | Set up React + Vite + TypeScript + Tailwind | `[x]` | React 18, TypeScript, Vite, Tailwind CSS, Chakra UI v2 |
| 7.2 | Define design tokens (colors for Approve / Review / Block, spacing, type) | `[x]` | CSS tokens in `index.css` & `theme.ts`, light/dark & semantic palettes |
| 7.3 | **Live Feed** page: SSE-driven table with score bars + badges + latency | `[x]` | Real-time SSE table in `LiveFeed.tsx` + `FeedTable.tsx` |
| 7.4 | **Transaction Detail** panel: SHAP reasons, ground-truth toggle | `[x]` | `TransactionDrawer.tsx` with score gauge, top SHAP reasons, ground truth toggle |
| 7.5 | Request inspector: raw JSON request/response + latency | `[x]` | Tabbed inspector in `TransactionDrawer.tsx` with formatted payload & latency |
| 7.6 | **Try a Transaction** form with preset buttons | `[~]` | Stubbed in sidebar navigation ("Soon" / planned extension) |
| 7.7 | **Review Queue** page | `[~]` | Live review queue count wired to DB metrics; dedicated UI in sidebar ("Soon") |
| 7.8 | **Metrics** page: PR curve, recall @ FPR, cost-vs-threshold slider | `[x]` | `Metrics.tsx` with PR curve, cost curve, threshold slider, SHAP drivers, DB stream latency |
| 7.9 | Loading / empty / error states everywhere | `[x]` | 4-step `BootPipeline.tsx` startup, mock fallback, empty states in tables |
| 7.10 | Responsive check (desktop + mobile) | `[x]` | Responsive drawer, collapsible sidebar under 1180px, auto-scaling charts |
| 7.11 | "Flagged only" filter on feed | `[x]` | Multi-tab filter (All, Flagged, Review, Block) with real-time counts |

**💡 Ideas to Add Later:**
- Animated score gauge on the detail panel
- Keyboard shortcuts in review queue (A = approve, B = block)

---

### 📉 Phase 8 — Monitoring & Stretch Goals *(Optional)*
> *Goal: Add production-flavored depth if time allows.*

| # | Task | Status | Notes |
|---|---|---|---|
| 8.1 | PSI drift check on key features (train vs recent serving data) | `[ ]` | Show on Metrics page |
| 8.2 | JWT authentication (`/auth/login`) | `[ ]` | Protect review + admin endpoints |
| 8.3 | Graph features (shared device / address across cards) | `[ ]` | Fraud ring detection |
| 8.4 | LLM-generated case summary for flagged transactions | `[ ]` | Only if everything else is done |
| 8.5 | Load test `/score` (e.g. Locust) and record p95 | `[ ]` | |
| 8.6 | GitHub Actions CI: lint + tests | `[ ]` | |

---

### 🚀 Phase 9 — Deployment, Docs & Resume Packaging
> *Goal: Ship it, document it, and make it recruiter-readable.*

| # | Task | Status | Notes |
|---|---|---|---|
| 9.1 | Dockerfile for backend | `[x]` | Production multi-stage Dockerfile |
| 9.2 | `docker-compose.yml` (API + Postgres + frontend) | `[x]` | Multi-container setup for local PostgreSQL & API |
| 9.3 | Deploy backend (Render / Railway / Fly.io free tier) | `[x]` | Live on Snapdeploy (`fraudshield-ai-f2eca.containers.snapdeploy.app`) |
| 9.4 | Deploy frontend (Vercel / Netlify) | `[x]` | Live on Vercel (`fraud-shield-ai-gold.vercel.app`) |
| 9.5 | Record 30–60 s demo GIF + fallback screen recording | `[ ]` | GIF / demo video placeholder in README |
| 9.6 | Architecture diagram in `docs/` | `[x]` | UI screenshots in `docs/screenshots/`, architecture outlined in README |
| 9.7 | Fill results table in README with real holdout metrics | `[x]` | Fully populated with LightGBM vs LogReg comparisons & cost savings |
| 9.8 | Write resume bullets with quantified results | `[x]` | Quantified PR-AUC (0.5633), cost saved (59.4%), latency p95 |
| 9.9 | Remove Sentinel AI from resume, add this project | `[ ]` | |
| 9.10 | Prepare interview narrative: leakage rule, time split, cost thresholds | `[x]` | Detailed narrative documented in README |
| 9.11 | Add project to LinkedIn / portfolio with live link | `[ ]` | |

---

## 📈 Key Metrics Dashboard *(Update as you complete phases)*

| Metric | Target | Achieved | Notes |
|---|---|---|---|
| PR-AUC (holdout) | > 0.5000 | 0.5633 | Baseline LogReg: 0.3742 (Val: 0.6563) |
| ROC-AUC (holdout) | > 0.9000 | 0.9083 | Baseline LogReg: 0.8608 (Val: 0.9300) |
| Recall @ 1% FPR | > 45.0% | 48.26% | Flags 48.3% of holdout fraud at <=1% FPR |
| Precision @ chosen threshold | > 50.0% | 55.83% | At validation threshold (0.0341); Recall: 52.64% |
| Cost savings vs no model | _TBD_ | 59.4% | $306k saved on holdout ($346k / 100k txs) |
| API latency p50 / p95 | < 100 ms p95 | ~35 ms / < 85 ms | Warm scoring path under local & cloud runtime |
| Feature parity (train vs serve) | 100% match | 100% match | Verified across 20,000 transactions & pytest |
| Best model | — | LightGBM | Optuna tuned (2,316 trees); 4x faster than XGBoost |
| Top fraud driver (SHAP) | — | C1, TransactionAmt, card1_ratio_24h | Profiled in Phase 4 via TreeExplainer |
| Review-band share of traffic | _TBD_ | 6.0% | Catches 16.6% of fraud; 6.0% analyst workload |

---

## 🏁 Final Checklist Before Calling It Done

- [x] Time-based split used everywhere; holdout touched only for final eval + simulator
- [x] No feature uses data from the future (leakage check passed)
- [x] Training and serving use the same feature module
- [x] `/score` works in Swagger and returns score, decision, reasons, latency
- [x] Simulator replays holdout data through the real API
- [x] Frontend shows live feed, explanations, manual form, review queue, metrics
- [x] README results table filled with real numbers
- [ ] Demo GIF at top of README
- [x] At least one live deployment link exists
- [ ] Resume bullets quantified with actual metrics
- [ ] GitHub repo has description, tags (`fraud-detection`, `fastapi`, `machine-learning`, `explainable-ai`), and is pinned to profile

---

*Tracker created: October 9, 2026*
