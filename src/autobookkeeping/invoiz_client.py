from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from autobookkeeping.config import Settings


class InvoizClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None

    def connect(self) -> dict[str, Any]:
        token = self.token()
        return {"ok": True, "token_present": bool(token)}

    def token(self) -> str:
        if self._token:
            return self._token
        if not (
            self.settings.invoiz_installation_id
            and self.settings.invoiz_api_key
            and self.settings.invoiz_api_secret
        ):
            raise RuntimeError("INVOIZ_INSTALLATION_ID, INVOIZ_API_KEY oder INVOIZ_API_SECRET fehlt")

        response = httpx.post(
            self._url("auth/token"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"installationId": self.settings.invoiz_installation_id},
            auth=(self.settings.invoiz_api_key, self.settings.invoiz_api_secret),
            timeout=30,
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise RuntimeError("invoiz hat keinen token zurückgegeben")
        self._token = str(token)
        return self._token

    def get_pay_conditions(self) -> Any:
        return self._request("GET", "setting/payCondition")

    def list_invoices(self, limit: int = 20, offset: int = 0, search_text: str = "") -> Any:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if search_text:
            params["searchText"] = search_text
        return self._request(
            "GET",
            "invoice",
            params=params,
        )

    def get_invoice(self, invoice_id: int | str) -> Any:
        return self._request("GET", f"invoice/{invoice_id}")

    def download_invoice(self, invoice_id: int | str) -> bytes:
        response = httpx.request(
            "GET",
            self._url(f"invoice/{invoice_id}/download"),
            headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/pdf"},
            timeout=60,
        )
        if response.is_error:
            raise RuntimeError(
                f"invoiz GET invoice/{invoice_id}/download failed: "
                f"{response.status_code} {response.text[:1000]}"
            )
        return response.content

    def create_invoice(self, invoice_payload: dict[str, Any]) -> Any:
        return self._request("POST", "v2/invoice/", json=invoice_payload)

    def lock_invoice(self, invoice_id: int | str) -> Any:
        return self._request("PUT", f"invoice/{invoice_id}/lock")

    def add_invoice_payment(self, invoice_id: int | str, payment_payload: dict[str, Any]) -> Any:
        return self._request("POST", f"invoice/{invoice_id}/payment", json=payment_payload)

    def list_expenses(self, limit: int = 20, offset: int = 0, search_text: str = "") -> Any:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if search_text:
            params["searchText"] = search_text
        return self._request(
            "GET",
            "expense",
            params=params,
        )

    def get_expense(self, expense_id: int | str) -> Any:
        return self._request("GET", f"expense/{expense_id}")

    def download_expense_receipt(self, receipt_url: str) -> bytes:
        """Download a receipt from the relative URL returned by an expense record."""
        parsed = urlparse(receipt_url)
        base = urlparse(self.settings.invoiz_base_url)
        if parsed.scheme or parsed.netloc:
            if (
                parsed.scheme != base.scheme
                or parsed.netloc != base.netloc
                or not parsed.path.startswith(base.path.rstrip("/") + "/")
            ):
                raise ValueError("invoiz receipt URL is outside the configured API")
            download_url = receipt_url
        else:
            relative_path = receipt_url.lstrip("/")
            if not relative_path.startswith("expense/receipt/"):
                raise ValueError("invoiz returned an unexpected receipt URL")
            download_url = self._url(relative_path)

        response = httpx.get(
            download_url,
            headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/pdf"},
            timeout=60,
        )
        if response.is_error:
            raise RuntimeError(f"invoiz GET expense receipt failed: {response.status_code}")
        if not response.content:
            raise RuntimeError("invoiz expense receipt response was empty")
        return response.content

    def upload_expense_receipt(self, receipt_path: Path) -> Any:
        with receipt_path.open("rb") as receipt:
            files = {
                "filename": (None, receipt_path.name),
                "receipt": (receipt_path.name, receipt, "application/pdf"),
            }
            return self._request("POST", "expense/receipt", files=files)

    def delete_expense_receipt(self, receipt_id: int | str) -> Any:
        return self._request("DELETE", f"expense/receipt/{receipt_id}")

    def create_expense(self, expense_payload: dict[str, Any]) -> Any:
        return self._request("POST", "expense/", json=expense_payload)

    def delete_invoice(self, invoice_id: int | str) -> Any:
        return self._request("DELETE", f"invoice/{invoice_id}")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token()}"
        headers.setdefault("Accept", "application/json")
        response = httpx.request(method, self._url(path), headers=headers, timeout=60, **kwargs)
        if response.is_error:
            raise RuntimeError(f"invoiz {method} {path} failed: {response.status_code} {response.text[:1000]}")
        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def _url(self, path: str) -> str:
        return self.settings.invoiz_base_url + path.lstrip("/")
