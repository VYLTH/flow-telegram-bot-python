# Telegram Bot + Crypto Payments (Flow)

Accept USDT, BTC, ETH, and 20+ cryptocurrencies in your Telegram bot — across 12 blockchain networks — with a single API integration.

**No custody risk. 0.5% fees. Funds go directly to your wallet.**

Built on [Flow](https://flow.vylth.com) — the self-custody crypto payment rail.

---

## What This Is

A production-ready Telegram bot template with crypto payments baked in. Clone it, add your keys, and your bot accepts deposits and processes withdrawals in minutes.

**Two files do everything:**

| File | Purpose |
|------|---------|
| `flow_payments.py` | Drop-in Flow API client — invoices, payouts, webhook verification |
| `bot.py` | Telegram bot with deposit/withdraw flow wired up |

## Supported Networks

| Network | Tokens |
|---------|--------|
| BSC (BNB Chain) | USDT, USDC, BNB |
| Tron | USDT, TRX |
| Ethereum | USDT, USDC, ETH |
| Solana | USDT, USDC, SOL |
| Polygon | USDT, USDC, MATIC |
| TON | USDT, TON |
| Arbitrum | USDT, USDC |
| Avalanche | USDT, USDC |
| Bitcoin | BTC |
| Litecoin | LTC |
| Dogecoin | DOGE |
| XRP Ledger | XRP |

## Quick Start

### 1. Clone

```bash
git clone https://github.com/VYLTH/flow-telegram-bot-python.git
cd flow-telegram-bot-python
```

### 2. Get Your Keys

- **Telegram:** Talk to [@BotFather](https://t.me/BotFather) → create a bot → copy the token
- **Flow:** Sign up at [flow.vylth.com](https://flow.vylth.com) → API Keys → Create Key → Enable Auto-Payout

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your tokens
```

### 4. Run

**With Docker:**
```bash
docker compose up -d
```

**Without Docker:**
```bash
pip install -r requirements.txt
python bot.py
```

Your bot is now accepting crypto payments.

## How It Works

```
User taps "Deposit" in your bot
        │
        ▼
Selects network (BSC, Tron, ETH, etc.)
        │
        ▼
Enters amount ($50)
        │
        ▼
Flow generates a unique deposit address
        │
        ▼
User sends crypto (via payment page or directly)
        │
        ▼
Flow monitors the blockchain
        │
        ▼
Payment confirmed → webhook fires → balance credited
```

## The Flow API Client

`flow_payments.py` is a standalone async client you can drop into any Python project:

```python
from flow_payments import FlowPayments

flow = FlowPayments(
    api_key="fl_your_key",
    api_secret="your_secret",
    webhook_secret="your_webhook_secret",  # optional
)

# Create a payment invoice
invoice = await flow.create_invoice(
    amount=25.00,
    network="bsc",
    currency="USDT",
    customer_name="john",
    metadata={"user_id": 12345},
    callback_url="https://yourdomain.com/webhook/flow",
)

print(invoice["payment_url"])      # Send this to the customer
print(invoice["deposit_address"])  # Or show the address directly
print(invoice["crypto_amount"])    # Exact amount to send

# Check invoice status
status = await flow.get_invoice(invoice["id"])
print(status["status"])  # pending, confirming, completed, expired

# Send a payout (requires vendor keys)
payout = await flow.create_payout(
    amount=100.00,
    recipient_address="0x1234...",
    network="bsc",
    currency="USDT",
)
```

## Webhooks

Flow sends HTTP POST requests to your `callback_url` when payments are confirmed:

```json
{
  "event": "invoice.completed",
  "data": {
    "invoice_id": "inv_abc123",
    "fiat_amount": 25.00,
    "crypto_amount": "25.12",
    "crypto_currency": "USDT",
    "network": "bsc",
    "tx_hash": "0xabc...",
    "status": "completed",
    "metadata": {"user_id": 12345},
    "customer_name": "john"
  }
}
```

Verify the signature:

```python
raw_body = await request.read()
signature = request.headers["X-Flow-Signature"]
is_valid = flow.verify_webhook(raw_body, signature)
```

## Adding Payments to an Existing Bot

You don't need this whole template. Just copy `flow_payments.py` into your project:

```python
# your_existing_bot.py
from flow_payments import FlowPayments

flow = FlowPayments(api_key="fl_...", api_secret="...")

# Anywhere in your bot handler:
invoice = await flow.create_invoice(amount=10.00, network="bsc")
await bot.send_message(chat_id, f"Pay here: {invoice['payment_url']}")
```

That's it. One file, one function call, crypto payments.

## Local Development

For testing webhooks locally, use [ngrok](https://ngrok.com):

```bash
ngrok http 8080
# Copy the HTTPS URL → set as WEBHOOK_URL in .env
```

## Why Flow?

| | Flow | Typical Gateway |
|---|---|---|
| Fee | **0.5%** | 1-3% |
| Self-custody | **Yes** | No — they hold your funds |
| Chains | **12+** | 3-8 |
| Settlement | **Minutes** | Hours to days |
| Integration | **1 API call** | SDK + dashboard setup |

Your keys, your wallets, your funds. Flow never touches your money.

## Also Available

- **[Node.js version](https://github.com/VYLTH/flow-telegram-bot-nodejs)** — same template using Telegraf

## License

MIT — use it however you want.

---

Built with [Flow](https://flow.vylth.com) — the self-custody crypto payment rail.
