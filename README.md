# Internshala Automation Bot with Self-Healing AI

Welcome to the **Internshala Automation** project. This tool automates the process of finding and applying to internships on Internshala that feature a "one-click" apply option. 

What makes this project truly unique is its **Self-Healing Agentic Workflow**. Web layouts change frequently, which usually breaks hardcoded automation scripts. This bot uses **CrewAI** and **LLMs (GPT-4o)** to autonomously detect when a CSS selector fails, inspect the raw HTML DOM, determine the newly updated CSS selector, patch its own `selectors.yaml` configuration file, and retry the action—completely without human intervention.

---

## Features

1. **Automated Search & Apply**: Automatically searches for your desired keywords (e.g., AI, ML, SWE) and applies to matched internships.
2. **Self-Healing Selectors**: If Internshala updates their website and a button's ID or Class changes, the script catches the `TimeoutError`. A CrewAI Agent steps in, reads the active DOM, fixes the selector in `selectors.yaml`, and resumes the script.
3. **Application Logging**: Keeps a JSON log file of all successful applications including company name, role, and the application URL so you can track your progress.
4. **Dry Run Mode**: Safely test your automation setup without actually submitting an application to any company.

## Architecture

The self-healing workflow utilizes a 3-Phase Agentic Loop:
- **Phase 1: The Auditor**: Observes the page DOM and validates if the script's selectors are correct. If an element cannot be found, it analyzes why.
- **Phase 2: The Healer**: Acts as a developer. Based on the Auditor's analysis, it rewrites `selectors.yaml` with the newly valid CSS selectors.
- **Phase 3: The Executor**: Resumes the mass-application automation seamlessly using the corrected selectors.

## Setup & Installation

### 1. Prerequisites
- Python 3.8+
- [Playwright](https://playwright.dev/python/) installed (`playwright install`)
- An OpenAI API Key (needed for the self-healing CrewAI agents).

### 2. Environment Setup
Create a virtual environment and install the required packages:

```bash
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
pip install -r requirements.txt
playwright install
```

### 3. Configuration
Create a `.env` file in the root directory and add your credentials:

```ini
INTERNSHALA_USERNAME="your_email@example.com"
INTERNSHALA_PASSWORD="your_secret_password"
OPENAI_API_KEY="sk-your-openai-api-key"
```

You can customize the job search keywords directly in `script.py`. 

## Usage

**Run the Standard Automation:**
```bash
python script.py
```

**Run in Dry-Run Mode (Safe Testing):**
```bash
python script.py --dry-run
```

**Application Logs:**
All successful applications (or simulated dry runs) are saved to `logs/internshala_applied.json`.

## Disclaimer

Automated applications and aggressive scraping may violate Internshala's Terms of Service. Be mindful of potential rate limits. Use this code responsibly and at your own risk.
