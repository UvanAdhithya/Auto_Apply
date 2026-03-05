import os
import json
import csv
import datetime
import argparse
import yaml
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = Path(LOG_DIR) / "internshala_applied.csv"

SELECTORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selectors.yaml")
with open(SELECTORS_FILE, "r") as f:
    SELECTORS = yaml.safe_load(f)["selectors"]

INTERNSHALA_URL = "https://internshala.com"
INTERNSHIPS_SEARCH_URL = "https://internshala.com/internships/matching-preferences/"

# Keywords to search for internships
KEYWORDS = [
    "AI",
    "ML",
    "SWE",
    "Web Dev",
    "Frontend",
    "Backend"
]

# --- Helper Functions ---

def load_credentials():
    """Loads Internshala credentials from environment variables."""
    username = os.environ.get("INTERNSHALA_USERNAME")
    password = os.environ.get("INTERNSHALA_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Internshala credentials not found. Please set "
            "INTERNSHALA_USERNAME and INTERNSHALA_PASSWORD environment variables."
        )
    return username, password


def save_log(record):
    """Appends a new application record to a CSV log file in real-time."""
    if not record:
        return

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = LOG_FILE.exists()
    
    # We define the column headers based on our record dictionary keys
    fieldnames = ["company", "role", "date_applied", "listing_url", "status"]

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writerow(record)


def robust_wait_and_click(page, selector_key, timeout=10000, force=False):
    """Waits for and clicks a selector, triggering the self-healing AI if it fails."""
    try:
        element = page.locator(SELECTORS[selector_key]).first
        element.wait_for(state="visible", timeout=timeout)
        element.click(timeout=timeout, force=force)
        return True
    except PlaywrightTimeoutError:
        print(f"Timeout waiting for '{selector_key}'. Triggering self-healing AI agent...")
        try:
            import agent
            # Take a screenshot before healing just in case
            page.screenshot(path=f"healing_trigger_{selector_key}.png")
            
            # Send HTML to the CrewAI agents
            agent.heal_selectors(page.content())
            
            # Reload fresh SELECTORS from the YAML file that the agent just fixed
            with open(SELECTORS_FILE, "r") as f:
                SELECTORS.update(yaml.safe_load(f)["selectors"])
                
            new_selector = SELECTORS[selector_key]
            print(f"Retrying '{selector_key}' with AI-fixed selector: {new_selector}")
            element = page.locator(new_selector).first
            element.wait_for(state="visible", timeout=timeout)
            element.click(timeout=timeout, force=force)
            return True
        except Exception as e:
            print(f"Self-healing failed for '{selector_key}': {e}")
            return False


def get_system_time_iso():
    """Returns the current system time in ISO format."""
    return datetime.datetime.now().isoformat()

# --- Core Automation Functions ---

def login_to_internshala(page, username, password):
    """Logs into Internshala.com."""
    print(f"Navigating to {INTERNSHALA_URL} for login...")
    try:
        page.goto(INTERNSHALA_URL)
        
        # Check if already logged in (persistent context)
        try:
            # Check if login button is present. If not, we are likely already logged in.
            login_btn = page.wait_for_selector(SELECTORS["login_btn_check"], timeout=5000)
            print("Not logged in. Proceeding with credentials...")
        except PlaywrightTimeoutError:
            print("Login button not found. Assuming already logged in (session restored).")
            return True

        # Click the login button
        login_btn.click()
        page.wait_for_selector(SELECTORS["login_modal_visible"], state="visible", timeout=10000)
        print("Clicked login button. Filling credentials...")
    
        # Wait for login form fields and fill them
        username_field_selector = SELECTORS["username_field"]
        password_field_selector = SELECTORS["password_field"]
        submit_button_selector = SELECTORS["login_submit"]

        page.locator(username_field_selector).press_sequentially(username, delay=50)
        page.locator(password_field_selector).press_sequentially(password, delay=50)

        # Click the submit button
        page.click(submit_button_selector, timeout=10000)

        # Wait for navigation or a success indicator (e.g., user dashboard element)
        # Waiting for the login modal to disappear indicates success or page reload
        print("Waiting up to 90 seconds for login to complete (Solve reCAPTCHA manually if prompted)...")
        page.wait_for_selector(SELECTORS["login_modal_hidden"], state="hidden", timeout=1600000)
        page.wait_for_load_state("domcontentloaded")
        print("Login successful.")
        return True
    except PlaywrightTimeoutError as e:
        page.screenshot(path="login_failure.png")
        print(f"Login failed: Timeout while waiting for page elements. Saved login_failure.png. {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during login: {e}")
        return False


def search_and_filter_internships(page):
    """Navigates to the internships search page and applies keyword filters."""
    print(f"Navigating to internships search page: {INTERNSHIPS_SEARCH_URL}")
    try:
        page.goto(INTERNSHIPS_SEARCH_URL, timeout=20000)

        # Combine keywords for a general search or apply them sequentially if there's a specific mechanisms
        # For simplicity, we'll try to submit a multi-keyword search query if possible,
        # or simulate a search. Inspecting Internshala's search input is key here.
        # If there is a single search input that accepts multiple keywords, use that.
        # Otherwise, this part might need complex iteration.
        # Let's assume a general search input and then potentially filtering.

        print("Waiting for internship listings to load...")
        # Wait for a common element that indicates listings are present
        page.wait_for_selector(SELECTORS["internship_listings"], timeout=20000)
        print("Internship listings page loaded.")
        return True
    except PlaywrightTimeoutError as e:
        print(f"Failed to load internship listings: Timeout. {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during internship search: {e}")
        return False


def apply_one_click_internships(page, keywords, dry_run=False):
    """
    On the matching-preferences page:
    - For each listing, click to open the popup.
    - In the popup, click the final "Apply now" button.
    - Then click the "Submit" button inside the flow.
    - Log details: company, role, date_applied, listing_url (same page), status.
    """
    print(f"\nScanning listings on matching preferences page for one-click apply (popup flow)...")
    applied_records = []
    listings = page.query_selector_all(SELECTORS["internship_listings"])

    if not listings:
        print("No listings found on the matching preferences page.")
        return []

    # First, collect all listings so we don't pollute the DOM iteration by navigating away
    listings_data = []
    
    for i, listing in enumerate(listings, start=1):
        try:
            company_el = listing.query_selector(SELECTORS["company_name"])
            role_el = listing.query_selector(SELECTORS["role_name"])
            listing_url_el = listing.query_selector(SELECTORS["listing_url"])

            if not (company_el and role_el and listing_url_el):
                continue

            company = company_el.inner_text().strip()
            role = role_el.inner_text().strip()
            listing_url = listing_url_el.get_attribute("href")
            if not listing_url.startswith("http"):
                listing_url = "https://internshala.com" + listing_url
                
            listings_data.append({
                "index": i, "company": company, "role": role, "listing_url": listing_url
            })
        except Exception as e:
            print(f"Error extracting listing {i}: {e}")

    # Now navigate to each listing directly
    for data in listings_data:
        i, company, role, listing_url = data["index"], data["company"], data["role"], data["listing_url"]
        print(f"\nListing {i}: '{role}' at '{company}' ({listing_url})")

        try:
            # Step 1: Navigate directly to the listing details page
            page.goto(listing_url, timeout=20000)

            # Step 2: Click the "Apply now" button (with Self-Healing Agent wrapper)
            if not dry_run:
                print("Applying: clicking 'Apply now'...")
                success = robust_wait_and_click(page, "apply_now_btn", force=True)
                if not success:
                    print(f"Listing {i}: 'Apply now' button ultimately not found. Skipping.")
                    continue
            else:
                print(f"Dry run: Would click 'Apply now' on {listing_url}.")

            # Step 2.5: Sometimes there forms a "Proceed to application" popup first
            proceed_btn = page.locator(SELECTORS["proceed_btn"]).first
            try:
                proceed_btn.wait_for(state="visible", timeout=5000)
                if not dry_run:
                    print("Clicking 'Proceed to application'...")
                    proceed_btn.click(timeout=10000, force=True)
            except PlaywrightTimeoutError:
                # It's fine if there is no "Proceed" button, might go straight to Submit
                pass

            # Step 3: Wait for the Submit Application flow (might be on next page or modal)
            submit_btn = page.locator(SELECTORS["submit_btn"]).first
            try:
                submit_btn.wait_for(state="visible", timeout=10000)
                if not dry_run:
                    submit_btn.click(timeout=10000, force=True)
                else:
                    print(f"Dry run: Would click Submit for listing {i}.")
            except PlaywrightTimeoutError:
                print(f"Listing {i}: Submit button not found after clicking Apply. Skipping.")
                continue

            # Optional: wait for a lightweight confirmation or network idle
            if not dry_run:
                try:
                    # Internshala's success popups change frequently or navigate to a new page.
                    # Waiting for network idle is a more robust way to ensure the submit finished.
                    page.wait_for_load_state("networkidle", timeout=15000)
                    print(f"Application submitted for '{role}' at '{company}'.")
                except PlaywrightTimeoutError:
                    print(f"Applied for '{role}'. Network didn't fully idle, but proceeding...")
            else:
                print(f"Dry run: Simulated application for '{role}' at '{company}'.")

            # Log the application
            status = "dry_run" if dry_run else "applied"
            new_record = {
                "company": company,
                "role": role,
                "date_applied": get_system_time_iso(),
                "listing_url": listing_url,
                "status": status
            }
            applied_records.append(new_record)
            save_log(new_record)

        except Exception as e:
            print(f"Error processing listing {i}: {e}")

    print(f"\n--- Application Summary ---")
    print(f"Total applied (or simulated): {len(applied_records)}")
    return applied_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without applying.")
    parser.add_argument("--headed", action="store_true", help="Run headed to solve CAPTCHA manually.")
    args = parser.parse_args()
    dry_run = bool(args.dry_run)
    headed = bool(args.headed)

    username, password = load_credentials()
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "internshala_session")
        print(f"Using persistent browser session in: {user_data_dir}")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=not headed,
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.pages[0] if context.pages else context.new_page()

        login_ok = login_to_internshala(page, username, password)
        if not login_ok:
            print("Aborting due to login failure.")
            context.close()
            return

        if not search_and_filter_internships(page):
            print("Aborting due to listings load failure.")
            context.close()
            return

        records = apply_one_click_internships(page, KEYWORDS, dry_run=dry_run)
        if not records:
            print("No applications recorded.")

        context.close()


if __name__ == "__main__":
    main()
