from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

# Mail content is untrusted: anyone who knows a tracking number can send a mail
# containing it. Receipts are fetched from DHL's own hosts only.
DHL_HOSTS = ("dhl.de", "dhl.com")


def is_dhl_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return False
    return any(host == allowed or host.endswith("." + allowed) for allowed in DHL_HOSTS)


def _require_dhl_host(request: httpx.Request) -> None:
    # Runs for every request, including redirects, form targets and page links.
    if not is_dhl_url(str(request.url)):
        raise RuntimeError("DHL-Beleg wird nur von DHL-Adressen geladen; fremde Adresse abgelehnt")


def likely_invoice_links(links: list[str]) -> list[str]:
    keywords = ("rechnung", "invoice", "beleg", "quittung", "download", "dhl")
    scored = []
    for link in links:
        if not is_dhl_url(link):
            continue
        lower = link.lower()
        score = sum(1 for keyword in keywords if keyword in lower)
        if score:
            scored.append((score, link))
    return [link for _, link in sorted(scored, reverse=True)]


def download_receipt_from_link(url: str, output_dir: Path) -> Path:
    if not is_dhl_url(url):
        raise RuntimeError("DHL-Beleg wird nur von DHL-Adressen geladen; fremde Adresse abgelehnt")
    output_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60,
                      event_hooks={"request": [_require_dhl_host]}) as client:
        first = client.get(url)
        first.raise_for_status()
        if _is_pdf(first):
            return _save_pdf(first.content, output_dir, first)

        soup = BeautifulSoup(first.text, "html.parser")
        form_pdf = _download_form_pdf(client, str(first.url), soup)
        if form_pdf:
            return _save_pdf(form_pdf[0], output_dir, form_pdf[1])

        candidates = _candidate_links(str(first.url), soup)

        for candidate in candidates:
            response = client.get(candidate)
            response.raise_for_status()
            if _is_pdf(response):
                return _save_pdf(response.content, output_dir, response)
            candidate_soup = BeautifulSoup(response.text, "html.parser")
            form_pdf = _download_form_pdf(client, str(response.url), candidate_soup)
            if form_pdf:
                return _save_pdf(form_pdf[0], output_dir, form_pdf[1])

    raise RuntimeError(
        "Kein PDF gefunden. Falls DHL hier JavaScript oder Bot-Schutz nutzt, brauchen wir "
        "als nächste Stufe einen Playwright-Browser-Schritt."
    )


def _is_pdf(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "pdf" in content_type or response.content.startswith(b"%PDF")


def _download_form_pdf(
    client: httpx.Client,
    page_url: str,
    soup: BeautifulSoup,
) -> tuple[bytes, httpx.Response] | None:
    for form in soup.find_all("form"):
        form_text = " ".join(form.get_text(" ").split()).lower()
        if "rechnung" not in form_text and not form.find("input", {"name": "download"}):
            continue
        action = form.get("action") or page_url
        method = (form.get("method") or "get").lower()
        target = urljoin(page_url, action)
        data = {}
        for input_node in form.find_all("input"):
            name = input_node.get("name")
            if not name:
                continue
            data[name] = input_node.get("value", "")
        if method == "post":
            response = client.post(target, data=data)
        else:
            response = client.get(target, params=data)
        response.raise_for_status()
        if _is_pdf(response):
            return response.content, response
    return None


def _candidate_links(page_url: str, soup: BeautifulSoup) -> list[str]:
    candidates = []
    target = soup.find("a", {"id": "targetLink"})
    if target and target.get("href"):
        candidates.append(urljoin(page_url, target["href"]))

    for anchor in soup.find_all("a"):
        text = " ".join(anchor.get_text(" ").split()).lower()
        href = anchor.get("href")
        if not href:
            continue
        lower_href = href.lower()
        if (
            "rechnung" in text
            or "download" in text
            or ".pdf" in lower_href
            or "restweb/invoice" in lower_href
        ):
            candidate = urljoin(page_url, href)
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _save_pdf(content: bytes, output_dir: Path, response: httpx.Response | None = None) -> Path:
    filename = _filename_from_response(response)
    if not filename:
        filename = f"dhl-rechnung-{len(list(output_dir.glob('dhl-rechnung-*.pdf'))) + 1:03d}.pdf"
    path = output_dir / filename
    path.write_bytes(content)
    return path


def _filename_from_response(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    disposition = response.headers.get("content-disposition", "")
    marker = "filename="
    if marker not in disposition:
        return None
    filename = disposition.split(marker, 1)[1].strip().strip('"')
    if not filename.lower().endswith(".pdf"):
        return None
    return Path(filename).name
