# rot-signals-api

> REST + WebSocket API for [Reddit Options Trader](https://github.com/Mattbusel/Reddit-Options-Trader-ROT-) signals.
> Real-time for paid tiers. 15-minute delayed for free.

Turn Reddit's collective intelligence into structured, actionable options signals — consumable by any language, any platform.

## Quick Start

```bash
pip install rot-signals-api
rot-api
# -> http://localhost:8000/docs
```

Or from source:

```bash
git clone https://github.com/Mattbusel/rot-signals-api
cd rot-signals-api
pip install -e ".[dev]"
DATABASE_URL=sqlite+aiosqlite:///./rot.db rot-api
```

## Get a Free API Key

```bash
curl -X POST http://localhost:8000/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app", "tier": "free"}'
# -> {"key": "rot_...", "tier": "free", "rpm_limit": 20}
```

**Store the key -- it's shown once.**

## REST Endpoints

```
GET  /v1/signals              List signals (paginated, filterable)
GET  /v1/signals/trending     Top tickers by mention count
GET  /v1/signals/{id}         Signal detail + related
POST /v1/keys                 Create API key
GET  /v1/keys/me              Current key info
GET  /v1/health               Liveness probe
```

Full interactive docs at `/docs` (Swagger) or `/redoc`.

### Example: Fetch bullish signals on NVDA

```python
import httpx

resp = httpx.get(
    "http://localhost:8000/v1/signals",
    params={"ticker": "NVDA", "stance": "bullish", "min_confidence": 0.7},
    headers={"X-API-Key": "rot_your_key_here"},
)
signals = resp.json()["signals"]
```

### Example: WebSocket real-time stream (Pro)

```python
import asyncio, json, websockets

async def stream():
    uri = "ws://localhost:8000/v1/ws/signals?api_key=rot_your_pro_key"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "subscribe",
            "data": {"tickers": ["AAPL", "TSLA"], "min_confidence": 0.6}
        }))
        async for msg in ws:
            print(json.loads(msg))

asyncio.run(stream())
```

## Tier Comparison

| | Free | Pro | Enterprise |
|---|---|---|---|
| Delay | 15 min | Real-time | Real-time |
| Page size | 10 | 200 | 1000 |
| Rate limit | 20 req/min | 300 req/min | 5000 req/min |
| WebSocket | 1 conn (delayed) | 5 conns | Custom |
| Reasoning | Redacted | Full | Full |
| Trade legs | Redacted | Full | Full |
| Date range filter | No | Yes | Yes |

## Configuration

All settings via environment variables (or `.env` file):

```bash
DATABASE_URL=sqlite+aiosqlite:///./rot.db
SECRET_KEY=your-secret-key-here
FREE_DELAY_SECONDS=900
FREE_PAGE_LIMIT=10
FREE_RPM=20
PRO_RPM=300
PORT=8000
```

## Architecture

```
rot-signals-api/
├── api/
│   ├── main.py                  # FastAPI app factory
│   ├── middleware/rate_limit.py # Sliding-window rate limiter
│   └── v1/routes/
│       ├── signals.py           # Signal list + detail + trending
│       ├── keys.py              # API key management
│       ├── ws.py                # WebSocket signal stream
│       └── health.py            # Health probe
├── core/
│   ├── config.py                # Settings (pydantic-settings)
│   ├── models.py                # Pydantic v2 wire types
│   ├── database.py              # Async SQLite adapter (aiosqlite)
│   ├── auth.py                  # API key generation + validation
│   └── gating.py                # Tier-based signal gating
└── tests/                       # 46 tests, 100% passing
```

## Related Projects by @Mattbusel

- [Reddit-Options-Trader-ROT](https://github.com/Mattbusel/Reddit-Options-Trader-ROT-) -- core signal engine
- [fin-primitives](https://github.com/Mattbusel/fin-primitives) -- financial market primitives
- [fin-stream](https://github.com/Mattbusel/fin-stream) -- streaming market data integration
- [tokio-prompt-orchestrator](https://github.com/Mattbusel/tokio-prompt-orchestrator) -- Rust LLM orchestration
- [prompt-observatory](https://github.com/Mattbusel/prompt-observatory) -- LLM interpretability dashboard

## License

MIT
