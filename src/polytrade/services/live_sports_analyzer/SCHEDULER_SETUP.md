# Cloud Scheduler Setup for Live Sports Analyzer

This guide explains how to create a Cloud Scheduler job that calls the Live Sports Analyzer service with custom parameters.

## Overview

The Live Sports Analyzer service accepts parameters via POST request body. You can configure these parameters when creating a Cloud Scheduler job.

## Service Endpoint

- **URL**: `https://polytrade-live-sports-<region>-<project-id>.a.run.run/run`
- **Method**: POST
- **Content-Type**: application/json

## Parameters

All parameters are optional and have defaults:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_workers` | int | 10 | Number of concurrent threads for fetching markets |
| `lookback_hours` | float | 4.0 | Hours to look back for live games |
| `min_liquidity` | float | 500.0 | Minimum liquidity in USD |
| `min_ask_price` | float | 0.93 | Minimum ask price (0-1, e.g., 0.93 = 93%) |
| `max_ask_price` | float | 0.96 | Maximum ask price (0-1, e.g., 0.96 = 96%) |

## Creating a Cloud Scheduler Job

### Option 1: Using gcloud CLI

**Note**: Since the service is deployed with `--allow-unauthenticated`, we don't need OIDC authentication. The service is publicly accessible.

```bash
# Set your variables
PROJECT_ID="your-project-id"
REGION="us-central1"
SERVICE_URL="https://polytrade-live-sports-${REGION}-${PROJECT_ID}.a.run.app/run"
SCHEDULE="0 * * * *"  # Every hour (at minute 0)

# Create the job (no authentication needed since service is public)
gcloud scheduler jobs create http live-sports-analyzer \
  --project=$PROJECT_ID \
  --location=$REGION \
  --schedule="$SCHEDULE" \
  --uri="$SERVICE_URL" \
  --http-method=POST \
  --message-body='{
    "max_workers": 15,
    "lookback_hours": 4.0,
    "min_liquidity": 500.0,
    "min_ask_price": 0.93,
    "max_ask_price": 0.96
  }' \
  --headers="Content-Type=application/json"
```

**If you want to use authentication** (recommended for production), you'll need to:
1. Remove `--allow-unauthenticated` from the Cloud Run service
2. Use OAuth client instead of OIDC, OR
3. Use a service account with proper IAM bindings

For now, the public endpoint works fine for testing.

### Option 2: Using GCP Console

1. **Navigate to Cloud Scheduler**:
   - Go to GCP Console → Cloud Scheduler
   - Click "CREATE JOB"

2. **Basic Configuration**:
   - **Name**: `live-sports-analyzer`
   - **Region**: Select your region (e.g., `us-central1`)
   - **Description**: (optional) "Runs live sports market analysis"

3. **Frequency**:
   - **Frequency**: Use cron syntax (e.g., `0 * * * *` for every hour)
   - Or use the visual picker

4. **Target Configuration**:
   - **Target type**: HTTP
   - **URL**: `https://polytrade-live-sports-<region>-<project-id>.a.run.app/run`
   - **HTTP method**: POST
   - **Auth header**: None (service is public/unauthenticated)
   - **Note**: If you want authentication, you'll need to remove `--allow-unauthenticated` from Cloud Run and configure OAuth client

5. **Request Body**:
   - Click "Show more" → "Body"
   - Select "JSON"
   - Enter the JSON payload:
   ```json
   {
     "max_workers": 15,
     "lookback_hours": 4.0,
     "min_liquidity": 500.0,
     "min_ask_price": 0.93,
     "max_ask_price": 0.96
   }
   ```

6. **Headers**:
   - Add header: `Content-Type` = `application/json`

7. **Click "CREATE"**

### Option 3: Using Terraform (if applicable)

```hcl
resource "google_cloud_scheduler_job" "live_sports_analyzer" {
  name             = "live-sports-analyzer"
  description      = "Runs live sports market analysis"
  schedule         = "*/15 * * * *"
  time_zone        = "UTC"
  region           = "us-central1"
  
  http_target {
    http_method = "POST"
    uri         = "https://polytrade-live-sports-${var.region}-${var.project_id}.a.run.run/run"
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      max_workers     = 15
      lookback_hours  = 4.0
      min_liquidity   = 500.0
      min_ask_price   = 0.93
      max_ask_price   = 0.96
    }))
    
    oidc_token {
      service_account_email = var.scheduler_service_account_email
      audience              = "https://polytrade-live-sports-${var.region}-${var.project_id}.a.run.run/run"
    }
  }
}
```

## Example Configurations

### Example 1: Default Settings (matches QUICK_TEST.py)
```json
{
  "max_workers": 15,
  "lookback_hours": 4.0,
  "min_liquidity": 500.0,
  "min_ask_price": 0.93,
  "max_ask_price": 0.96
}
```

### Example 2: More Aggressive Filtering
```json
{
  "max_workers": 20,
  "lookback_hours": 2.0,
  "min_liquidity": 1000.0,
  "min_ask_price": 0.94,
  "max_ask_price": 0.95
}
```

### Example 3: Broader Search
```json
{
  "max_workers": 10,
  "lookback_hours": 6.0,
  "min_liquidity": 300.0,
  "min_ask_price": 0.90,
  "max_ask_price": 0.98
}
```

## Service Account Setup

**Note**: Since the service is deployed with `--allow-unauthenticated`, you don't need a service account for basic scheduling. However, if you want to secure the service later:

```bash
# Create service account (if it doesn't exist)
gcloud iam service-accounts create scheduler-sa \
  --display-name="Cloud Scheduler Service Account" \
  --project=$PROJECT_ID

# Grant Cloud Run Invoker role
gcloud run services add-iam-policy-binding polytrade-live-sports \
  --member="serviceAccount:scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --project=$PROJECT_ID

# Then remove --allow-unauthenticated from the service
gcloud run services update polytrade-live-sports \
  --no-allow-unauthenticated \
  --region=$REGION \
  --project=$PROJECT_ID
```

## Testing the Job

### Test via gcloud:
```bash
gcloud scheduler jobs run live-sports-analyzer \
  --location=$REGION \
  --project=$PROJECT_ID
```

### Test via curl (for debugging):
```bash
# Since service is public, no authentication needed
SERVICE_URL="https://polytrade-live-sports-us-central1-516809641795.run.app/run"

curl -X POST $SERVICE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "max_workers": 15,
    "lookback_hours": 4.0,
    "min_liquidity": 500.0,
    "min_ask_price": 0.93,
    "max_ask_price": 0.96
  }'
```

## Monitoring

- **View logs**: Cloud Run → polytrade-live-sports → Logs
- **View job history**: Cloud Scheduler → live-sports-analyzer → View History
- **Set up alerts**: Create alerting policies for failed job executions

## Troubleshooting

1. **403 Forbidden**: Check service account has Cloud Run Invoker role
2. **404 Not Found**: Verify the service URL is correct
3. **500 Internal Server Error**: Check Cloud Run logs for details
4. **Timeout**: Increase Cloud Run timeout if analysis takes longer than default (300s)

## Updating an Existing Job

```bash
# Update the URL (if it's missing /run)
gcloud scheduler jobs update http live-sports-analyzer \
  --location=us-central1 \
  --project=polytrade-476720 \
  --uri="https://polytrade-live-sports-516809641795.us-central1.run.app/run"

# Update parameters
gcloud scheduler jobs update http live-sports-analyzer \
  --location=us-central1 \
  --project=polytrade-476720 \
  --message-body='{
    "max_workers": 15,
    "lookback_hours": 4.0,
    "min_liquidity": 500.0,
    "min_ask_price": 0.93,
    "max_ask_price": 0.96
  }'
```

## Notes

- The service will send Telegram notifications via `bot_b` when markets are found
- All parameters are optional - if omitted, defaults will be used
- The service returns a JSON response with `filtered_markets_found` and `parameters` fields
- Make sure `BOT_B_DEFAULT_CHAT_ID` and `TELEGRAM_BOT_B_TOKEN` are configured in Cloud Run environment variables/secrets

