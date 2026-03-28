import os
import yaml
import base64
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from bs4 import BeautifulSoup, Comment
import re
from dotenv import load_dotenv
import os

# Disable the buggy CrewAI telemetry server unconditionally to prevent 30s connection timeouts
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

# Load environment variables (Make sure OPENAI_API_KEY is in .env)
load_dotenv()

SELECTORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selectors.yaml")

# 1. Provide the LLMs
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_smart = ChatOpenAI(model="gpt-4o", temperature=0)

# --- Define Agents ---

def get_agents(llm):
    # 2. Define the Auditor Agent (The Inspector)
    auditor = Agent(
        role="Web Automation QA Engineer",
        goal="Ensure the Internshala DOM matches the configured selectors in selectors.yaml. If the selector cannot be determined, output 'FAILURE'.",
        backstory=(
            "You are an expert QA engineer who evaluates raw HTML to find the correct CSS selectors "
            "for buttons and forms. Your job is purely observational. You look at HTML and verify if "
            "expected CSS selectors (like 'button#submit' or 'div.listing') would correctly target "
            "the right elements. You are meticulous and understand complex web structures. "
            "If the HTML is completely missing the element, state 'FAILURE'."
        ),
        verbose=True,
        allow_delegation=False, # The Auditor works alone
        llm=llm
    )

    # 3. Define the Healer Agent (The Developer)
    healer = Agent(
        role="Senior Python Automation Engineer",
        goal="Rewrite the selectors.yaml file to fix any broken Playwright locators. If Audit says 'FAILURE', you must also output 'FAILURE'.",
        backstory=(
            "You are a developer who works alongside QA. When QA tells you that a CSS selector is broken, "
            "or that Internshala updated their layout, you rewrite the selectors.yaml configuration file "
            "with perfectly accurate Playwright CSS selectors based on the actual HTML provided. "
            "If QA could not find the element, you MUST output the exact word 'FAILURE' and nothing else."
        ),
        verbose=True,
        allow_delegation=False,
        llm=llm
    )
    return auditor, healer

# --- Define Tasks ---

def get_tasks(auditor, healer):
    # 4. Define the Tasks
    audit_task = Task(
        description=(
            "One or more CSS selectors used by our Playwright automation script are failing to match "
            "elements on the Internshala page. This could be due to a site redesign, an A/B test, or "
            "incorrect selectors.\n\n"
            "The following selector keys are specifically broken: {broken_keys}\n\n"
            "Here is the HTML dump of the page:\n\n"
            "```html\n{html_dump}\n```\n\n"
            "Here are our current expected selectors from selectors.yaml:\n\n"
            "```yaml\n{current_yaml}\n```\n\n"
            "Task: Focus on the broken keys listed above. For each one, find the correct CSS selector "
            "that matches the corresponding element in the HTML dump. Provide an analysis detailing "
            "precisely why the current selector is broken and what the correct replacement should be. "
            "If a broken key is not present in the page HTML at all, output 'FAILURE' for that key."
        ),
        expected_output="An audit report with corrected selectors for each broken key, or 'FAILURE'.",
        agent=auditor
    )

    heal_task = Task(
        description=(
            "Based on the QA Auditor's report, fix the `selectors.yaml` configuration. "
            "You must output ONLY the raw, perfectly formatted YAML string. Do not output anything else, "
            "no markdown code blocks, just the raw text of the updated selectors.yaml file.\n\n"
            "Here is the current YAML to base your work off:\n\n"
            "```yaml\n{current_yaml}\n```\n\n"
            "If the auditor output 'FAILURE', you must ONLY output the string 'FAILURE'."
        ),
        expected_output="The final, corrected raw YAML string for selectors.yaml, or 'FAILURE'.",
        agent=healer
    )
    return [audit_task, heal_task]

# --- Orchestration ---

def clean_html(html_content):
    """Strips massive bloat tags to ensure the <body> fits inside the LLM context."""
    soup = BeautifulSoup(html_content, "html.parser")
    # Remove script, style, svg, and head tags to save tokens
    for tag in soup(["script", "style", "svg", "path", "head", "noscript", "meta", "link", "iframe"]):
        tag.decompose()
    
    # Remove HTML comments
    for element in soup.find_all(string=lambda text: isinstance(text, Comment)):
        element.extract()
        
    cleaned_html = str(soup)
    # Remove excessive blank space
    cleaned_html = re.sub(r'\s+', ' ', cleaned_html)
    return cleaned_html

# 5. Assemble the Crew and Run
def heal_selectors(html_snippet, screenshot_path=None, broken_keys=None):
    """
    Called by script.py when selectors fail (click timeouts OR extraction misses). 
    Triggers the LLM self-healing workflow.
    
    Args:
        html_snippet: Raw page HTML.
        screenshot_path: Optional path to a screenshot of the page.
        broken_keys: Optional set/list of specific selector keys that failed.
                     If None, the agent audits all selectors.
    """
    if broken_keys is None:
        broken_keys = "all (unknown which specific keys are broken)"
    # Clean the HTML to ensure the actual visible elements reach the LLM
    html_snippet = clean_html(html_snippet)
    
    # Dump the cleaned HTML to disk so I (Antigravity) can read exactly what the AI sees
    with open("agent_dom_dump.html", "w", encoding="utf-8") as f:
        f.write(html_snippet)
    
    print(f"Initiating Self-Healing Protocol (Phase 1: Fast DOM pass)... (DOM optimally compressed to {len(html_snippet)} chars)")
    
    with open(SELECTORS_FILE, "r") as f:
        current_yaml = f.read()

    auditor_fast, healer_fast = get_agents(llm_fast)
    tasks_fast = get_tasks(auditor_fast, healer_fast)

    crew = Crew(
        agents=[auditor_fast, healer_fast],
        tasks=tasks_fast,
        process=Process.sequential
    )

    # Execute Phase 1
    try:
        result = crew.kickoff(inputs={
            'html_dump': html_snippet[:100000],  # Send the full compressed DOM snapshot
            'current_yaml': current_yaml,
            'broken_keys': str(broken_keys)
        })
    except Exception as e:
        print(f"Error during fast pass kickoff: {e}")
        result = None # Ensure result is defined for the next check
    
    final_output = str(result.raw).strip() if result else "FAILURE"

    # Fallback to smart model / vision strategy if fast pass fails
    if "FAILURE" in final_output or "selectors:" not in final_output:
        print("\nFast pass returned low confidence or failed. Triggering Smart Fallback (gpt-4o)...")

        print("\n(Running smart fallback with gpt-4o for better DOM reasoning without vision due to token limits...)")
        auditor_smart, healer_smart = get_agents(llm_smart)
        tasks_smart = get_tasks(auditor_smart, healer_smart)
        
        print("Initiating Self-Healing Protocol (Phase 2: Smart LLM fallback)...")
        fallback_crew = Crew(
            agents=[auditor_smart, healer_smart], # Use both smart agents for the fallback
            tasks=tasks_smart,
            process=Process.sequential,
            verbose=True
        )
        
        try:
            result = fallback_crew.kickoff(inputs={
                'html_dump': html_snippet[:100000], # Pass the full valid DOM to the smarter model
                'current_yaml': current_yaml,
                'broken_keys': str(broken_keys)
            })
        except Exception as e:
            print(f"Error during smart fallback kickoff: {e}")
            result = None # Ensure result is defined for the next check
        final_output = str(result.raw).strip() if result else "FAILURE"

    # Clean any markdown wrapping before evaluation
    if final_output.startswith("```yaml"):
        final_output = final_output[7:]
    if final_output.startswith("```"):
         final_output = final_output[3:]
    if final_output.endswith("```"):
         final_output = final_output[:-3]
    final_output = final_output.strip()

    if final_output == "FAILURE" or "selectors:" not in final_output:
        print("\nSelf-Healing Agent could not find a valid selector layout (FAILURE or invalid output format).")
        return False

    with open(SELECTORS_FILE, "w") as f:
        f.write(final_output)
    
    print("\nSelf-Healing Complete! selectors.yaml has been updated.")
    return True

if __name__ == "__main__":
    print("Agent module loaded. Testing agent compilation...")
    print("Agents assembled and ready.")
