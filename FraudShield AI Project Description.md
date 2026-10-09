# FraudShield — Real-Time Fraud Detection API

> A production-style fraud scoring service: a FastAPI backend that scores payment transactions in real time, explains every decision, and powers a live analyst dashboard.

*(Project name is a placeholder. Rename freely.)*

![status](https://img.shields.io/badge/status-in%20development-orange)
![python](https://img.shields.io/badge/python-3.11+-blue)
![fastapi](https://img.shields.io/badge/FastAPI-0.11x-009688)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

<!-- Add a 30–60 s demo GIF here: live feed → click flagged row → SHAP reasons -->

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Demo Walkthrough](#demo-walkthrough)
4. [System Architecture](#system-architecture)
5. [Tech Stack](#tech-stack)
6. [Dataset](#dataset)
7. [Machine Learning Approach](#machine-learning-approach)
8. [API Reference](#api-reference)
9. [Frontend](#frontend)
10. [Evaluation & Results](#evaluation--results)
11. [Project Structure](#project-structure)
12. [Getting Started](#getting-started)
13. [Roadmap](#roadmap)
14. [Design Decisions & Limitations](#design-decisions--limitations)

---

## Overview

Most fraud-detection projects stop at a notebook with an accuracy score. **FraudShield** goes further: it treats fraud detection as a *system*, not just a model.

Every transaction is sent to a FastAPI service that builds leakage-safe features, scores the transaction with a gradient-boosted model, explains the decision with SHAP, applies a cost-optimized threshold, and returns one of three outcomes:

| Decision | Meaning |
|---|---|
| ✅ **Approve** | Low risk. Let the transaction through. |
| 🟡 **Review** | Uncertain. Route to a human analyst queue. |
| 🔴 **Block** | High risk. Decline the transaction. |

A custom web dashboard shows a live stream of scored transactions, explanations for each decision, an analyst review queue, and model performance metrics.

### Why this project

- **Realistic imbalance:** fraud is rare (~3.5% in the dataset), so accuracy is meaningless. Evaluation uses PR-AUC and recall at fixed false-positive rates.
- **Time-aware modeling:** the model is trained on the past and tested on the future, as it would be in production.
- **Business-aware decisions:** thresholds come from a cost model (missed fraud vs. false alert), not a default 0.5.
- **Explainability:** every decision ships with human-readable reasons.
- **Serving, not just training:** auth, persistence, streaming, and latency tracking are all part of the project.

---

## Key Features

- **Real-time scoring API** — `POST /score` returns a risk score, decision, and top reasons, typically in under 100 ms.
- **Three-tier decisioning** — Approve / Review / Block with configurable thresholds.
- **Explainable decisions** — top SHAP drivers returned with every response.
- **Live transaction simulator** — replays held-out (never-trained-on) transactions through the real API.
- **Bring-your-own transaction** — a form with presets ("Normal purchase", "Late-night foreign high-value", "Card testing") that scores through the same endpoint.
- **Analyst review queue** — mark flagged transactions as confirmed fraud or false positive.
- **Cost-based threshold tuning** — interactive slider showing money saved vs. money lost to false alerts.
- **Drift monitoring** — Population Stability Index (PSI) on key features. *(stretch goal)*
- **Persistent history** — all transactions and decisions stored in PostgreSQL and queryable.
- **Request inspector** — raw JSON request/response and latency visible in the UI.

---

## Demo Walkthrough

A typical 2–3 minute demo:

1. **Live feed.** The simulator streams transactions from the held-out test set into the API. Each row shows amount, product, device, a risk score (0–100), a decision badge, and latency. Most rows are green; some are amber or red.
2. **Explain a decision.** Click a flagged row. A side panel lists the top reasons, for example:
   - *5 transactions on this card in the last 10 minutes*
   - *First time this device is seen with this card*
   - *Amount is 8× the card's historical average*
3. **Try your own transaction.** Fill in the form (or click a preset). The same `/score` endpoint returns a score, decision, and reasons live.
4. **Analyst queue.** Review flagged items and mark them as fraud or false positive.
5. **Metrics page.** PR curve, recall at fixed FPR, the cost/threshold slider, and drift indicators.

> **Note on the demo stream:** fraud is oversampled in the replay (e.g. ~1 in 20 instead of the natural ~1 in 30–100) so viewers see flagged transactions quickly. Reported metrics are always computed on the natural, un-oversampled distribution. A "Reveal ground truth" toggle shows the real label next to the model's decision.

---

## System Architecture

```
┌──────────────┐   POST /score        ┌────────────────────────────────────┐
│  Web client  │ ───────────────────▶ │              FastAPI               │
│ (dashboard & │                      │                                    │
│  tx form)    │ ◀─── SSE /stream ─── │  1. Validate input (Pydantic)      │
└──────────────┘                      │  2. Build features (shared module) │
       ▲                              │  3. Model inference (GBDT)         │
       │                              │  4. SHAP reasons                   │
┌──────┴───────┐   POST /score        │  5. Apply thresholds → decision    │
│  Simulator   │ ───────────────────▶ │  6. Persist to PostgreSQL          │
│ (test-set    │                      └──────────────┬─────────────────────┘
│  replay)     │                                     │
└──────────────┘                         ┌───────────┴───────────┐
                                         │ PostgreSQL            │
                                         │ (transactions,        │
                                         │  decisions, reviews)  │
                                         └───────────────────────┘
```

**Key principles**

- The model is loaded **once at startup**, inside the FastAPI process.
- The simulator and the manual form use **the same scoring path**, so there is exactly one place where decisions are made.
- Feature code lives in **one shared module** used by both training and serving to prevent training/serving skew.
- Per-card recent history is kept in a small in-memory cache for fast velocity features, with writes to PostgreSQL done asynchronously.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | **FastAPI**, Pydantic, Uvicorn |
| ML | XGBoost / LightGBM, scikit-learn, SHAP, pandas, NumPy |
| Database | **PostgreSQL** (SQLAlchemy / asyncpg) |
| Streaming | Server-Sent Events (SSE) |
| Auth | JWT *(optional for MVP)* |
| Frontend | React + Vite + TypeScript, Tailwind CSS, a charting library (Recharts or similar) |
| Packaging | Docker, Docker Compose |
| Testing | pytest, httpx |

---

## Dataset

**[IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection)** (Kaggle)

- ~590k transactions, ~3.5% fraud
- `train_transaction` joined with `train_identity` (identity data covers only part of the transactions)
- Human-readable fields (`TransactionAmt`, `ProductCD`, `card4`, `card6`, `addr1`, `P_emaildomain`, `DeviceType`, `DeviceInfo`) are used for the UI and explanations
- `TransactionDT` provides the time axis for the split and the simulator
- Many columns (C, D, V series) are anonymized. They are kept in the model but not used as headline explanations

> Downloading requires accepting the competition rules on Kaggle. The raw data is **not** committed to this repository.

**Why not the popular ULB Credit Card dataset?** Its features are anonymized PCA components, which makes explanations and user input forms meaningless.

---

## Machine Learning Approach

### 1. Data preparation
- Merge the transaction and identity tables.
- Handle missing values and high-cardinality categoricals.
- **Time-based split:** train on the earliest period, validate on the next, and hold out the latest period for the simulator and final test. No random shuffling.

### 2. Feature engineering
- **Velocity features:** transaction counts and amount sums per card over rolling windows (e.g. 10 min, 1 h, 24 h).
- **Behavioral ratios:** amount relative to the card's historical mean/median.
- **Novelty flags:** new device, new email domain, new address for this card.
- **Reconstructed card identity** from card/address columns, since the dataset has no explicit card ID.
- *(Optional)* Graph features via NetworkX: shared devices or addresses across cards.

> **Leakage rule:** every aggregate for a transaction uses *only* data from strictly before that transaction's timestamp.

### 3. Modeling
- Baseline: logistic regression.
- Main model: XGBoost or LightGBM.
- Class imbalance handled via class weights / scale factors. SMOTE is avoided on time-series-like data.
- Calibrated probabilities so the 0–100 risk score is meaningful.

### 4. Decisioning
- Two thresholds create three bands: **Approve**, **Review**, **Block**.
- Thresholds are chosen by minimizing expected cost:
  `cost = (missed fraud × avg fraud amount) + (false alerts × review/friction cost)`
- Review-band capacity (how many cases analysts can handle) is a tunable constraint.

### 5. Explainability
- SHAP values computed per request, with the top contributors mapped to readable reasons.

### 6. Monitoring *(stretch)*
- PSI per key feature between training and recent serving data.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/score` | Score one transaction; returns score, decision, reasons, latency; stores the result |
| `GET` | `/stream` | SSE stream of simulated transactions and their decisions |
| `POST` | `/simulate/start` · `/simulate/stop` | Control the replay simulator |
| `GET` | `/transactions` | Paginated history with filters (decision, date range, amount) |
| `POST` | `/transactions/{id}/review` | Analyst marks fraud / false positive |
| `GET` | `/metrics` | PR curve data, current thresholds, drift stats |
| `POST` | `/auth/login` | Obtain a JWT *(optional)* |
| `GET` | `/docs` | Interactive Swagger UI (auto-generated) |

**Example**

```http
POST /score
Content-Type: application/json

{
  "TransactionAmt": 912.50,
  "ProductCD": "W",
  "card4": "visa",
  "card6": "credit",
  "addr1": 315,
  "P_emaildomain": "protonmail.com",
  "DeviceType": "mobile"
}
```

```json
{
  "transaction_id": "tx_01HZ...",
  "score": 87,
  "decision": "BLOCK",
  "reasons": [
    "Amount is 8x higher than this card's average",
    "First time this device is used with this card",
    "5 transactions on this card in the last 10 minutes"
  ],
  "latency_ms": 42
}
```

*(Field names and values are illustrative and will be finalized with the feature schema.)*

---

## Frontend

A custom web dashboard (not Streamlit) designed to present the system clearly and attractively.

**Pages**

- **Live Feed**: streaming table of transactions with decision badges, score bars, and latency.
- **Transaction Detail**: SHAP reasons, request/response inspector, ground-truth toggle.
- **Try a Transaction**: input form with presets, using the same `/score` endpoint.
- **Review Queue**: analyst workflow for Review/Block items.
- **Metrics**: PR curve, recall at fixed FPR, cost-vs-threshold slider, drift indicators.

**UX goals:** responsive layout, dark/light theme, color-coded decisions, smooth live updates, and clear empty/loading/error states.

---

## Evaluation & Results

Metrics are computed on the **time-based holdout** with the natural fraud rate.

| Metric | Value |
|---|---|
| PR-AUC | _TBD_ |
| ROC-AUC | _TBD_ |
| Recall @ 1% FPR | _TBD_ |
| Precision @ chosen threshold | _TBD_ |
| Expected cost savings vs. no model | _TBD_ |
| API p50 / p95 latency | _TBD_ |

Accuracy is deliberately not reported as a headline metric, because with ~3.5% fraud a model that approves everything is already ~96.5% "accurate".

---

## Project Structure

*Proposed layout. Adjust as the project evolves.*

```
fraudshield/
├── README.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, startup (model loading)
│   │   ├── api/                 # routers: score, stream, transactions, metrics, auth
│   │   ├── core/                # config, security, thresholds
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # scoring, explanation, simulator
│   │   ├── db/                  # models, session, migrations
│   │   └── features/            # shared feature code (training + serving)
│   ├── tests/
│   └── Dockerfile
├── ml/
│   ├── notebooks/               # EDA and experiments
│   ├── training/                # train, evaluate, threshold tuning
│   └── artifacts/               # saved model, feature schema (gitignored if large)
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   └── package.json
├── data/                        # raw data (gitignored)
└── docs/                        # architecture diagram, screenshots, demo GIF
```

---

## Getting Started

> Commands below are placeholders until the project is implemented.

**Prerequisites:** Python 3.11+, Node 18+, Docker, a Kaggle account (for the dataset).

```bash
# 1. Clone
git clone https://github.com/<your-username>/fraudshield.git
cd fraudshield

# 2. Download the dataset (requires Kaggle API credentials)
kaggle competitions download -c ieee-fraud-detection -p data/
unzip data/ieee-fraud-detection.zip -d data/

# 3. Train the model
cd ml/training
python train.py

# 4. Start everything
docker compose up --build
```

- API: `http://localhost:8000` (Swagger UI at `/docs`)
- Dashboard: `http://localhost:5173`

---

## Roadmap

**Phase 1: MVP**
- [ ] EDA, time-based split, baseline model
- [ ] Shared feature module with leakage-safe velocity features
- [ ] GBDT model, PR-AUC evaluation, cost-based thresholds
- [ ] `POST /score` with SHAP reasons, tested via Swagger
- [ ] Frontend: live feed, explanation panel, manual transaction form

**Phase 2: System depth**
- [ ] PostgreSQL persistence and `/transactions` history
- [ ] SSE `/stream` and replay simulator
- [ ] Analyst review queue
- [ ] Metrics page with cost/threshold slider
- [ ] Dockerized deployment

**Phase 3: Stretch**
- [ ] JWT authentication
- [ ] Drift monitoring (PSI)
- [ ] Graph-based features
- [ ] Optional LLM-generated case summaries for flagged transactions
- [ ] CI pipeline and load testing

---

## Design Decisions & Limitations

- **Time-based split over random split:** mirrors real deployment and avoids optimistic leakage.
- **One scoring path:** the simulator and manual form share `/score`, so there is a single source of truth for decisions.
- **Oversampled demo stream:** a presentation choice. All reported metrics use the natural distribution.
- **No card ID in the dataset:** card identity is reconstructed heuristically, which is imperfect.
- **Anonymized features:** many predictive columns can't be explained in plain language. Readable reasons rely on the interpretable subset.
- **Not production-ready:** this is a portfolio project. A real system would add stricter security, PCI-DSS considerations, a feature store, model versioning, and a retraining pipeline with delayed fraud labels.

---

## License

MIT. See `LICENSE` for details.
