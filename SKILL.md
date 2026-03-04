# internshala-automation

**Title:** Internshala Automation Skill

**Summary:**
This skill automates the process of logging into Internshala.com, searching for internships based on specified keywords, and applying to listings that feature a one-click apply option. It logs the details of each successful application, including company name, role, date applied (using system time), and the link to the listing.

**Usage:**
1.  **Prerequisites:**
    *   Ensure you have Python 3.8+ installed.
    *   Install Playwright: `pip install playwright`
    *   Install browser binaries: `playwright install`
    *   Set environment variables for your Internshala credentials:
        ```bash
        export INTERNSHALA_USERNAME="your_email@example.com"
        export INTERNSHALA_PASSWORD="your_secret_password"
        ```
        (Or set them via your system's environment variable settings.)

2.  **Execution:**
    *   Navigate to the directory where the `script.py` is located using your terminal.
    *   Run the script: `python script.py`
    *   To perform a dry run (simulate actions without actually applying): `python script.py --dry-run`

3.  **Output:**
    *   Application logs will be saved in `logs/internshala_applied.json`.
    *   On completion, the script will print a summary of applications made or simulated.

**Configuration:**
*   **Keywords:** AI, ML, SWE, Web Dev, Frontend, Backend
*   **Login Credentials:** Read from `INTERNSHALA_USERNAME` and `INTERNSHALA_PASSWORD` environment variables.
*   **Date Applied:** Uses the system's local time.
*   **Log Output:** JSON file located at `logs/internshala_applied.json`.
*   **Browser:** Uses Playwright with Chromium in headless mode by default.

**Security & Best Practices:**
*   **Credentials:** Never hardcode credentials. Use environment variables.
*   **Terms of Service:** Automated applications may violate Internshala's Terms of Service. Use responsibly and at your own risk. This script includes a dry-run mode for testing.
*   **Rate Limiting:** Be mindful of potential rate limits imposed by Internshala. This script does not implement advanced rate-limiting logic but can be extended.
*   **Selector Fragility:** Website structure can change. If the script fails, selectors might need to be updated by inspecting the current Internshala website structure.

**Author:** Helen (your AI assistant)
**Version:** 1.0
