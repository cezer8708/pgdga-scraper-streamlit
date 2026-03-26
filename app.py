import html
import re
import time
import base64
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

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


def fetch_page_content(
    url: str,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """Fetch a server-rendered page and return the HTML."""
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def extract_first_email(soup: BeautifulSoup, page_content: str) -> str:
    """Return the first mailto email or a raw email match from the page."""
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


def get_detail_links(search_url: str, column_name: str, is_tournament_mode: bool) -> list[tuple]:
    """Walk the paginated result set and collect all detail page links."""
    status_box = st.empty()
    status_lines = [f"Loading index pages from `{search_url}`"]
    render_status_log(status_box, "Index Progress", status_lines)

    detail_links: list[tuple] = []
    page_count = 0
    current_url = search_url
    final_target_column = column_name

    try:
        while current_url:
            page_count += 1
            status_lines.append(f"Processing results page {page_count}")
            render_status_log(status_box, "Index Progress", status_lines)

            page_content = fetch_page_content(current_url, timeout=15)
            new_links, next_url, resolved_column = scrape_page_links(page_content, column_name, is_tournament_mode)
            final_target_column = resolved_column
            detail_links.extend(new_links)

            if new_links:
                status_lines.append(f"Found {len(new_links)} events on page {page_count}")
                render_status_log(status_box, "Index Progress", status_lines)

            current_url = next_url if next_url and next_url != current_url else None

        status_lines.append(f"Finished pagination after {page_count} page(s)")
    except Exception as exc:
        st.error(f"An error occurred during pagination on page {page_count}. Stopping. Error: {exc}")

    status_lines.append(
        f"Collected {len(detail_links)} detail page(s) using column `{final_target_column}`"
    )
    render_status_log(status_box, "Index Progress", status_lines)
    return detail_links


def scrape_tournament_detail(
    event_name: str,
    url: str,
    dates: str,
    tier_label: str,
) -> dict[str, str]:
    """Scrape tournament contact details from the event page."""
    try:
        page_content = fetch_page_content(url)
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
    detail_links = get_detail_links(input_url, column_to_parse, True)
    if not detail_links:
        st.error("No links were found to process. Please double-check your search URL.")
        return

    progress_bar = st.progress(0)
    all_results: list[dict[str, str]] = []
    total_links = len(detail_links)
    detail_status = st.empty()
    render_status_log(detail_status, "Detail Progress", ["Starting detail page scrape"])

    for index, item_data in enumerate(detail_links, start=1):
        progress = index / total_links
        item_name, link, dates = item_data
        progress_bar.progress(progress, text=f"Processing {item_name} ({index}/{total_links}) - {dates}")
        render_status_log(
            detail_status,
            "Detail Progress",
            [
                f"Processing `{item_name}`",
                f"Item {index} of {total_links}",
                f"Dates: {dates}",
            ],
        )
        result = scrape_tournament_detail(item_name, link, dates, tier_label)

        all_results.append(result)
        time.sleep(0.1)

    progress_bar.progress(1.0, text="Scraping Complete!")
    render_status_log(
        detail_status,
        "Detail Progress",
        [
            "Scrape complete",
            f"Processed {total_links} event(s)",
        ],
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
