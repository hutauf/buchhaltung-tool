import httpx
import pytest

from autobookkeeping import dhl_receipts
from autobookkeeping.dhl_receipts import download_receipt_from_link, is_dhl_url, likely_invoice_links


@pytest.mark.parametrize("url", [
    "https://www.dhl.de/restweb/Invoice?id=1",
    "https://dhl.de/restweb/Invoice",
    "https://shop.example.dhl.com/invoice.pdf",
])
def test_dhl_hosts_are_accepted(url):
    assert is_dhl_url(url)


@pytest.mark.parametrize("url", [
    "http://www.dhl.de/restweb/Invoice",
    "https://dhl.de.example.org/restweb/Invoice",
    "https://example.org/dhl.de/restweb/Invoice",
    "https://notdhl.de/restweb/Invoice",
    "https://user@www.dhl.de/restweb/Invoice",
    "https://www.dhl.de:8443/restweb/Invoice",
    "https://www.dhl.de@example.org/restweb/Invoice",
    "ftp://www.dhl.de/restweb/Invoice",
    "not a url",
])
def test_foreign_or_unsafe_addresses_are_rejected(url):
    assert not is_dhl_url(url)


def test_foreign_links_are_not_offered_or_fetched(tmp_path):
    links = ["https://example.org/restweb/Invoice/dhl", "https://www.dhl.de/restweb/Invoice?x=1"]
    assert likely_invoice_links(links) == ["https://www.dhl.de/restweb/Invoice?x=1"]
    with pytest.raises(RuntimeError):
        download_receipt_from_link(links[0], tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_redirect_to_foreign_host_is_blocked(tmp_path, monkeypatch):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.org/forged.pdf"})

    original = httpx.Client
    monkeypatch.setattr(dhl_receipts.httpx, "Client",
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(RuntimeError):
        download_receipt_from_link("https://www.dhl.de/restweb/Invoice?x=1", tmp_path)
    assert requested == ["https://www.dhl.de/restweb/Invoice?x=1"]
    assert not list(tmp_path.glob("*.pdf"))
