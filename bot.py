"""
Telegram Bot with Flow Crypto Payments — Template

A minimal, production-ready Telegram bot that accepts crypto deposits
and processes withdrawals using Flow (flow.vylth.com).

Run:  python bot.py
"""

import asyncio
import logging
import os

from aiohttp import web
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from flow_payments import FlowPayments

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # e.g. https://yourdomain.com/webhook/flow
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))

flow = FlowPayments(
    api_key=os.getenv("FLOW_API_KEY", ""),
    api_secret=os.getenv("FLOW_API_SECRET", ""),
    vendor_key=os.getenv("FLOW_VENDOR_KEY"),
    vendor_secret=os.getenv("FLOW_VENDOR_SECRET"),
    webhook_secret=os.getenv("FLOW_WEBHOOK_SECRET"),
)

# Simple in-memory store. Replace with your database.
user_balances: dict[int, float] = {}
pending_invoices: dict[str, int] = {}  # invoice_id -> telegram_user_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Networks ─────────────────────────────────────────────────────────

NETWORKS = {
    "bsc": "BSC (BEP-20)",
    "tron": "Tron (TRC-20)",
    "ethereum": "Ethereum (ERC-20)",
    "solana": "Solana",
    "polygon": "Polygon",
    "ton": "TON",
    "arbitrum": "Arbitrum",
    "avalanche": "Avalanche",
}

# ── Bot Commands ─────────────────────────────────────────────────────


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /start — show main menu."""
    keyboard = [
        [
            InlineKeyboardButton("Deposit", callback_data="deposit"),
            InlineKeyboardButton("Withdraw", callback_data="withdraw"),
        ],
        [InlineKeyboardButton("Balance", callback_data="balance")],
    ]
    await update.message.reply_text(
        "Welcome! Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /balance — show current balance."""
    uid = update.effective_user.id
    balance = user_balances.get(uid, 0.0)
    await update.message.reply_text(f"Your balance: ${balance:.2f}")


# ── Deposit Flow ─────────────────────────────────────────────────────


async def handle_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 1: User taps Deposit → show network selection."""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"deposit_net:{net}")]
        for net, label in NETWORKS.items()
    ]
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])

    await query.edit_message_text(
        "Select a network:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_deposit_network(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 2: Network selected → ask for amount."""
    query = update.callback_query
    await query.answer()

    network = query.data.split(":")[1]
    ctx.user_data["deposit_network"] = network

    await query.edit_message_text(
        f"Network: {NETWORKS[network]}\n\nEnter the deposit amount in USD (e.g. 50):"
    )
    ctx.user_data["awaiting_deposit_amount"] = True


async def handle_deposit_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 3: Amount entered → create Flow invoice and show payment link."""
    if not ctx.user_data.get("awaiting_deposit_amount"):
        return

    try:
        amount = float(update.message.text.strip().replace("$", ""))
        if amount < 1:
            await update.message.reply_text("Minimum deposit is $1.")
            return
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return

    ctx.user_data["awaiting_deposit_amount"] = False
    network = ctx.user_data.pop("deposit_network", "bsc")
    uid = update.effective_user.id
    name = update.effective_user.first_name or str(uid)

    await update.message.reply_text("Creating invoice...")

    try:
        invoice = await flow.create_invoice(
            amount=amount,
            network=network,
            currency="USDT",
            customer_name=f"{name} ({uid})",
            metadata={"telegram_user_id": uid},
            callback_url=WEBHOOK_URL,
        )
    except Exception as e:
        logger.error(f"Failed to create invoice: {e}")
        await update.message.reply_text("Failed to create invoice. Try again later.")
        return

    invoice_id = invoice.get("id", "")
    payment_url = invoice.get("payment_url", "")
    deposit_address = invoice.get("deposit_address", "")
    crypto_amount = invoice.get("crypto_amount", "")

    # Track this invoice
    pending_invoices[invoice_id] = uid

    keyboard = [[InlineKeyboardButton("Open Payment Page", url=payment_url)]]

    await update.message.reply_text(
        f"Send exactly {crypto_amount} USDT ({NETWORKS[network]})\n\n"
        f"Address:\n`{deposit_address}`\n\n"
        f"Or tap the button below to pay:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ── Withdraw Flow ────────────────────────────────────────────────────


async def handle_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 1: User taps Withdraw → show network selection."""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"withdraw_net:{net}")]
        for net, label in list(NETWORKS.items())[:3]  # BSC, Tron, ETH
    ]
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])

    await query.edit_message_text(
        "Select withdrawal network:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_withdraw_network(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 2: Network selected → ask for wallet address."""
    query = update.callback_query
    await query.answer()

    network = query.data.split(":")[1]
    ctx.user_data["withdraw_network"] = network

    await query.edit_message_text(
        f"Network: {NETWORKS[network]}\n\nSend your wallet address:"
    )
    ctx.user_data["awaiting_withdraw_address"] = True


async def handle_withdraw_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 3: Address entered → ask for amount."""
    if not ctx.user_data.get("awaiting_withdraw_address"):
        return

    address = update.message.text.strip()
    if len(address) < 20:
        await update.message.reply_text("Invalid address. Try again.")
        return

    ctx.user_data["awaiting_withdraw_address"] = False
    ctx.user_data["withdraw_address"] = address
    ctx.user_data["awaiting_withdraw_amount"] = True

    uid = update.effective_user.id
    balance = user_balances.get(uid, 0.0)
    await update.message.reply_text(
        f"Balance: ${balance:.2f}\n\nEnter withdrawal amount in USD:"
    )


async def handle_withdraw_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Step 4: Amount entered → confirm and process payout."""
    if not ctx.user_data.get("awaiting_withdraw_amount"):
        return

    try:
        amount = float(update.message.text.strip().replace("$", ""))
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return

    uid = update.effective_user.id
    balance = user_balances.get(uid, 0.0)

    if amount <= 0 or amount > balance:
        await update.message.reply_text(f"Invalid amount. Your balance is ${balance:.2f}.")
        return

    ctx.user_data["awaiting_withdraw_amount"] = False
    network = ctx.user_data.pop("withdraw_network", "bsc")
    address = ctx.user_data.pop("withdraw_address", "")

    # Deduct balance
    user_balances[uid] = balance - amount

    await update.message.reply_text("Processing withdrawal...")

    try:
        payout = await flow.create_payout(
            amount=amount,
            recipient_address=address,
            network=network,
            currency="USDT",
            reference_id=f"bot_withdraw_{uid}_{int(asyncio.get_event_loop().time())}",
        )
        payout_id = payout.get("payout_id", payout.get("id", ""))
        await update.message.reply_text(
            f"Withdrawal submitted!\n\n"
            f"Amount: ${amount:.2f} USDT\n"
            f"Network: {NETWORKS[network]}\n"
            f"Payout ID: `{payout_id}`\n\n"
            f"You'll be notified when it's sent.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Payout failed: {e}")
        # Refund balance
        user_balances[uid] = user_balances.get(uid, 0.0) + amount
        await update.message.reply_text("Withdrawal failed. Balance restored. Try again later.")


# ── Callbacks ────────────────────────────────────────────────────────


async def handle_balance_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    balance = user_balances.get(uid, 0.0)
    await query.edit_message_text(f"Your balance: ${balance:.2f}")


async def handle_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text("Cancelled.")


# ── Text Router ──────────────────────────────────────────────────────


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Route text messages to the correct handler based on state."""
    if ctx.user_data.get("awaiting_deposit_amount"):
        await handle_deposit_amount(update, ctx)
    elif ctx.user_data.get("awaiting_withdraw_address"):
        await handle_withdraw_address(update, ctx)
    elif ctx.user_data.get("awaiting_withdraw_amount"):
        await handle_withdraw_amount(update, ctx)
    else:
        await update.message.reply_text("Use /start to see options.")


# ── Flow Webhook Server ─────────────────────────────────────────────


async def handle_flow_webhook(request: web.Request):
    """
    Receive payment notifications from Flow.

    Flow sends webhooks when:
      - invoice.paid / invoice.completed → deposit confirmed
      - payout.completed / payout.failed → withdrawal processed
    """
    raw_body = await request.read()
    signature = request.headers.get("X-Flow-Signature", "")

    if not flow.verify_webhook(raw_body, signature):
        logger.warning("Invalid webhook signature")
        return web.json_response({"error": "invalid signature"}, status=401)

    data = await request.json()
    event = data.get("event", "")
    payload = data.get("data", data)

    logger.info(f"Webhook received: {event}")

    if event in ("invoice.paid", "invoice.completed"):
        await _handle_deposit_webhook(payload)
    elif event == "payout.completed":
        await _handle_payout_webhook(payload)
    elif event == "payout.failed":
        await _handle_payout_failed(payload)

    return web.json_response({"status": "ok"})


async def _handle_deposit_webhook(data: dict):
    """Credit user balance when a deposit is confirmed."""
    invoice_id = data.get("invoice_id", data.get("id", ""))
    fiat_amount = float(data.get("fiat_amount", data.get("amount", 0)))

    # Find the user from our tracking dict
    metadata = data.get("metadata", {})
    uid = metadata.get("telegram_user_id")

    if not uid:
        uid = pending_invoices.get(invoice_id)

    if not uid:
        # Try parsing from customer_name: "Name (12345)"
        customer_name = data.get("customer_name", "")
        if "(" in customer_name:
            try:
                uid = int(customer_name.split("(")[-1].rstrip(")"))
            except ValueError:
                pass

    if not uid:
        logger.error(f"Could not identify user for invoice {invoice_id}")
        return

    uid = int(uid)
    user_balances[uid] = user_balances.get(uid, 0.0) + fiat_amount
    pending_invoices.pop(invoice_id, None)

    logger.info(f"Credited ${fiat_amount:.2f} to user {uid}")

    # TODO: Send a Telegram message to notify the user
    # You'll need to pass the bot application to this handler
    # or use a global reference. Example:
    #
    #   await bot_app.bot.send_message(
    #       chat_id=uid,
    #       text=f"Deposit confirmed! +${fiat_amount:.2f}\nNew balance: ${user_balances[uid]:.2f}"
    #   )


async def _handle_payout_webhook(data: dict):
    """Log successful payout."""
    payout_id = data.get("payout_id", data.get("id", ""))
    tx_hash = data.get("tx_hash", "")
    logger.info(f"Payout {payout_id} completed. TX: {tx_hash}")

    # TODO: Notify user their withdrawal was sent with tx_hash


async def _handle_payout_failed(data: dict):
    """Handle failed payout — refund the user."""
    payout_id = data.get("payout_id", data.get("id", ""))
    amount = float(data.get("amount", 0))
    logger.error(f"Payout {payout_id} failed. Amount: {amount}")

    # TODO: Refund user balance and notify them


async def health_check(request: web.Request):
    return web.json_response({"status": "healthy"})


# ── Main ─────────────────────────────────────────────────────────────


async def main():
    # Build the Telegram bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(handle_deposit, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(handle_deposit_network, pattern="^deposit_net:"))
    app.add_handler(CallbackQueryHandler(handle_withdraw, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(handle_withdraw_network, pattern="^withdraw_net:"))
    app.add_handler(CallbackQueryHandler(handle_balance_button, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(handle_cancel, pattern="^cancel$"))

    # Text input (amounts, addresses)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start the bot (polling mode — no Telegram webhook needed)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Start webhook server for Flow payment callbacks
    webhook_app = web.Application()
    webhook_app.router.add_post("/webhook/flow", handle_flow_webhook)
    webhook_app.router.add_get("/health", health_check)

    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()

    logger.info(f"Bot started. Webhook server on port {WEBHOOK_PORT}")

    # Keep running
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await flow.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
