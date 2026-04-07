import os
import re
import httpx
import hashlib
import tempfile
import pdfplumber
from anthropic import Anthropic

RBI_URL = "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def fetch_latest_circulars() -> list[dict]:
    """Scrape RBI circular listing page and return list of circulars."""
    from bs4 import BeautifulSoup

    resp = httpx.get(RBI_URL, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    circulars = []

    # RBI uses a table with class 'tablebg' for circulars
    table = soup.find("table", class_="tablebg")
    if not table:
        # fallback: find any table with circular links
        table = soup.find("table")

    if not table:
        return circulars

    for row in table.find_all("tr")[1:]:  # skip header row
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        link_tag = cols[0].find("a") or cols[1].find("a")
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")

        if not href or not title:
            continue

        # Build absolute URL — preserve /Scripts/ base path for relative hrefs
        if href.startswith("http"):
            url = href
        else:
            from urllib.parse import urljoin
            url = urljoin(RBI_URL, href)

        # Stable ID from URL
        circular_id = hashlib.md5(url.encode()).hexdigest()

        # Try to get date from adjacent column
        date_text = cols[-1].get_text(strip=True) if cols else ""

        circulars.append({
            "id": circular_id,
            "title": title,
            "url": url,
            "date": date_text,
        })

    return circulars


def extract_pdf_text(url: str) -> str:
    """Fetch URL, find PDF link if HTML, extract text from PDF."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    try:
        resp = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # If HTML page, look for a PDF link inside it
        if "html" in content_type or resp.content[:4] != b"%PDF":
            soup = BeautifulSoup(resp.text, "html.parser")
            pdf_link = None
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.lower().endswith(".pdf") or "pdf" in href.lower():
                    pdf_link = urljoin(url, href)
                    break

            if pdf_link:
                print(f"[scraper] Found PDF link: {pdf_link}")
                return _download_and_extract_pdf(pdf_link)
            else:
                # No PDF found — extract text directly from HTML
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                return text[:8000]

        return _download_and_extract_pdf(url, content=resp.content)

    except Exception as e:
        print(f"[scraper] Extraction failed for {url}: {e}")
        return ""


def _download_and_extract_pdf(url: str, content: bytes = None) -> str:
    """Extract text from a PDF URL or bytes."""
    try:
        if content is None:
            resp = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        text = ""
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if len(text.strip()) < 100:
            text = _ocr_pdf(tmp_path)

        return text.strip()

    except Exception as e:
        print(f"[scraper] PDF extraction failed for {url}: {e}")
        return ""


def _ocr_pdf(pdf_path: str) -> str:
    """OCR fallback using pytesseract."""
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(pdf_path)
        return "\n".join(pytesseract.image_to_string(img) for img in images)
    except Exception as e:
        print(f"[scraper] OCR fallback failed: {e}")
        return ""


def summarize_circular(title: str, text: str) -> str:
    """Call Claude to summarize the circular text."""
    if not text:
        return "Full text could not be extracted. Please read the circular directly."

    prompt = f"""You are a regulatory compliance assistant for Indian banks. Summarize the RBI circular below in a strict professional format. No emojis, no markdown, no bold text, no headers. Plain text only.

Use exactly this structure:

Circular Title & No.: [Full title and circular number], dated [date]

Applicable From: [Effective date]

Applicable To: [Who this applies to]

Summary:
- [Key point 1]
- [Key point 2]
- [Key point 3]
- [Key point 4]
- [Key point 5 if needed]

Keep each bullet point to one clear, formal sentence. Focus on what has changed, restrictions introduced, actions required, and deadlines.

Circular title: {title}

Circular text:
{text[:8000]}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def scrape_and_summarize() -> list[dict]:
    """
    Main entry point. Returns list of new circulars with summaries.
    Caller is responsible for checking Firebase and saving.
    """
    from firebase_client import is_circular_seen, mark_circular_seen

    print("[scraper] Fetching RBI circular list...")
    circulars = fetch_latest_circulars()
    print(f"[scraper] Found {len(circulars)} circulars on page.")

    new_circulars = []
    for c in circulars:
        if is_circular_seen(c["id"]):
            continue

        print(f"[scraper] New circular: {c['title']}")

        # Download and summarize
        text = extract_pdf_text(c["url"])
        summary = summarize_circular(c["title"], text)
        c["summary"] = summary

        # Persist to Firebase
        mark_circular_seen(c["id"], {
            "title": c["title"],
            "url": c["url"],
            "date": c["date"],
            "summary": summary,
            "notified_at": firestore_now(),
        })

        new_circulars.append(c)

    print(f"[scraper] {len(new_circulars)} new circulars found.")
    return new_circulars


def firestore_now():
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
    return SERVER_TIMESTAMP
