from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings


class YooKassaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class YooKassaPayment:
    id: str
    status: str
    amount: Decimal
    currency: str
    metadata: dict[str, str]
    confirmation_url: str | None = None


class YooKassaProvider:
    def __init__(self, settings: Settings) -> None:
        shop_id = (settings.yookassa_shop_id or "").strip()
        secret_key = (settings.yookassa_secret_key or "").strip()
        if not shop_id or not secret_key:
            raise YooKassaError("YooKassa is not configured")
        self.base_url = settings.yookassa_base_url.rstrip("/")
        self.auth = httpx.BasicAuth(shop_id, secret_key)

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        idempotence_key: str,
    ) -> YooKassaPayment:
        payload: dict[str, Any] = {
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": metadata,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), auth=self.auth) as client:
            response = await client.post(
                f"{self.base_url}/payments",
                headers={"Idempotence-Key": idempotence_key},
                json=payload,
            )
        return self._parse_response(response, operation="create payment")

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), auth=self.auth) as client:
            response = await client.get(f"{self.base_url}/payments/{payment_id}")
        return self._parse_response(response, operation="get payment")

    @staticmethod
    def _parse_response(response: httpx.Response, *, operation: str) -> YooKassaPayment:
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("description") or payload.get("code") or str(payload)
            except ValueError:
                message = response.text[:300]
            raise YooKassaError(f"YooKassa {operation} failed ({response.status_code}): {message}")

        payload = response.json()
        amount = payload.get("amount") or {}
        confirmation = payload.get("confirmation") or {}
        metadata = payload.get("metadata") or {}
        payment_id = str(payload.get("id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not payment_id or not status or not amount.get("value") or not amount.get("currency"):
            raise YooKassaError(f"YooKassa {operation} returned an incomplete payment object")
        return YooKassaPayment(
            id=payment_id,
            status=status,
            amount=Decimal(str(amount["value"])),
            currency=str(amount["currency"]),
            metadata={str(key): str(value) for key, value in metadata.items()},
            confirmation_url=(
                str(confirmation.get("confirmation_url"))
                if confirmation.get("confirmation_url")
                else None
            ),
        )
