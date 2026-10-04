from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


from autobookkeeping.workspace import data_root


@dataclass(slots=True)
class Settings:
    invoiz_base_url: str
    invoiz_installation_id: str
    invoiz_api_key: str
    invoiz_api_secret: str
    ebay_authnauth_token: str
    ebay_app_id: str
    ebay_dev_id: str
    ebay_cert_id: str
    ebay_site_id: str
    ebay_trading_compatibility_level: str
    ebay_sandbox: bool
    gmx_imap_host: str
    gmx_imap_port: int
    gmx_email: str
    gmx_password: str
    invoiz_pay_condition_id: int | None
    bookkeeping_price_kind: str
    bookkeeping_vat_percent: float
    invoice_intro: str
    invoice_conclusion: str
    shipping_article_title: str
    shipping_article_number: str
    dhl_payee: str
    expense_pay_kind: str
    vine_backend_url: str
    vine_backend_token: str


def load_settings(env_file: Path | None = None) -> Settings:
    # Load from local .env first
    env_vars = dotenv_values(data_root() / ".env")

    # Override with custom env_file if provided
    if env_file:
        env_vars.update(dotenv_values(env_file))

    # Helper to get env value with default
    def get_env(name: str, default: str = "") -> str:
        return (env_vars.get(name) or default).strip()

    return Settings(
        invoiz_base_url=get_env("INVOIZ_BASE_URL", "https://app.invoiz.de/api/").rstrip("/") + "/",
        invoiz_installation_id=get_env("INVOIZ_INSTALLATION_ID"),
        invoiz_api_key=get_env("INVOIZ_API_KEY"),
        invoiz_api_secret=get_env("INVOIZ_API_SECRET"),
        ebay_authnauth_token=get_env("EBAY_AUTHNAUTH_TOKEN"),
        ebay_app_id=get_env("EBAY_APP_ID"),
        ebay_dev_id=get_env("EBAY_DEV_ID"),
        ebay_cert_id=get_env("EBAY_CERT_ID"),
        ebay_site_id=get_env("EBAY_SITE_ID", "77"),
        ebay_trading_compatibility_level=get_env("EBAY_TRADING_COMPATIBILITY_LEVEL", "1423"),
        ebay_sandbox=get_env("EBAY_SANDBOX", "false").lower() == "true",
        gmx_imap_host=get_env("GMX_IMAP_HOST", "imap.gmx.net"),
        gmx_imap_port=int(get_env("GMX_IMAP_PORT", "993")),
        gmx_email=get_env("GMX_EMAIL"),
        gmx_password=get_env("GMX_PASSWORD"),
        invoiz_pay_condition_id=_int_or_none(get_env("INVOIZ_PAY_CONDITION_ID")),
        bookkeeping_price_kind=get_env("BOOKKEEPING_PRICE_KIND", "gross"),
        bookkeeping_vat_percent=float(get_env("BOOKKEEPING_VAT_PERCENT", "0")),
        invoice_intro=get_env(
            "BOOKKEEPING_INVOICE_INTRO",
            "Vielen Dank für Ihren Kauf. Wir berechnen Ihnen folgende Lieferung:",
        ),
        invoice_conclusion=get_env(
            "BOOKKEEPING_INVOICE_CONCLUSION",
            "",
        ),
        shipping_article_title=get_env("BOOKKEEPING_SHIPPING_ARTICLE_TITLE", "Versandkosten"),
        shipping_article_number=get_env("BOOKKEEPING_SHIPPING_ARTICLE_NUMBER", "VERSAND"),
        dhl_payee=get_env("BOOKKEEPING_DHL_PAYEE", "DHL"),
        expense_pay_kind=get_env("BOOKKEEPING_EXPENSE_PAY_KIND", "bank"),
        vine_backend_url=get_env("VINE_BACKEND_URL", ""),
        vine_backend_token=get_env("VINE_BACKEND_TOKEN"),
    )

def _int_or_none(value: str) -> int | None:
    if not value:
        return None
    return int(value)
