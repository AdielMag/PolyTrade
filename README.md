# PolyTrade (GCP, Firestore, Cloud Run)

Live Polymarket trading with two Telegram bots. Bot A suggests trades and lets you pick the stake; Bot B sends results. State is kept in Firestore. Deployed as Cloud Run services, scheduled by Cloud Scheduler. CI/CD via GitHub Actions.

## Architecture
- Cloud Run services (single image, different `APP_MODULE`):
  - `polytrade-bot-a` → `APP_MODULE=polytrade.telegram.bot_a:app`
  - `polytrade-bot-b` → `APP_MODULE=polytrade.telegram.bot_b:app`
  - `polytrade-analyzer` → `APP_MODULE=polytrade.api.analyzer_app:app`
  - `polytrade-monitor` → `APP_MODULE=polytrade.api.monitor_app:app`
- Firestore collections: `suggestions`, `trades`, `events`, `settings`, `balances_cache`
- Cloud Scheduler: calls Analyzer every 5m, Monitor every 1m
- Both bots show current balance on every message; Bot A has amount presets and confirm flow

## Prerequisites
- GCP project with billing enabled
- Artifact Registry repository for Docker images
- Firestore (Native mode) created in the project
- Telegram bot tokens (create two bots with BotFather)
- Polymarket CLOB access (wallet private key + proxy address)

## Secrets vs Env Vars
- Put secrets in Secret Manager (referenced by Cloud Run env from secrets) and GitHub Secrets (for CI deploy only).
- Non-sensitive config goes into Cloud Run environment variables.

Variables and where to store them:
- Secrets (GCP Secret Manager + Cloud Run from-secret mapping)
  - `WALLET_PRIVATE_KEY` (your trading wallet/Magic private key)
  - `TELEGRAM_BOT_A_TOKEN`
  - `TELEGRAM_BOT_B_TOKEN`
- Non-secrets (Cloud Run environment variables)
  - `CLOB_HOST` (default `https://clob.polymarket.com`)
  - `POLYMARKET_PROXY_ADDRESS` (proxy shown under your profile picture)
  - `SIGNATURE_TYPE` (1 = Magic/email, 2 = browser wallet/EOA; default 2)
  - `CHAIN_ID` (default 137 for Polygon)
  - `EDGE_BPS`, `MIN_LIQUIDITY_USD`, `DEFAULT_SL_PCT`, `DEFAULT_TP_PCT`
  - `GCP_PROJECT_ID` (optional; auto-detected at runtime on Cloud Run)
  - `BOT_B_DEFAULT_CHAT_ID` (Telegram chat ID for Bot B notifications)
  - `APP_MODULE` (set per service as above)
  - `TELEGRAM_BOT_A_WEBHOOK_URL`, `TELEGRAM_BOT_B_WEBHOOK_URL` (the public URLs of the Cloud Run services for bot webhooks)
- GitHub Secrets (for CI/CD)
  - `GCP_PROJECT_ID`, `GCP_REGION`, `GAR_REPOSITORY` (repo name), `IMAGE_NAME` (e.g., `polytrade`), `CLOUD_RUN_SA_KEY` (JSON key for a deploy-only service account)

## Step-by-step Setup
1) Firestore
   - In GCP Console → Firestore → Select Native mode, create database.
2) Artifact Registry
   - Create a Docker repository (e.g., name `polytrade`).
3) Service Account for Deploy
   - Create SA (e.g., `polytrade-deployer`) with roles: Cloud Run Admin, Service Account User, Artifact Registry Writer.
   - Create JSON key and save as GitHub Secret `CLOUD_RUN_SA_KEY`.
4) GitHub Secrets
   - Add: `GCP_PROJECT_ID`, `GCP_REGION`, `GAR_REPOSITORY` (repo name), `IMAGE_NAME` (e.g., `polytrade`), `CLOUD_RUN_SA_KEY`.
5) Telegram Bots
   - Create two bots with BotFather, note tokens.
   - Store tokens in Secret Manager as `TELEGRAM_BOT_A_TOKEN`, `TELEGRAM_BOT_B_TOKEN`.
6) Polymarket CLOB credentials
   - Get your wallet private key (for Magic/email: follow the docs; for browser wallet/EOA: export from your wallet). See Polymarket quickstart: https://docs.polymarket.com/quickstart/orders/first-order
   - Find your Polymarket Proxy address (below your avatar on Polymarket).
   - Store in Secret Manager:
     - `WALLET_PRIVATE_KEY` (secret)
   - Set Cloud Run env (non-secrets):
     - `POLYMARKET_PROXY_ADDRESS`, `CLOB_HOST=https://clob.polymarket.com`, `SIGNATURE_TYPE` (1 or 2), `CHAIN_ID=137`.
7) First Deployment (trigger CI)
   - Push to `master` to run GitHub Actions workflow `.github/workflows/deploy.yml`.
   - The workflow builds and pushes the image, then deploys 4 Cloud Run services with the proper `APP_MODULE`.
8) Configure Cloud Run env and secret mappings
   - For each service (`polytrade-bot-a`, `polytrade-bot-b`, `polytrade-analyzer`, `polytrade-monitor`):
    - Set env vars: `CLOB_HOST`, `POLYMARKET_PROXY_ADDRESS`, `SIGNATURE_TYPE`, `CHAIN_ID`, `EDGE_BPS`, `MIN_LIQUIDITY_USD`, `DEFAULT_SL_PCT`, `DEFAULT_TP_PCT`, `GCP_PROJECT_ID` (optional), and the service-specific `APP_MODULE`.
    - Map secrets: `WALLET_PRIVATE_KEY`, `TELEGRAM_BOT_A_TOKEN` (for Bot A only), `TELEGRAM_BOT_B_TOKEN` (for Bot B only).
9) Get Cloud Run URLs and set Telegram webhooks
   - After deploy, note `polytrade-bot-a` and `polytrade-bot-b` URLs.
   - Set env `TELEGRAM_BOT_A_WEBHOOK_URL` and `TELEGRAM_BOT_B_WEBHOOK_URL` to those URLs.
   - Set Telegram webhook for each bot:
     - `https://api.telegram.org/bot<TELEGRAM_BOT_A_TOKEN>/setWebhook?url=<bot-a-url>/webhook`
     - `https://api.telegram.org/bot<TELEGRAM_BOT_B_TOKEN>/setWebhook?url=<bot-b-url>/webhook`
10) Cloud Scheduler jobs
    - Create HTTP job (every 5 minutes) to POST `<analyzer-url>/run`.
    - Create HTTP job (every 1 minute) to POST `<monitor-url>/run`.
    - Use OIDC auth with the Cloud Run Invoker role for the job’s service account.
11) Validate
    - Send `/suggest` to Bot A in Telegram; each message should display your balance.
    - Tap an idea → choose amount (preset or custom) → Confirm → trade created.
    - Monitor will manage exits and Bot B will notify results (messages include current balance).

## Local Run (optional)
```bash
# Pick one app to run locally
export APP_MODULE=polytrade.api.analyzer_app:app
uvicorn $APP_MODULE --reload --port 8000
```

## CI/CD
- On push to `master`, workflow builds the Docker image, pushes to Artifact Registry, and deploys to 4 Cloud Run services. Secrets remain configured on Cloud Run/Secret Manager; the pipeline only updates the image and `APP_MODULE` env var.