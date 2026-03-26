import html
import re
import time
import random
import base64
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_DIR = Path(__file__).resolve().parent
LOGO_CANDIDATES = [
    Path("/Users/cesarzermeno/Desktop/Back Ups/Custom_Stamp_Tool/dga-logo.png"),
    APP_DIR / "dga_logo.png",
    APP_DIR / "dga-logo.png",
    APP_DIR / "DGA_logo.png",
    APP_DIR / "DGA Logo.png",
    APP_DIR / "assets" / "dga_logo.png",
    APP_DIR / "assets" / "dga-logo.png",
]

st.set_page_config(
    layout="wide",
    page_title="PDGA Event Contact Scraper",
    initial_sidebar_state="collapsed",
)

BASE_URL = "https://www.pdga.com"
REQUEST_TIMEOUT = 30
REQUEST_RETRY_COUNT = 4
REQUEST_MIN_DELAY = 0.45
REQUEST_MAX_DELAY = 1.1
REQUEST_BATCH_SIZE = 25
REQUEST_BATCH_PAUSE_SECONDS = 4
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )
}
EMAIL_PATTERN = r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
NOT_FOUND = "Not Found"


def decode_html(text: str) -> str:
    try:
        return html.unescape(text)
    except Exception:
        return text


def sanitize_email(value: str) -> str:
    if value != NOT_FOUND and not value.startswith("FORM: "):
        return value.rstrip(";\'\" ")
    return value


def decode_cloudflare_email(encoded: str) -> str:
    """Decode Cloudflare's email protection hex payload."""
    if not encoded:
        return NOT_FOUND

    try:
        key = int(encoded[:2], 16)
        decoded_chars = [
            chr(int(encoded[index:index + 2], 16) ^ key)
            for index in range(2, len(encoded), 2)
        ]
        return sanitize_email("".join(decoded_chars))
    except Exception:
        return NOT_FOUND


def get_logo_path() -> Optional[Path]:
    for candidate in LOGO_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def get_logo_data_uri() -> Optional[str]:
    logo_path = get_logo_path()
    if not logo_path:
        return None

    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_status_log(container, title: str, lines: list[str]) -> None:
    body = "\n".join(f"- {line}" for line in lines)
    container.markdown(f"**{title}**\n\n{body}")


def render_progress_panel(
    container,
    title: str,
    stats: list[tuple[str, str]],
    status: str,
    note: Optional[str] = None,
) -> None:
    stats_markup = "".join(
        f"""
        <div class="run-stat-card">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
        """
        for label, value in stats
    )
    note_markup = f'<p class="run-panel-note">{note}</p>' if note else ""
    container.markdown(
        f"""
        <div class="run-panel">
          <div class="run-panel-header">{title}</div>
          <div class="run-stats-grid">{stats_markup}</div>
          <div class="run-panel-status">{status}</div>
          {note_markup}
        </div>
        """,
        unsafe_allow_html=True,
    )


def create_http_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=REQUEST_RETRY_COUNT,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(REQUEST_HEADERS)
    return session


def sleep_with_jitter(min_seconds: float = REQUEST_MIN_DELAY, max_seconds: float = REQUEST_MAX_DELAY) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def fetch_page_content(
    session: requests.Session,
    url: str,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """Fetch a server-rendered page and return the HTML."""
    last_error: Optional[Exception] = None

    for attempt in range(1, REQUEST_RETRY_COUNT + 2):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 429 and attempt <= REQUEST_RETRY_COUNT:
                retry_after = response.headers.get("Retry-After")
                delay_seconds = float(retry_after) if retry_after and retry_after.isdigit() else (attempt * 3)
                time.sleep(delay_seconds + random.uniform(0.25, 0.75))
                continue

            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt > REQUEST_RETRY_COUNT:
                break
            time.sleep((attempt * 2) + random.uniform(0.25, 0.75))

    raise last_error if last_error else RuntimeError(f"Request failed for {url}")


def extract_first_email(soup: BeautifulSoup, page_content: str) -> str:
    """Return the first mailto email or a raw email match from the page."""
    protected_email = soup.find("span", class_="__cf_email__", attrs={"data-cfemail": True})
    if protected_email:
        decoded_email = decode_cloudflare_email(protected_email["data-cfemail"])
        if decoded_email != NOT_FOUND:
            return decoded_email

    for tag in soup.find_all("a", href=re.compile(r"^mailto:")):
        candidate = tag["href"].replace("mailto:", "").strip()
        if "@" in candidate:
            return sanitize_email(candidate)

    match = re.search(EMAIL_PATTERN, decode_html(page_content), re.IGNORECASE)
    if match:
        return sanitize_email(match.group(1).strip())

    return NOT_FOUND


def parse_table_headers(table: BeautifulSoup) -> list[str]:
    header_row = table.find("thead")
    if not header_row:
        return []
    return [header.get_text(strip=True) for header in header_row.find_all("th")]


def resolve_target_column(headers: list[str], requested_column: str) -> Optional[str]:
    if requested_column in headers:
        return requested_column

    fallback_column = "Name" if requested_column == "Course" else "Course"
    if fallback_column in headers:
        return fallback_column

    return None


def scrape_page_links(page_content: str, column_name: str, is_tournament_mode: bool) -> tuple[list[tuple], Optional[str], str]:
    """Scrape the listing rows from a PDGA search results page."""
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("table", class_="views-table")
    if not table:
        return [], None, column_name

    headers = parse_table_headers(table)
    resolved_column = resolve_target_column(headers, column_name)
    if not resolved_column:
        st.error(f"Could not find a valid target column in the table headers: {headers}")
        return [], None, column_name

    name_col_index = headers.index(resolved_column)
    dates_col_index = headers.index("Dates") if is_tournament_mode and "Dates" in headers else -1

    if is_tournament_mode and dates_col_index == -1:
        st.warning("Could not find 'Dates' column for tournament scraping.")

    all_links: list[tuple] = []
    tbody = table.find("tbody")
    if tbody:
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) <= name_col_index:
                continue

            link_tag = cells[name_col_index].find("a", href=True)
            if not link_tag:
                continue

            full_link = BASE_URL + link_tag["href"]
            item_name = link_tag.get_text(strip=True)

            if is_tournament_mode:
                dates = cells[dates_col_index].get_text(strip=True) if len(cells) > dates_col_index >= 0 else ""
                all_links.append((item_name, full_link, dates))
            else:
                all_links.append((item_name, full_link))

    next_link = soup.find("a", title="Go to next page")
    next_url = BASE_URL + next_link["href"] if next_link and next_link.get("href") else None
    return all_links, next_url, resolved_column


def get_detail_links(session: requests.Session, search_url: str, column_name: str, is_tournament_mode: bool) -> list[tuple]:
    """Walk the paginated result set and collect all detail page links."""
    status_box = st.empty()
    detail_links: list[tuple] = []
    page_count = 0
    current_url = search_url
    final_target_column = column_name
    last_page_count = 0
    render_progress_panel(
        status_box,
        "Search Progress",
        [
            ("Pages scanned", "0"),
            ("Events found", "0"),
            ("Target column", column_name),
        ],
        "Opening PDGA search results",
        "Preparing event links for contact scraping.",
    )

    try:
        while current_url:
            page_count += 1
            render_progress_panel(
                status_box,
                "Search Progress",
                [
                    ("Pages scanned", str(page_count - 1)),
                    ("Events found", str(len(detail_links))),
                    ("Target column", final_target_column),
                ],
                f"Scanning results page {page_count}",
                "Collecting event detail links from the PDGA search results.",
            )

            page_content = fetch_page_content(session, current_url, timeout=15)
            new_links, next_url, resolved_column = scrape_page_links(page_content, column_name, is_tournament_mode)
            final_target_column = resolved_column
            detail_links.extend(new_links)
            last_page_count = len(new_links)
            render_progress_panel(
                status_box,
                "Search Progress",
                [
                    ("Pages scanned", str(page_count)),
                    ("Events found", str(len(detail_links))),
                    ("Target column", final_target_column),
                ],
                f"Page {page_count} captured",
                f"Added {last_page_count} event link(s) from the current page.",
            )

            sleep_with_jitter(0.6, 1.4)
            current_url = next_url if next_url and next_url != current_url else None

        render_progress_panel(
            status_box,
            "Search Progress",
            [
                ("Pages scanned", str(page_count)),
                ("Events found", str(len(detail_links))),
                ("Target column", final_target_column),
            ],
            "Search pages loaded",
            f"Finished scanning {page_count} result page(s).",
        )
    except Exception as exc:
        st.error(f"An error occurred during pagination on page {page_count}. Stopping. Error: {exc}")

    render_progress_panel(
        status_box,
        "Search Progress",
        [
            ("Pages scanned", str(page_count)),
            ("Events found", str(len(detail_links))),
            ("Target column", final_target_column),
        ],
        "Event queue ready",
        f"{len(detail_links)} detail page(s) queued for scraping.",
    )
    return detail_links


def scrape_tournament_detail(
    session: requests.Session,
    event_name: str,
    url: str,
    dates: str,
    tier_label: str,
) -> dict[str, str]:
    """Scrape tournament contact details from the event page."""
    try:
        page_content = fetch_page_content(session, url)
    except Exception as exc:
        return {
            "Name": event_name,
            "Dates": dates,
            "Tier": tier_label,
            "Tournament Director": "ERROR",
            "Email": f"Request Failed: {exc}",
            "URL": url,
        }

    soup = BeautifulSoup(page_content, "html.parser")
    td_link = soup.find("a", href=re.compile(r"/general-contact\?pdganum="))
    tournament_director = td_link.get_text(strip=True) if td_link else NOT_FOUND
    email = extract_first_email(soup, page_content)

    return {
        "Name": event_name,
        "Dates": dates,
        "Tier": tier_label,
        "Tournament Director": tournament_director,
        "Email": email,
        "URL": url,
    }


def render_header() -> None:
    logo_data_uri = get_logo_data_uri()
    logo_markup = (
        f'<div class="brand-logo-shell"><img src="{logo_data_uri}" alt="DGA logo" class="brand-logo-img" /></div>'
        if logo_data_uri
        else ""
    )

    st.markdown(
        f"""
<section class="brand-hero">
  {logo_markup}
  <div class="brand-text">
    <h1>PDGA Event Contact Scraper</h1>
    <p>Designed by CZ</p>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def run_scrape(
    input_url: str,
    column_to_parse: str,
    result_columns: list[str],
    tier_label: str,
) -> None:
    st.header("Scraping Results")
    session = create_http_session()
    detail_links = get_detail_links(session, input_url, column_to_parse, True)
    if not detail_links:
        st.error("No links were found to process. Please double-check your search URL.")
        return

    progress_bar = st.progress(0)
    all_results: list[dict[str, str]] = []
    total_links = len(detail_links)
    detail_status = st.empty()
    render_progress_panel(
        detail_status,
        "Scrape Progress",
        [
            ("Queued", str(total_links)),
            ("Processed", "0"),
            ("Errors", "0"),
        ],
        "Starting contact lookup",
        "Opening event pages and pulling tournament director details.",
    )

    for index, item_data in enumerate(detail_links, start=1):
        progress = index / total_links
        item_name, link, dates = item_data
        progress_bar.progress(progress, text=f"Scraping event contacts {index}/{total_links}")
        error_count = sum(1 for row in all_results if row.get("Tournament Director") == "ERROR")
        render_progress_panel(
            detail_status,
            "Scrape Progress",
            [
                ("Queued", str(total_links)),
                ("Processed", str(index - 1)),
                ("Errors", str(error_count)),
            ],
            f"Currently checking: {item_name}",
            f"{dates}" if dates else None,
        )
        result = scrape_tournament_detail(session, item_name, link, dates, tier_label)

        all_results.append(result)
        if index % REQUEST_BATCH_SIZE == 0 and index < total_links:
            error_count = sum(1 for row in all_results if row.get("Tournament Director") == "ERROR")
            render_progress_panel(
                detail_status,
                "Scrape Progress",
                [
                    ("Queued", str(total_links)),
                    ("Processed", str(index)),
                    ("Errors", str(error_count)),
                ],
                "Cooling down to avoid PDGA rate limits",
                "Taking a short pause before opening the next batch of event pages.",
            )
            time.sleep(REQUEST_BATCH_PAUSE_SECONDS)
        else:
            sleep_with_jitter()

    final_error_count = sum(1 for row in all_results if row.get("Tournament Director") == "ERROR")
    progress_bar.progress(1.0, text="Scrape complete")
    render_progress_panel(
        detail_status,
        "Scrape Progress",
        [
            ("Queued", str(total_links)),
            ("Processed", str(total_links)),
            ("Errors", str(final_error_count)),
        ],
        "Contact scrape complete",
        "Review the table below or export the CSV.",
    )

    final_df = pd.DataFrame(all_results)[result_columns]
    st.subheader("Extracted Contact Information")
    st.dataframe(final_df, width="stretch")

    csv = final_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Data as CSV",
        data=csv,
        file_name=f"tournament_scraper_contacts_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


def main() -> None:
    render_header()
    st.markdown(
        """
<style>
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 1.5rem; max-width: 1400px; }
.brand-hero {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-bottom: 2rem;
    padding: 1.25rem 1.5rem;
    border: 1px solid rgba(66, 135, 245, 0.18);
    border-radius: 24px;
    background: linear-gradient(180deg, rgba(22,24,31,0.98), rgba(15,16,22,0.98));
}
.brand-logo-shell {
    flex: 0 0 auto;
    background: linear-gradient(135deg, rgba(255,255,255,0.97), rgba(239,243,249,0.94));
    border-radius: 18px;
    padding: 0.9rem 1rem;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
}
.brand-logo-img {
    display: block;
    width: 280px;
    height: auto;
}
.brand-text h1 {
    margin: 0;
    font-size: 2.2rem;
    line-height: 1.1;
}
.brand-text p {
    margin: 0.45rem 0 0;
    color: rgba(250, 250, 250, 0.72);
    font-size: 0.98rem;
}
.run-panel {
    margin: 0.6rem 0 1rem;
    padding: 1rem 1.05rem;
    border: 1px solid rgba(66, 135, 245, 0.14);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(22,24,31,0.96), rgba(16,18,24,0.96));
}
.run-panel-header {
    font-size: 0.84rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(250, 250, 250, 0.62);
    margin-bottom: 0.85rem;
}
.run-stats-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
    margin-bottom: 0.85rem;
}
.run-stat-card {
    padding: 0.7rem 0.8rem;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.05);
}
.run-stat-card span {
    display: block;
    font-size: 0.76rem;
    color: rgba(250, 250, 250, 0.58);
    margin-bottom: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.run-stat-card strong {
    display: block;
    font-size: 1.1rem;
    line-height: 1.1;
    color: #f9fafb;
}
.run-panel-status {
    font-size: 0.98rem;
    font-weight: 600;
    color: #f9fafb;
}
.run-panel-note {
    margin: 0.35rem 0 0;
    font-size: 0.88rem;
    color: rgba(250, 250, 250, 0.66);
}
.stSelectbox label, .stTextInput label {
    font-weight: 600;
}
.stButton>button { border-radius: 0.5rem; transition: all 0.2s; }
.stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
@media (max-width: 900px) {
    .brand-hero {
        flex-direction: column;
        align-items: flex-start;
    }
    .brand-logo-img {
        width: 220px;
    }
    .run-stats-grid {
        grid-template-columns: 1fr;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )

    placeholder_url = (
        "https://www.pdga.com/tour/search?"
        "date_filter%5Bmin%5D%5Bdate%5D=2025-10-09&"
        "date_filter%5Bmax%5D%5Bdate%5D=2026-10-09&"
        "State%5B%5D=CA&Tier%5B%5D=B"
    )
    column_to_parse = "Name"
    result_columns = ["Name", "Dates", "Tier", "Tournament Director", "Email", "URL"]
    tier_label = st.selectbox(
        "Select Tier Label for CSV Column:",
        options=["A-Tier", "B-Tier", "C-Tier", "Major", "NT", "Other"],
        help="This value will populate the 'Tier' column for all scraped entries.",
    )

    input_url = st.text_input(
        "Paste the Tournament Scraper Search URL from PDGA:",
        placeholder=placeholder_url,
    )

    if st.button("Start Tournament Scrape 🎯"):
        if not input_url:
            st.warning("Please enter a valid PDGA search URL to start.")
            st.stop()

        if not input_url.startswith(BASE_URL):
            st.error(f"The URL must start with {BASE_URL}. Please use a valid PDGA link.")
            st.stop()

        run_scrape(
            input_url=input_url,
            column_to_parse=column_to_parse,
            result_columns=result_columns,
            tier_label=tier_label,
        )


if __name__ == "__main__":
    main()
