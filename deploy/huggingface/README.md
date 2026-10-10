---
title: FraudShield API
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Real-time fraud scoring API with SHAP explanations
---

# FraudShield API

FastAPI backend for [FraudShield](https://github.com/AkshatJ24/FraudShield-AI): scores payment
transactions with a calibrated LightGBM model, explains each decision with SHAP, and replays
the IEEE-CIS holdout as a live stream for the dashboard.

- Health: `/health`, `/health/db`
- Interactive docs: `/docs`

Secrets required: `DATABASE_URL`. Optional: `CORS_ORIGINS` (e.g. `https://your-app.vercel.app`).
