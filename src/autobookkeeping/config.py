from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


from autobookkeeping.workspace import data_root


@dataclass(slots=True)
class Settings:
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
        vine_backend_url=get_env("VINE_BACKEND_URL", ""),
        vine_backend_token=get_env("VINE_BACKEND_TOKEN"),
    )
