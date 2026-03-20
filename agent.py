import os
import yaml
import base64
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

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
            "A Playwright timeout occurred while searching for a selector. Here is the HTML dump of the page:\n\n"
            "```html\n{html_dump}\n```\n\n"
            "Here are our current expected selectors from selectors.yaml:\n\n"
            "```yaml\n{current_yaml}\n```\n\n"
            "Task: Evaluate if the expected selectors still exist and are valid in the HTML dump. "
            "Output an analysis detailing precisely which selector is broken, why it failed, and what "
            "the new, correct CSS selector should be based on the HTML provided. If it's impossible to tell, output 'FAILURE'."
        ),
        expected_output="An audit report detailing broken selectors, or the word 'FAILURE'.",
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

# 5. Assemble the Crew and Run
def heal_selectors(html_snippet, screenshot_path=None):
    """
    Called by script.py when a timeout error occurs. 
    Triggers the LLM self-healing workflow.
    """
    print("Initiating Self-Healing Protocol (Phase 1: Fast DOM pass with gpt-4o-mini)...")
    
    with open(SELECTORS_FILE, "r") as f:
        current_yaml = f.read()

    auditor_fast, healer_fast = get_agents(llm_fast)
    tasks_fast = get_tasks(auditor_fast, healer_fast)

    crew = Crew(
        agents=[auditor_fast, healer_fast],
        tasks=tasks_fast,
        process=Process.sequential
    )

    result = crew.kickoff(inputs={
        'html_dump': html_snippet[:10000], 
        'current_yaml': current_yaml
    })
    
    final_output = str(result.raw).strip()

    # Fallback to smart model / vision strategy if fast pass fails
    if "FAILURE" in final_output or "selectors:" not in final_output:
        print("\nFast pass returned low confidence or failed. Triggering Smart Fallback (gpt-4o)...")
        
        vision_context = ""
        if screenshot_path and os.path.exists(screenshot_path):
            print(f"(Screenshot saved at {screenshot_path} available for vision fallback)")
            with open(screenshot_path, "rb") as img_file:
                b64_string = base64.b64encode(img_file.read()).decode("utf-8")
                # Using markdown image syntax commonly accepted by vision models via Langchain wrappers
                vision_context = f"\n\nHere is a screenshot of the page currently:\n![Screenshot](data:image/png;base64,{b64_string})"
            
        auditor_smart, healer_smart = get_agents(llm_smart)
        tasks_smart = get_tasks(auditor_smart, healer_smart)
        
        # Inject the vision context into the auditor's description
        tasks_smart[0].description += vision_context
        
        crew_smart = Crew(
            agents=[auditor_smart, healer_smart],
            tasks=tasks_smart,
            process=Process.sequential
        )
        
        result = crew_smart.kickoff(inputs={
            'html_dump': html_snippet[:20000], # Pass more context to the smarter model
            'current_yaml': current_yaml
        })
        final_output = str(result.raw).strip()

    # Save the Healer's output to the file (removing markdown blocks if LLM adds them)
    if final_output.startswith("```yaml"):
        final_output = final_output[7:]
    if final_output.startswith("```"):
         final_output = final_output[3:]
    if final_output.endswith("```"):
         final_output = final_output[:-3]
    final_output = final_output.strip()

    with open(SELECTORS_FILE, "w") as f:
        f.write(final_output)
    
    print("\nSelf-Healing Complete! selectors.yaml has been updated.")

if __name__ == "__main__":
    print("Agent module loaded. Testing agent compilation...")
    print("Agents assembled and ready.")
