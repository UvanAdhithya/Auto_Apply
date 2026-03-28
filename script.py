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
INTERNSHIPS_SEARCH_URL = "https://internshala.com/internships/"

# Keywords to search for internships (Default Fallback)
KEYWORDS = [
    "AI",
    "ML",
    "SWE",
    "Web Dev",
    "Frontend",
    "Backend"
]

UNHEALABLE_SELECTORS = set()

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
    except Exception as e:
        if selector_key in UNHEALABLE_SELECTORS:
            print(f"Skipping AI heal for '{selector_key}' to save credits (previously marked as unhealable).")
            return False

        print(f"Failed to find or click '{selector_key}' (Error: {type(e).__name__}). Triggering self-healing AI agent...")
        try:
            import agent
            # Take a screenshot before healing just in case
            screenshot_path = os.path.join(os.getcwd(), f"healing_trigger_{selector_key}.png")
            page.screenshot(path=screenshot_path)
            
            # Send HTML to the CrewAI agents
            is_healed = agent.heal_selectors(page.content(), screenshot_path=screenshot_path)
            
            if not is_healed:
                print(f"Self-healing agent failed to repair '{selector_key}'. Marking as unhealable for this run.")
                UNHEALABLE_SELECTORS.add(selector_key)
                return False
                
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
            UNHEALABLE_SELECTORS.add(selector_key)
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


def search_and_filter_internships(page, search_keywords_str=None):
    """Navigates to the internships search page and applies keyword filters."""
    print(f"Navigating to internships search page: {INTERNSHIPS_SEARCH_URL}")
    try:
        page.goto(INTERNSHIPS_SEARCH_URL, timeout=60000, wait_until="domcontentloaded")

        if search_keywords_str:
            print(f"Applying search keywords: {search_keywords_str}")
            try:
                # Dismiss overlay popups if they exist (e.g. subscription alerts)
                try:
                    close_btn = page.locator(SELECTORS.get("overlay_close", ".close_action")).first
                    if close_btn.is_visible():
                        close_btn.click(timeout=1000)
                except PlaywrightTimeoutError:
                    pass
                
                # Uncheck preferences checkbox to enable keyword field
                checkbox = page.locator(SELECTORS["preferences_checkbox"])
                if checkbox.is_visible() and checkbox.is_checked():
                    print("Unchecking 'As per my preferences'...")
                    checkbox.uncheck(force=True)
                    page.wait_for_timeout(1000)
                    
                # Fill the search field directly
                print("Filling search input...")
                page.locator(SELECTORS["search_input"]).fill(search_keywords_str, force=True)
                page.locator(SELECTORS["search_btn"]).click(force=True)
                
                # Wait for search navigation
                page.wait_for_timeout(4000)
            except Exception as e:
                print(f"Warning during custom keyword search: {e}")
        else:
            print("No specific keywords provided; relying on default saved user preferences if redirected.")

        print("Waiting for internship listings to load...")
        # Wait for a common element that indicates listings are present
        page.wait_for_selector(SELECTORS["internship_listings"], timeout=20000)
        print("Internship listings page loaded.")
        # Give lazy-loaded / JS-hydrated content time to fully render
        page.wait_for_timeout(3000)
        return True
    except PlaywrightTimeoutError as e:
        print(f"Failed to load internship listings: Timeout. {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during internship search: {e}")
        return False


def _try_extract_all(listings):
    """
    Pure extraction logic — no healing. Iterates every listing element and
    tries to pull company, role, and URL from each one.

    Returns:
        (listings_data, failed_keys)
        - listings_data: list of dicts with index/company/role/listing_url
        - failed_keys:   set of selector keys that failed (e.g. {'role_name', 'listing_url'})
    """
    listings_data = []
    failed_keys = set()
    skipped_hidden = 0
    skipped_missing = 0

    for i, listing in enumerate(listings, start=1):
        try:
            # Skip hidden/ad listings
            try:
                if not listing.is_visible():
                    skipped_hidden += 1
                    continue
            except Exception:
                pass

            company_el = listing.query_selector(SELECTORS["company_name"])
            role_el = listing.query_selector(SELECTORS["role_name"])
            listing_url_el = listing.query_selector(SELECTORS["listing_url"])

            if not (company_el and role_el and listing_url_el):
                missing = []
                if not company_el:
                    missing.append("company_name")
                    failed_keys.add("company_name")
                if not role_el:
                    missing.append("role_name")
                    failed_keys.add("role_name")
                if not listing_url_el:
                    missing.append("listing_url")
                    failed_keys.add("listing_url")
                if skipped_missing < 3:
                    print(f"  Listing {i}: SKIPPED — missing: {', '.join(missing)}")
                skipped_missing += 1
                continue

            company = company_el.inner_text().strip()
            role = role_el.inner_text().strip()
            listing_url = listing_url_el.get_attribute("href")
            if not listing_url.startswith("http"):
                listing_url = "https://internshala.com" + listing_url

            # Skip external aggregator URLs (e.g. appcast.io) — they redirect off-site
            if "internshala.com" not in listing_url and listing_url.startswith("http"):
                continue

            listings_data.append({
                "index": i, "company": company, "role": role, "listing_url": listing_url
            })
        except Exception as e:
            print(f"Error extracting listing {i}: {e}")

    print(f"  Extraction pass: {len(listings_data)} valid, {skipped_hidden} hidden, "
          f"{skipped_missing} missing selectors (of {len(listings)} total)")
    return listings_data, failed_keys


def _trigger_extraction_heal(page, failed_keys):
    """
    Triggers the AI self-healing agent to fix extraction selectors.
    This is the bridge between the extraction loop and agent.heal_selectors().
    """
    print(f"\n🔧 Self-healing: attempting to fix extraction selectors: {failed_keys}")
    try:
        screenshot_path = os.path.join(os.getcwd(), "healing_trigger_extraction.png")
        page.screenshot(path=screenshot_path)

        import agent
        is_healed = agent.heal_selectors(page.content(), screenshot_path=screenshot_path)

        if is_healed:
            # Reload the fixed selectors from YAML
            with open(SELECTORS_FILE, "r") as f:
                SELECTORS.update(yaml.safe_load(f)["selectors"])
            print("✅ Extraction selectors healed and reloaded from selectors.yaml.")
            return True
        else:
            print("❌ Self-healing agent could not fix extraction selectors.")
            return False
    except Exception as e:
        print(f"❌ Self-healing failed with error: {e}")
        return False


def robust_extract_listings(page, max_heal_attempts=1):
    """
    Self-healing wrapper around listing extraction.

    Flow:
      1. query_selector_all for the listings container.
      2. Try extracting company/role/url from each listing.
      3. If >50% of visible listings fail extraction, trigger the self-healing
         agent to fix the broken selectors, then retry.
      4. Return the successfully extracted listings.
    """
    for attempt in range(1 + max_heal_attempts):
        attempt_label = f"(attempt {attempt + 1}/{1 + max_heal_attempts})"

        # Step 1: Find all listing elements
        listings = page.query_selector_all(SELECTORS["internship_listings"])
        print(f"\n{attempt_label} query_selector_all('{SELECTORS['internship_listings']}') "
              f"returned {len(listings)} elements.")

        if not listings:
            if attempt < max_heal_attempts:
                print("No listings found — container selector may be broken.")
                healed = _trigger_extraction_heal(page, {"internship_listings"})
                if healed:
                    continue
            print("No listings found on the matching preferences page.")
            return []

        # Step 2: Attempt extraction
        listings_data, failed_keys = _try_extract_all(listings)

        # Step 3: Evaluate failure rate & heal if necessary
        total_visible = max(len(listings), 1)
        fail_rate = 1 - (len(listings_data) / total_visible)

        if fail_rate > 0.5 and failed_keys and attempt < max_heal_attempts:
            print(f"\n⚠️  High extraction failure rate ({fail_rate:.0%}). "
                  f"Broken keys: {failed_keys}")
            healed = _trigger_extraction_heal(page, failed_keys)
            if healed:
                print("Retrying extraction with healed selectors...")
                continue
            # If healing failed, fall through and use whatever we have

        return listings_data

    return []


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

    # Take a debug screenshot of the page state before processing
    try:
        page.screenshot(path=os.path.join(os.getcwd(), "debug_listings_page.png"))
        print("Saved debug screenshot: debug_listings_page.png")
    except Exception:
        pass

    # --- Self-healing extraction ---
    listings_data = robust_extract_listings(page)

    # Now navigate to each listing directly
    for data in listings_data:
        i, company, role, listing_url = data["index"], data["company"], data["role"], data["listing_url"]
        print(f"\nListing {i}: '{role}' at '{company}' ({listing_url})")

        try:
            # Step 1: Navigate directly to the listing details page
            page.goto(listing_url, timeout=30000, wait_until="domcontentloaded")
            
            # Allow JS to fully hydrate the page before clicking to prevent ghost clicks
            page.wait_for_timeout(3000)

            # Step 2: Click "Apply Now" to open the application modal.
            print("Applying: clicking 'Apply now' to open the application modal...")
            success = robust_wait_and_click(page, "apply_now_btn", force=False)
            if not success:
                print(f"Listing {i}: 'Apply now' button ultimately not found. Skipping.")
                continue

            # Step 2.5: Sometimes Internshala shows a "Proceed to application" popup
            if not dry_run:
                proceed_btn = page.locator(SELECTORS["proceed_btn"]).first
                try:
                    proceed_btn.wait_for(state="visible", timeout=3000)
                    print("Clicking 'Proceed to application'...")
                    proceed_btn.click(timeout=5000, force=True)
                except Exception:
                    # Ignore if the proceed button isn't there, meaning we go straight to the modal
                    pass

            # Step 3: Wait for the Submit Application Form
            if not dry_run:
                # Give the modal animation time to slide in
                page.wait_for_timeout(2000)
                
                print("Waiting for 'Submit' button in the application form...")
                success = robust_wait_and_click(page, "submit_btn", force=True)
                if not success:
                    print(f"Listing {i}: Submit button not found after clicking Apply. Skipping.")
                    continue
            else:
                print(f"Dry run: Simulated clicking Proceed and Submit for listing {i}.")

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
    parser.add_argument("--keywords", type=str, help="Comma-separated keywords to search for.")
    args = parser.parse_args()
    dry_run = bool(args.dry_run)
    headed = bool(args.headed)

    # Prompt user for search keywords
    if args.keywords:
        search_keywords_str = args.keywords
    else:
        try:
            print("\n" + "="*50)
            print("Internshala Automation Bot")
            print("="*50)
            print(f"Default KEYWORDS: {', '.join(KEYWORDS)}")
            user_input = input("Enter keywords to search (comma-separated), or press Enter to use defaults: ").strip()
            if user_input:
                search_keywords_str = user_input
            else:
                search_keywords_str = ', '.join(KEYWORDS)
        except EOFError:
            search_keywords_str = ', '.join(KEYWORDS)

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

        if not search_and_filter_internships(page, search_keywords_str):
            print("Aborting due to listings load failure.")
            context.close()
            return

        records = apply_one_click_internships(page, KEYWORDS, dry_run=dry_run)
        if not records:
            print("No applications recorded.")

        context.close()


if __name__ == "__main__":
    main()
