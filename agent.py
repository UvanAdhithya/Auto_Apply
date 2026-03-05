import os
import yaml
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables (Make sure OPENAI_API_KEY is in .env)
load_dotenv()

SELECTORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selectors.yaml")

# 1. Provide the LLM
# We default to gpt-4o which has excellent vision/DOM parsing capabilities.
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# --- Define Agents ---

# 2. Define the Auditor Agent (The Inspector)
auditor = Agent(
    role="Web Automation QA Engineer",
    goal="Ensure the Internshala DOM matches the configured selectors in selectors.yaml",
    backstory=(
        "You are an expert QA engineer who evaluates raw HTML to find the correct CSS selectors "
        "for buttons and forms. Your job is purely observational. You look at HTML and verify if "
        "expected CSS selectors (like 'button#submit' or 'div.listing') would correctly target "
        "the right elements. You are meticulous and understand complex web structures."
    ),
    verbose=True,
    allow_delegation=False, # The Auditor works alone
    llm=llm
)

# 3. Define the Healer Agent (The Developer)
healer = Agent(
    role="Senior Python Automation Engineer",
    goal="Rewrite the selectors.yaml file to fix any broken Playwright locators.",
    backstory=(
        "You are a developer who works alongside QA. When QA tells you that a CSS selector is broken, "
        "or that Internshala updated their layout, you rewrite the selectors.yaml configuration file "
        "with perfectly accurate Playwright CSS selectors based on the actual HTML provided."
    ),
    verbose=True,
    allow_delegation=False,
    llm=llm
)

# --- Define Tasks ---

# 4. Define the Tasks
audit_task = Task(
    description=(
        "A Playwright timeout occurred while searching for a selector. Here is the HTML dump of the page:\n\n"
        "```html\n{html_dump}\n```\n\n"
        "Here are our current expected selectors from selectors.yaml:\n\n"
        "```yaml\n{current_yaml}\n```\n\n"
        "Task: Evaluate if the expected selectors still exist and are valid in the HTML dump. "
        "Output an analysis detailing precisely which selector is broken, why it failed, and what "
        "the new, correct CSS selector should be based on the HTML provided."
    ),
    expected_output="An audit report detailing broken selectors and their correct replacements.",
    agent=auditor
)

heal_task = Task(
    description=(
        "Based on the QA Auditor's report, fix the `selectors.yaml` configuration. "
        "You must output ONLY the raw, perfectly formatted YAML string. Do not output anything else, "
        "no markdown code blocks, just the raw text of the updated selectors.yaml file.\n\n"
        "Here is the current YAML to base your work off:\n\n"
        "```yaml\n{current_yaml}\n```"
    ),
    expected_output="The final, corrected raw YAML string for selectors.yaml.",
    agent=healer
)

# --- Orchestration ---

# 5. Assemble the Crew and Run
def heal_selectors(html_snippet):
    """
    Called by script.py when a timeout error occurs. 
    Triggers the LLM self-healing workflow.
    """
    print("Initiating Self-Healing Protocol...")
    
    with open(SELECTORS_FILE, "r") as f:
        current_yaml = f.read()

    crew = Crew(
        agents=[auditor, healer],
        tasks=[audit_task, heal_task],
        process=Process.sequential
    )

    print("Auditor and Healer agents deployed.")
    # Fire the agents!
    result = crew.kickoff(inputs={
        'html_dump': html_snippet[:8000], # Trucate safely to avoid token limits just in case
        'current_yaml': current_yaml
    })
    
    # Save the Healer's output to the file (removing markdown blocks if LLM adds them)
    final_output = str(result.raw).strip()
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
