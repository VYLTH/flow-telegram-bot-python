"""
Flow Payment Integration — Drop-in crypto payments for Telegram bots.

Usage:
    from flow_payments import FlowPayments

    flow = FlowPayments(api_key="fl_...", api_secret="your_secret")
    invoice = await flow.create_invoice(amount=25.00, network="bsc")
    # Send invoice["payment_url"] to your user
"""

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

FLOW_API_URL = "https://flow.vylth.com/api/flow"


class FlowPayments:
    """Async client for the Flow crypto payment API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        vendor_key: Optional[str] = None,
        vendor_secret: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        api_url: str = FLOW_API_URL,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.vendor_key = vendor_key
        self.vendor_secret = vendor_secret
        self.webhook_secret = webhook_secret
        self.api_url = api_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Invoices (Deposits) ──────────────────────────────────────────

    async def create_invoice(
        self,
        amount: float,
        network: str = "bsc",
        currency: str = "USDT",
        customer_name: str = "",
        customer_email: str = "",
        metadata: Optional[dict] = None,
        callback_url: Optional[str] = None,
    ) -> dict:
        """
        Create a payment invoice. Returns dict with:
          - id: invoice ID
          - payment_url: URL to send to the customer
          - deposit_address: crypto address
          - crypto_amount: exact amount to send
          - expires_at: ISO timestamp
        """
        session = await self._get_session()
        payload = {
            "amount": float(Decimal(str(amount)).quantize(Decimal("0.01"))),
            "crypto_currency": currency.upper(),
            "network": network.lower(),
            "customer_name": customer_name,
        }
        if customer_email:
            payload["customer_email"] = customer_email
        if metadata:
            payload["metadata"] = metadata
        if callback_url:
            payload["callback_url"] = callback_url

        async with session.post(
            f"{self.api_url}/invoices/",
            headers={
                "X-API-Key": self.api_key,
                "X-API-Secret": self.api_secret,
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise FlowAPIError(resp.status, data)
            return data

    async def get_invoice(self, invoice_id: str) -> dict:
        """Get invoice status. Check data["status"] for: pending, confirming, completed, expired."""
        session = await self._get_session()
        async with session.get(
            f"{self.api_url}/invoices/{invoice_id}",
            headers={
                "X-API-Key": self.api_key,
                "X-API-Secret": self.api_secret,
            },
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise FlowAPIError(resp.status, data)
            return data

    # ── Payouts (Withdrawals) ────────────────────────────────────────

    async def create_payout(
        self,
        amount: float,
        recipient_address: str,
        network: str = "bsc",
        currency: str = "USDT",
        reference_id: str = "",
        recipient_name: str = "",
        note: str = "",
    ) -> dict:
        """
        Send crypto to an address. Requires vendor keys.
        Returns dict with payout_id.
        """
        if not self.vendor_key or not self.vendor_secret:
            raise FlowAPIError(0, {"error": "Vendor keys required for payouts"})

        session = await self._get_session()
        payload = {
            "amount": float(Decimal(str(amount)).quantize(Decimal("0.01"))),
            "currency": currency.upper(),
            "network": network.lower(),
            "recipient_address": recipient_address,
        }
        if reference_id:
            payload["reference_id"] = reference_id
        if recipient_name:
            payload["recipient_name"] = recipient_name
        if note:
            payload["note"] = note

        async with session.post(
            f"{self.api_url}/vendor/payout",
            headers={
                "X-Vendor-Key": self.vendor_key,
                "X-Vendor-Secret": self.vendor_secret,
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise FlowAPIError(resp.status, data)
            return data

    # ── Webhook Verification ─────────────────────────────────────────

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        """
        Verify a Flow webhook signature.
        Pass the raw request body (bytes) and the X-Flow-Signature header value.
        """
        if not self.webhook_secret:
            logger.warning("No webhook_secret configured — skipping verification")
            return True

        expected = hmac.new(
            self.webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        # Header may be "sha256=<hex>" or just "<hex>"
        sig = signature.replace("sha256=", "")
        return hmac.compare_digest(expected, sig)


class FlowAPIError(Exception):
    def __init__(self, status: int, data: dict):
        self.status = status
        self.data = data
        super().__init__(f"Flow API error {status}: {data}")
