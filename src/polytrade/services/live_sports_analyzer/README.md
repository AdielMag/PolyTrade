# Live Sports Market Analyzer

A high-performance service that fetches and analyzes all live sports markets from Polymarket using pagination and multithreading.

## Features

- 🚀 **Pagination**: Fetches ALL markets from Polymarket API using efficient pagination
- ⚡ **Multithreading**: Uses concurrent threads (10 by default) for fast parallel fetching
- 🏀 **Sports Filtering**: Filters for sports-related markets using official sports tag IDs and keyword matching
- 🔴 **Live Detection**: Identifies markets where the game has already started (within configurable lookback window)
- 📊 **Comprehensive Logging**: Logs full market details including:
  - Market title and status
  - Start time and time since start
  - Liquidity and volume metrics
  - All outcomes with token IDs
  - Real-time pricing data (best bid/ask/spread) for each outcome

## Architecture

### Key Components

1. **`live_sports_analysis.py`** - Core analysis logic
   - `fetch_markets_page()` - Fetches a single page of markets
   - `fetch_all_sports_markets()` - Coordinates paginated fetching with multithreading
   - `filter_live_markets()` - Filters for live games only
   - `fetch_market_pricing()` - Gets order book data for all outcomes
   - `log_market_details()` - Logs comprehensive market information
   - `run_live_sports_analysis()` - Main entry point

2. **`app.py`** - FastAPI application
   - `POST /run` - Triggers the analysis
   - `GET /health` - Health check endpoint

### How It Works

1. **Fetch Sports Tags**: Retrieves sports tag IDs from `/sports` endpoint
2. **Paginated Fetching**: 
   - Fetches markets in pages of 100 using `/markets` endpoint
   - Uses ThreadPoolExecutor to fetch multiple pages concurrently
   - Continues until all pages are retrieved
3. **Sports Filtering**: Filters markets by sports tag IDs or sports keywords
4. **Live Filtering**: 
   - Checks `gameStartTime`, `eventStartTime`, or `endDate` fields
   - Includes only games that have started within the lookback window (default: 4 hours)
5. **Detail Collection**: For each live market, fetches and logs:
   - Market metadata (title, ID, status, tags)
   - Timing information (start time, hours since start)
   - Financial metrics (liquidity, volume)
   - Outcomes and token IDs
   - Real-time pricing from order book

## Usage

### As a Service (FastAPI)

Run the service:
```bash
cd src/polytrade/services/live_sports_analyzer
uvicorn app:app --host 0.0.0.0 --port 8000
```

Trigger analysis:
```bash
curl -X POST http://localhost:8000/run
```

### As a Python Module

```python
from polytrade.services.live_sports_analyzer.live_sports_analysis import run_live_sports_analysis

# Run analysis
live_markets = run_live_sports_analysis(
    max_workers=10,        # Number of concurrent threads
    lookback_hours=4.0     # How many hours back to include live games
)

print(f"Found {len(live_markets)} live sports markets")
```

### Test Script

A test script is provided in `LocalTests/`:

```bash
cd LocalTests
python test_live_sports_analyzer.py
```

## Configuration

### Parameters

- **`max_workers`** (default: 10)
  - Number of concurrent threads for fetching market pages
  - Higher values = faster fetching but more API load
  - Recommended: 5-15

- **`lookback_hours`** (default: 4.0)
  - How many hours back to include live games
  - Games that started within this window are considered "live"
  - Recommended: 2-6 hours

## API Endpoints

### Polymarket API Endpoints Used

1. **Sports Metadata**: `GET https://gamma-api.polymarket.com/sports`
   - Returns sports tag IDs for filtering

2. **Markets**: `GET https://gamma-api.polymarket.com/markets`
   - Parameters: `closed=false`, `limit=100`, `offset=<page*100>`
   - Returns market data with pagination

3. **Order Book**: `GET https://clob.polymarket.com/book?token_id=<token_id>`
   - Returns best bid/ask prices for a specific outcome

## Output

The service logs comprehensive information for each live market:

```
================================================================================
LIVE MARKET #1/5
================================================================================
📊 TITLE: Will Team A beat Team B? (NBA)
🔑 Condition ID: 0x1234...
📍 STATUS: ✅ ACCEPTING ORDERS | 🟢 ACTIVE
⏰ STARTED: 2024-11-13 19:00 UTC (2.3h ago)
💧 LIQUIDITY: $15,234.50
📈 VOLUME (24h): $45,678.90
📈 VOLUME (total): $123,456.78
🎯 OUTCOMES: 2 options
   1. YES (Token: 0xabc...)
   2. NO (Token: 0xdef...)

💰 PRICING DATA (Order Book):
--------------------------------------------------------------------------------
   YES:
      Best Bid: $0.6500 (65.00%)
      Best Ask: $0.6520 (65.20%)
      Spread:   $0.0020 (0.20%)
   NO:
      Best Bid: $0.3480 (34.80%)
      Best Ask: $0.3500 (35.00%)
      Spread:   $0.0020 (0.20%)
================================================================================
```

## Future Enhancements

Based on user requirements, future additions will include:
- **Price-based filtering**: Select specific markets based on pricing criteria
- **Automated trading**: Execute trades on selected markets
- **Telegram notifications**: Send updates about actions to Telegram bot

## Notes

- No authentication required (read-only operations)
- No Telegram/messaging integration (intentionally excluded for now)
- Respects Polymarket API rate limits with retry logic
- Handles both binary (YES/NO) and multi-outcome markets

