import streamlit as st
import pandas as pd
import time
import re
import html
from playwright.sync_api import sync_playwright, Playwright
from bs4 import BeautifulSoup
import os # <-- ADDED OS IMPORT HERE

# --- CRITICAL FIX FOR STREAMLIT DEPLOYMENT ---
# This line tells the Playwright Python library the exact location where the
# browser executable was installed by the 'post_install.sh' script in the
# Streamlit deployment environment, resolving the "Executable doesn't exist" error.
# **LOCAL FIX: The line below is COMMENTED OUT to allow the app to run locally.**
# os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.getcwd() + '/browser_cache'
# --- END OF CRITICAL FIX ---

# Base URL for PDGA site
BASE_URL = "https://www.pdga.com"


# --- CORE SCRAPING FUNCTIONS ---

def get_detail_links(p: Playwright, search_url, column_name):
    """
    Stage 1: Uses Playwright to load the search page, execute JavaScript,
    and find links from the fully rendered table.
    """
    st.info(f"Step 1: Launching headless browser to fetch index page from {search_url}...")
    try:
        # --- SIMPLIFIED FOR STREAMLIT CLOUD AFTER 'playwright install' ---
        browser = p.chromium.launch(
            headless=True  # Keep headless mode enabled for server deployment
        )
        # ---------------------------------------------
        page = browser.new_page()

        # Go to the URL and wait for the network to be mostly idle
        page.goto(search_url, wait_until="domcontentloaded")

        # Wait specifically for the data table (Timeout reduced to 10s)
        page.wait_for_selector('table.views-table', timeout=10000)

        # Get the fully rendered HTML content
        page_content = page.content()
        browser.close()

    except Exception as e:
        st.error(f"Error fetching search URL with Playwright: {e}")
        # Added a path check to help with future debugging if needed
        st.error(f"Playwright Path Check: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}")
        return []

    soup = BeautifulSoup(page_content, 'html.parser')
    table = soup.find('table', class_='views-table')

    if not table:
        st.warning("No data table found on the fully rendered page. Check your URL filters.")
        return []

    # Find the header index for the target column
    headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]

    # Check for the correct column name based on the mode
    if column_name not in headers:
        st.error(f"Could not find column '{column_name}' in the table headers: {headers}")
        return []

    col_index = headers.index(column_name)

    detail_links = []

    # Iterate through table rows (excluding the header)
    for row in table.find('tbody').find_all('tr'):
        cells = row.find_all('td')
        if len(cells) > col_index:
            link_tag = cells[col_index].find('a', href=True)
            if link_tag:
                full_link = BASE_URL + link_tag['href']
                item_name = link_tag.get_text(strip=True)
                detail_links.append((item_name, full_link))

    st.success(f"Found {len(detail_links)} detail pages to scrape.")
    return detail_links


def scrape_tournament_detail(p: Playwright, event_name, url):
    """
    Tournament Scraper (MODIFIED: Removed Manual Search Query logic.)
    """
    try:
        # --- SIMPLIFIED FOR STREAMLIT CLOUD AFTER 'playwright install' ---
        browser = p.chromium.launch(
            headless=True
        )
        # ---------------------------------------------
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")

        # Wait for a key element (director link) - Timeout INCREASED to 30s
        page.wait_for_selector('a[href*="/general-contact?pdganum="]', timeout=30000)

        page_content = page.content()
        browser.close()
    except Exception as e:
        # Removed "Manual Search Query" from return dict
        return {"Name": event_name, "Tournament Director": "ERROR", "Email": f"Playwright/Request Failed: {e}",
                "URL": url}

    soup = BeautifulSoup(page_content, 'html.parser')

    tournament_director = "Not Found"
    email = "Not Found"
    email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'

    # --- 1. Scrape Tournament Director Name ---
    td_link = soup.find('a', href=re.compile(r'/general-contact\?pdganum='))
    if td_link:
        tournament_director = td_link.get_text(strip=True)

    # --- 2. PRIORITY 1: ROBUST MAILTO SEARCH ---
    mailto_tags = soup.find_all('a', href=re.compile(r'^mailto:'))
    if mailto_tags:
        for tag in mailto_tags:
            candidate_email = tag['href'].replace('mailto:', '').strip()
            if candidate_email and '@' in candidate_email:
                email = candidate_email
                break

    # --- 3. PRIORITY 2: AGGRESSIVE RAW CONTENT SEARCH ---
    if email == "Not Found":
        # Aggressive decoding of HTML entities
        decoded_page_content = page_content
        try:
            decoded_page_content = html.unescape(page_content)
        except Exception:
            pass

            # Search the ENTIRE DECODED content for an exact email string
        direct_email_match = re.search(email_pattern, decoded_page_content, re.IGNORECASE)
        if direct_email_match:
            email = direct_email_match.group(1).strip()

    # E. Final Cleanup
    if email != "Not Found":
        email = email.rstrip(';\'" ')

    # Removed Manual Search Query Generation logic

    # Final return dictionary simplified
    return {
        "Name": event_name,
        "Tournament Director": tournament_director,
        "Email": email,
        "URL": url,
    }


def clean_contact_name(raw_name_text):
    """Strips the optional '#PDGA_NUMBER' suffix from a contact name and 'Email:' prefix."""
    if not raw_name_text:
        return "Not Found"

    # NEW: Remove "Email:" prefix if present (fixes "Email:Bill Fratzke")
    if raw_name_text.lower().startswith("email:"):
        raw_name_text = raw_name_text[len("email:"):].strip()

    # This regex captures the name (group 1) and optionally ignores '#\d+' at the end.
    raw_name_text = raw_name_text.strip()
    name_match = re.match(r'(.+?)(?:\s*#\d+)?$', raw_name_text)
    if name_match:
        return name_match.group(1).strip()
    return raw_name_text


def scrape_course_detail(p: Playwright, course_name, url):
    """
    Course Scraper (MODIFIED: Cleaned up Contact Name and Phone formatting.
    Removed Manual Search Query logic.)
    """
    try:
        # --- SIMPLIFIED FOR STREAMLIT CLOUD AFTER 'playwright install' ---
        browser = p.chromium.launch(
            headless=True
        )
        # ---------------------------------------------
        page = browser.new_page()

        # Use a shorter, more reliable wait condition
        page.goto(url, wait_until="networkidle")

        # Small additional sleep to ensure any final JavaScript executes
        time.sleep(1)

        page_content = page.content()
        browser.close()
    except Exception as e:
        # Removed "Manual Search Query" from return dict
        return {"Course": course_name, "Contact Name": "ERROR", "Phone": "Request Failed",
                "Email": f"Playwright/Request Failed: {e}", "URL": url}

    soup = BeautifulSoup(page_content, 'html.parser')

    contact_name = "Not Found"
    phone = "Not Found"
    alt_phone = "Not Found"
    email = "Not Found"
    email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

    # --- 1. Targeted Search for Contact Name, Email, and Phone Number(s) (Drupal Classes) ---

    # Target 1.1: Primary Name Field (via general field class)
    contact_field_wrapper = soup.find('div', class_=re.compile(r'field--name-field-course-contact'))
    if contact_field_wrapper:
        contact_name_item = contact_field_wrapper.find('div', class_='field__item')
        if contact_name_item:
            raw_name_text = contact_name_item.get_text(strip=True)
            contact_name = clean_contact_name(raw_name_text)

    # Target 1.2: Primary Phone Number (via specific ID)
    phone_field_wrapper = soup.find('div', class_='views-field-field-course-contact-home-phone-revision-id')
    if phone_field_wrapper:
        phone_item = phone_field_wrapper.find('span', class_='field-content')
        if phone_item:
            raw_phone_text = phone_item.get_text(strip=True)
            phone_match = re.search(phone_pattern, raw_phone_text)
            if phone_match:
                phone = phone_match.group(0)

    # Target 1.3: Alternative Phone Number (via work phone ID)
    alt_phone_field_wrapper = soup.find('div', class_='views-field-field-course-contact-work-phone-revision-id')
    if alt_phone_field_wrapper:
        alt_phone_item = alt_phone_field_wrapper.find('span', class_='field-content')
        if alt_phone_item:
            raw_phone_text = alt_phone_item.get_text(strip=True)
            phone_match = re.search(phone_pattern, raw_phone_text)
            if phone_match:
                alt_phone = phone_match.group(0)

    # Target 1.4: Email/Contact Link (via email field ID)
    email_field_wrapper = soup.find('div', class_='views-field-field-course-contact-email-revision-id')
    provisional_contact_name = ""

    if email_field_wrapper:

        # FIX for Northside Park structure: grabs name from field text, e.g., 'Tom Jackson #4217'
        contact_field_text = email_field_wrapper.get_text(strip=True)
        if contact_field_text and contact_name in ["Not Found", ""]:
            contact_name = clean_contact_name(contact_field_text)

        # A. Check for direct MAILTO link first
        direct_email_match = email_field_wrapper.find('a', href=re.compile(r'^mailto:'))
        if direct_email_match:
            email = direct_email_match['href'].replace('mailto:', '').strip()
            provisional_contact_name = direct_email_match.get_text(strip=True)

        # B. Check for Contact Form link
        contact_form_link = email_field_wrapper.find('a', href=re.compile(r'^/course-contact\?course='))
        if email == "Not Found" and contact_form_link:
            email = "FORM: " + BASE_URL + contact_form_link['href']
            provisional_contact_name = contact_form_link.get_text(strip=True)

        # Use the anchor text as the Contact Name fallback if the main field was empty
        if provisional_contact_name and contact_name in ["Not Found", ""]:
            contact_name = clean_contact_name(provisional_contact_name)

    # --- 2. Fallback Search for Simple Contact Block ---

    contact_block_header = soup.find('h3', string=re.compile(r'Contact'))

    # If we still haven't found a decent contact name, look immediately after the 'Contact' header
    if contact_block_header and contact_name in ["Not Found", ""]:
        name_tag = contact_block_header.find_next_sibling(text=True)
        if name_tag:
            name_text = name_tag.strip()
            if name_text and len(name_text) > 3 and not name_text.lower().startswith('phone'):
                contact_name = clean_contact_name(name_text)

    # Now, check the general content container for email/phone
    if contact_block_header:
        parent_div = contact_block_header.find_parent('div')
        if parent_div:
            content_container = parent_div.find_next_sibling('div') or parent_div.find_next_sibling('p')

            if content_container:
                contact_block_content = content_container.get_text()

                # Re-check for phone
                alt_phone_match = re.search(r'(?:Alt\.\s*Phone|Phone|Contact):\s*(' + phone_pattern + r')',
                                            contact_block_content)
                if alt_phone_match:
                    if phone == "Not Found":
                        phone = alt_phone_match.group(1)
                    elif alt_phone == "Not Found":
                        alt_phone = alt_phone_match.group(1)

                # Re-check for email link
                if email == "Not Found" or email.startswith("FORM:"):
                    email_link_tag = content_container.find('a', href=re.compile(r'^mailto:'))
                    if email_link_tag:
                        email = email_link_tag['href'].replace('mailto:', '').strip()
                    else:
                        contact_form_link = content_container.find('a', href=re.compile(r'^/course-contact\?course='))
                        if contact_form_link and email == "Not Found":
                            email = "FORM: " + BASE_URL + contact_form_link['href']

    # --- 3. AGGRESSIVE PRIORITY: Full-page Raw Content Search ---
    if not ('@' in email):
        decoded_page_content = page_content
        try:
            decoded_page_content = html.unescape(page_content)
        except Exception:
            pass

        if email == "Not Found" or email.startswith("FORM:"):
            mailto_tags = soup.find_all('a', href=re.compile(r'^mailto:'))
            if mailto_tags:
                for tag in mailto_tags:
                    candidate_email = tag['href'].replace('mailto:', '').strip()
                    if candidate_email and '@' in candidate_email:
                        email = candidate_email
                        break

        if email == "Not Found" or email.startswith("FORM:"):
            direct_email_match = re.search(email_pattern, decoded_page_content, re.IGNORECASE)
            if direct_email_match:
                email = direct_email_match.group(1).strip()

    # E. Final Cleanup
    if email != "Not Found" and not email.startswith("FORM: "):
        email = email.rstrip(';\'" ')

    # --- 4. Combine Phone Results (MODIFIED: Removed 'Alt:' and 'Main:' prefixes) ---
    final_phone_output = phone
    if phone == "Not Found" and alt_phone != "Not Found":
        final_phone_output = alt_phone
    elif phone != "Not Found" and alt_phone != "Not Found":
        # Keep phones separated by comma if both exist, without prefixes
        final_phone_output = f"{phone}, {alt_phone}"

    # If the combined output is still 'Not Found', replace with an empty string for cleaner display
    if final_phone_output == "Not Found":
        final_phone_output = ""

    # Handle the case where the email/phone was found but name wasn't
    if (email != "Not Found" or final_phone_output != "") and contact_name in ["Not Found", ""]:
        contact_name = "Contact Info Found"

    # Removed Manual Search Query Generation logic

    # Final return dictionary simplified
    return {
        "Course": course_name,
        "Contact Name": contact_name,
        "Phone": final_phone_output,
        "Email": email,
        "URL": url,
    }


# --- STREAMLIT APP LAYOUT (MODIFIED: Updated result_columns) ---

st.set_page_config(layout="wide", page_title="PDGA Contact Scraper")
st.title("PDGA Event & Course Contact Scraper (Playwright) 📧")
st.markdown("""
<style>
.stAlert { border-radius: 0.5rem; }
.stButton>button { border-radius: 0.5rem; background-color: #007bff; color: white; transition: all 0.2s; }
.stButton>button:hover { background-color: #0056b3; transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
</style>
""", unsafe_allow_html=True)

# Define the scraping mode
mode = st.radio(
    "Select Scraper Mode:",
    ("Tournament Scraper", "Course Scraper")
)

# Configuration based on mode
if mode == "Tournament Scraper":
    placeholder_url = "https://www.pdga.com/tour/search?date_filter%5Bmin%5D%5Bdate%5D=2025-10-09&date_filter%5Bmax%5D%5Bdate%5D=2026-10-09&State%5B%5D=CA&Tier%5B%5D=B"
    column_to_parse = "Name"
    scrape_detail_function = scrape_tournament_detail
    # UPDATED: Removed "Manual Search Query"
    result_columns = ["Name", "Tournament Director", "Email", "URL"]

else:  # Course Scraper
    placeholder_url = "https://www.pdga.com/course-directory/advanced?title=&field_course_location_country=US&field_course_location_locality=&field_course_location_administrative_area=CA&field_course_type_value=All&rating_value=All&field_course_holes_value=1-9&field_course_total_length_value=All&field_course_target_type_value=Mach2&field_course_tee_type_value=All&field_location_type_value=All&field_course_camping_value=yes&field_course_facilities_value=All&field_course_fees_value=All&field_course_handicap_value=All&field_course_private_value=All&field_course_signage_value=All&field_cart_friendly_value=All"
    column_to_parse = "Course"
    scrape_detail_function = scrape_course_detail
    # UPDATED: Removed "Manual Search Query"
    result_columns = ["Course", "Contact Name", "Phone", "Email", "URL"]

# User Input
input_url = st.text_input(
    f"Paste the {mode} Search URL from PDGA:",
    placeholder=placeholder_url
)

# Execute Scrape
if st.button(f"Start {mode} Scrape 🎯 (Using Playwright)"):
    if not input_url:
        st.warning("Please enter a valid PDGA search URL to start.")
        st.stop()

    if not input_url.startswith(BASE_URL):
        st.error(f"The URL must start with {BASE_URL}. Please use a valid PDGA link.")
        st.stop()

    st.header("Scraping Results")

    # Wrap the entire scraping operation in the Playwright context
    with sync_playwright() as p:

        # 1. Get the list of detail links
        detail_links = get_detail_links(p, input_url, column_to_parse)

        if detail_links:
            # Create a progress bar for the second stage
            progress_bar = st.progress(0)
            all_results = []
            total_links = len(detail_links)

            # 2. Iterate and scrape each detail page
            st.subheader("Step 2: Scraping Detail Pages...")

            for i, (item_name, link) in enumerate(detail_links):
                # Update progress bar
                progress = (i + 1) / total_links
                progress_bar.progress(progress, text=f"Processing {item_name} ({i + 1}/{total_links})")

                # Scrape the detail page using the Playwright instance 'p'
                result = scrape_detail_function(p, item_name, link)
                all_results.append(result)

                # Performance optimization: reduced wait time
                time.sleep(0.1)

            progress_bar.progress(1.0, text="Scraping Complete!")
            st.balloons()

            # 3. Display and export results
            final_df = pd.DataFrame(all_results)
            # Select only the columns defined in result_columns for display/download
            final_df = final_df[result_columns]

            st.subheader("Extracted Contact Information (Browser-Rendered)")
            st.dataframe(final_df, use_container_width=True)

            # Download button
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Data as CSV",
                data=csv,
                file_name=f"{mode.lower().replace(' ', '_')}_contacts_playwright_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.error("No links were found to process. Please double-check your search URL.")
