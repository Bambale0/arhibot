from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from time import monotonic
from typing import Any

import httpx

from app.core.config import Settings
from app.core.resilience import (
    CircuitOpenError,
    RetryPolicy,
    get_circuit_breaker,
    request_with_resilience,
)


class YooKassaError(RuntimeError):
    def __init__(self, message: str, *, ambiguous: bool = False) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


@dataclass(frozen=True, slots=True)
class YooKassaPayment:
    id: str
    status: str
    amount: Decimal
    currency: str
    metadata: dict[str, str]
    confirmation_url: str | None = None


@dataclass(frozen=True, slots=True)
class YooKassaRefund:
    id: str
    payment_id: str
    status: str
    amount: Decimal
    currency: str


class YooKassaProvider:
    def __init__(self, settings: Settings) -> None:
        shop_id = (settings.yookassa_shop_id or "").strip()
        secret_key = (settings.yookassa_secret_key or "").strip()
        if not shop_id or not secret_key:
            raise YooKassaError("YooKassa is not configured")
        self.base_url = settings.yookassa_base_url.rstrip("/")
        self.auth = httpx.BasicAuth(shop_id, secret_key)
        self.breaker = get_circuit_breaker(
            "yookassa",
            failure_threshold=settings.yookassa_circuit_failure_threshold,
            recovery_seconds=settings.yookassa_circuit_recovery_seconds,
        )
        self.retry_policy = RetryPolicy(max_attempts=settings.yookassa_retry_attempts)
        self.request_deadline_seconds = settings.yookassa_request_deadline_seconds
        self.http_timeout = httpx.Timeout(
            settings.yookassa_http_read_timeout_seconds,
            connect=settings.yookassa_http_connect_timeout_seconds,
        )

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        idempotence_key: str,
        receipt: dict[str, Any] | None = None,
    ) -> YooKassaPayment:
        payload: dict[str, Any] = {
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": metadata,
        }
        if receipt is not None:
            payload["receipt"] = receipt
        response = await self._request(
            "create payment",
            lambda client: client.post(
                f"{self.base_url}/payments",
                headers={"Idempotence-Key": idempotence_key},
                json=payload,
            ),
            mutation=True,
        )
        return self._parse_payment(response, operation="create payment")

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        response = await self._request(
            "get payment", lambda client: client.get(f"{self.base_url}/payments/{payment_id}")
        )
        return self._parse_payment(response, operation="get payment")

    async def create_refund(
        self,
        *,
        payment_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        idempotence_key: str,
    ) -> YooKassaRefund:
        payload = {
            "payment_id": payment_id,
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "description": description[:250],
        }
        response = await self._request(
            "create refund",
            lambda client: client.post(
                f"{self.base_url}/refunds",
                headers={"Idempotence-Key": idempotence_key},
                json=payload,
            ),
            mutation=True,
        )
        return self._parse_refund(response, operation="create refund")

    async def get_refund(self, refund_id: str) -> YooKassaRefund:
        response = await self._request(
            "get refund", lambda client: client.get(f"{self.base_url}/refunds/{refund_id}")
        )
        return self._parse_refund(response, operation="get refund")


    async def _request(
        self,
        operation: str,
        request_factory: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]],
        *,
        mutation: bool = False,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.http_timeout, auth=self.auth) as client:
            try:
                response = await request_with_resilience(
                    lambda: request_factory(client),
                    dependency="yookassa",
                    operation=operation.replace(" ", "_"),
                    breaker=self.breaker,
                    policy=self.retry_policy,
                    deadline_monotonic=monotonic() + self.request_deadline_seconds,
                )
                if mutation and response.status_code in {408, 500, 502, 503, 504}:
                    raise YooKassaError(
                        f"YooKassa {operation} outcome is uncertain",
                        ambiguous=True,
                    )
                return response
            except CircuitOpenError as exc:
                raise YooKassaError("YooKassa is temporarily unavailable") from exc
            except (httpx.HTTPError, TimeoutError) as exc:
                raise YooKassaError(
                    f"YooKassa {operation} request failed",
                    ambiguous=mutation,
                ) from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload.get("description") or payload.get("code") or payload)
        except ValueError:
            return response.text[:300]

    @classmethod
    def _parse_payment(cls, response: httpx.Response, *, operation: str) -> YooKassaPayment:
        if response.status_code >= 400:
            raise YooKassaError(
                f"YooKassa {operation} failed ({response.status_code}): {cls._error_message(response)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise YooKassaError(f"YooKassa {operation} returned invalid JSON") from exc
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

    @classmethod
    def _parse_refund(cls, response: httpx.Response, *, operation: str) -> YooKassaRefund:
        if response.status_code >= 400:
            raise YooKassaError(
                f"YooKassa {operation} failed ({response.status_code}): {cls._error_message(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise YooKassaError(f"YooKassa {operation} returned invalid JSON") from exc
        amount = payload.get("amount") or {}
        refund_id = str(payload.get("id") or "").strip()
        payment_id = str(payload.get("payment_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not refund_id or not payment_id or not status or not amount.get("value") or not amount.get("currency"):
            raise YooKassaError(f"YooKassa {operation} returned an incomplete refund object")
        return YooKassaRefund(
            id=refund_id,
            payment_id=payment_id,
            status=status,
            amount=Decimal(str(amount["value"])),
            currency=str(amount["currency"]),
        )
