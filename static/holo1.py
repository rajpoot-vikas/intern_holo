from web_agent import WebBrowsingAgent  # Your existing agent
from playwright_controller import PlaywrightWebAgent

# Initialize the agent
agent = WebBrowsingAgent()
playwright_agent = PlaywrightWebAgent(
    agent, 
    headless=False,  # Set to True for headless mode
    browser_type="chromium"
)

# Run a task
result = playwright_agent.run_task(
    "Find the price of iPhone 15 on Amazon",
    starting_url="https://amazon.com",
    max_steps=25
)
print(f"Task completed: {result}") 

