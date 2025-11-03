# Local Testing Scripts

This folder contains scripts for testing the PolyTrade bot locally without deploying to Cloud Run.

## Files

### `find_proxy_address.py`
Helps you find your Polymarket proxy wallet address.

**Usage:**
```bash
python LocalTests/find_proxy_address.py
```

**Requirements:** `.env` file with `WALLET_PRIVATE_KEY`

### `test_proxy_simple.py`
Tests if a proxy address has positions by directly calling the Polymarket Data API.

**Usage:**
```bash
python LocalTests/test_proxy_simple.py
```

Edit the `proxy_address` variable in the file to test different addresses.

### `test_balance_local.py`
Comprehensive test of the `get_balance()` function with both mock and real data.

**Usage:**
```bash
python LocalTests/test_balance_local.py
```

**Features:**
- Tests with mock data (always works, no credentials needed)
- Tests with real credentials if `.env` file exists
- Shows detailed logs of the balance fetching process

### `test_analyzer_local.py`
Runs the analyzer locally to debug why suggestions are or aren't being generated.

**Usage:**
```bash
python LocalTests/test_analyzer_local.py
```

**Features:**
- Fetches real sports markets from Polymarket
- Shows detailed filtering at each step
- Explains why markets are filtered out
- Displays generated suggestions with all details
- Helps debug: no suggestions, price ranges, liquidity, edge thresholds

**Requirements:** `.env` file with `WALLET_PRIVATE_KEY` and `POLYMARKET_PROXY_ADDRESS`

## Setup

1. Copy `.env.example` to `.env` (if you have one)
2. Add your credentials:
   ```
   WALLET_PRIVATE_KEY=0x...
   POLYMARKET_PROXY_ADDRESS=0x...
   ```
3. Run any test script

## Notes

- These scripts are for **local testing only**
- They are **not** deployed to Cloud Run
- They help debug issues without needing to deploy

