import asyncio
import io
import time
from typing import Optional, Dict, Any, List
from PIL import Image
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from playwright.sync_api import sync_playwright, Browser as SyncBrowser, BrowserContext as SyncBrowserContext, Page as SyncPage
import json
import os
from pathlib import Path

class PlaywrightBrowserController:
    """
    Playwright-based browser controller for the web browsing agent.
    Supports both async and sync operations.
    """
    
    def __init__(self, 
                 headless: bool = False,
                 browser_type: str = "chromium",
                 viewport_size: Dict[str, int] = None,
                 user_agent: str = None,
                 slow_mo: int = 0):
        """
        Initialize the Playwright browser controller.
        
        Args:
            headless: Whether to run browser in headless mode
            browser_type: Browser type ('chromium', 'firefox', 'webkit')
            viewport_size: Viewport dimensions {'width': 1280, 'height': 720}
            user_agent: Custom user agent string
            slow_mo: Slow down operations by specified milliseconds
        """
        self.headless = headless
        self.browser_type = browser_type
        self.viewport_size = viewport_size or {"width": 1280, "height": 720}
        self.user_agent = user_agent
        self.slow_mo = slow_mo
        
        # Browser instances
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # State tracking
        self.is_initialized = False
        self.current_url = ""
        self.page_load_timeout = 30000  # 30 seconds
        
    def initialize(self):
        """Initialize the browser (sync version)."""
        if self.is_initialized:
            return
            
        try:
            self.playwright = sync_playwright().start()
            
            # Select browser
            if self.browser_type == "chromium":
                browser_launcher = self.playwright.chromium
            elif self.browser_type == "firefox":
                browser_launcher = self.playwright.firefox
            elif self.browser_type == "webkit":
                browser_launcher = self.playwright.webkit
            else:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")
            
            # Launch browser
            self.browser = browser_launcher.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--no-sandbox" if os.getenv("CI") else "",
                ] if self.browser_type == "chromium" else []
            )
            
            # Create context
            context_options = {
                "viewport": self.viewport_size,
                "ignore_https_errors": True,
            }
            
            if self.user_agent:
                context_options["user_agent"] = self.user_agent
                
            self.context = self.browser.new_context(**context_options)
            
            # Create page
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.page_load_timeout)
            
            self.is_initialized = True
            print(f"Playwright browser ({self.browser_type}) initialized successfully")
            
        except Exception as e:
            print(f"Failed to initialize browser: {e}")
            self.cleanup()
            raise
    
    def cleanup(self):
        """Clean up browser resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.is_initialized = False
    
    def get_screenshot(self) -> Image.Image:
        """Get current screenshot as PIL Image."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            screenshot_bytes = self.page.screenshot(full_page=False, type="png")
            return Image.open(io.BytesIO(screenshot_bytes))
        except Exception as e:
            print(f"Failed to get screenshot: {e}")
            # Return a blank image as fallback
            return Image.new('RGB', self.viewport_size.values(), color='white')
    
    def click(self, x: int, y: int, delay: float = 0.1):
        """Click at coordinates (x, y)."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            # Use mouse click for precise coordinates
            self.page.mouse.click(x, y)
            time.sleep(delay)
            print(f"Clicked at coordinates ({x}, {y})")
        except Exception as e:
            print(f"Failed to click at ({x}, {y}): {e}")
    
    def type_text(self, text: str, delay: float = 0.05):
        """Type text at current cursor position."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            # Type with realistic delay between keystrokes
            self.page.keyboard.type(text, delay=int(delay * 1000))
            print(f"Typed text: '{text}'")
        except Exception as e:
            print(f"Failed to type text '{text}': {e}")
    
    def press_key(self, key: str):
        """Press a specific key."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.keyboard.press(key)
            print(f"Pressed key: {key}")
        except Exception as e:
            print(f"Failed to press key '{key}': {e}")
    
    def scroll(self, direction: str, amount: int = 500):
        """Scroll in given direction."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            if direction.lower() == "down":
                self.page.mouse.wheel(0, amount)
            elif direction.lower() == "up":
                self.page.mouse.wheel(0, -amount)
            elif direction.lower() == "right":
                self.page.mouse.wheel(amount, 0)
            elif direction.lower() == "left":
                self.page.mouse.wheel(-amount, 0)
            else:
                print(f"Unknown scroll direction: {direction}")
                return
                
            time.sleep(0.5)  # Wait for scroll to complete
            print(f"Scrolled {direction} by {amount} pixels")
            
        except Exception as e:
            print(f"Failed to scroll {direction}: {e}")
    
    def go_back(self):
        """Navigate back in browser history."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.go_back(wait_until="networkidle")
            self.current_url = self.page.url
            print("Navigated back")
        except Exception as e:
            print(f"Failed to go back: {e}")
    
    def go_forward(self):
        """Navigate forward in browser history."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.go_forward(wait_until="networkidle")
            self.current_url = self.page.url
            print("Navigated forward")
        except Exception as e:
            print(f"Failed to go forward: {e}")
    
    def refresh(self):
        """Refresh current page."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.reload(wait_until="networkidle")
            print("Page refreshed")
        except Exception as e:
            print(f"Failed to refresh page: {e}")
    
    def goto(self, url: str, wait_until: str = "networkidle"):
        """Navigate to URL."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            # Ensure URL has protocol
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
                
            self.page.goto(url, wait_until=wait_until)
            self.current_url = self.page.url
            print(f"Navigated to: {url}")
            
        except Exception as e:
            print(f"Failed to navigate to {url}: {e}")
    
    def restart(self):
        """Restart/reset browser state."""
        print("Restarting browser...")
        self.cleanup()
        self.initialize()
    
    def wait_for_element(self, selector: str, timeout: int = 5000) -> bool:
        """Wait for element to appear."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception as e:
            print(f"Element '{selector}' not found within {timeout}ms: {e}")
            return False
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get current page information."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            return {
                "url": self.page.url,
                "title": self.page.title(),
                "viewport": self.page.viewport_size,
                "content_loaded": True
            }
        except Exception as e:
            print(f"Failed to get page info: {e}")
            return {"error": str(e)}
    
    def execute_javascript(self, script: str) -> Any:
        """Execute JavaScript on the page."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            result = self.page.evaluate(script)
            return result
        except Exception as e:
            print(f"Failed to execute JavaScript: {e}")
            return None
    
    def handle_dialog(self, accept: bool = True, prompt_text: str = ""):
        """Set up dialog handler for alerts, confirms, prompts."""
        if not self.is_initialized:
            self.initialize()
            
        def dialog_handler(dialog):
            if dialog.type == "prompt" and prompt_text:
                dialog.accept(prompt_text)
            elif accept:
                dialog.accept()
            else:
                dialog.dismiss()
                
        self.page.on("dialog", dialog_handler)
    
    def save_screenshot(self, filepath: str, full_page: bool = False):
        """Save screenshot to file."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.screenshot(path=filepath, full_page=full_page)
            print(f"Screenshot saved to: {filepath}")
        except Exception as e:
            print(f"Failed to save screenshot: {e}")
    
    def get_element_at_coordinates(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """Get element information at specific coordinates."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            # JavaScript to get element at coordinates
            script = f"""
            const element = document.elementFromPoint({x}, {y});
            if (element) {{
                return {{
                    tagName: element.tagName,
                    className: element.className,
                    id: element.id,
                    textContent: element.textContent?.substring(0, 100),
                    href: element.href,
                    type: element.type,
                    value: element.value,
                    placeholder: element.placeholder
                }};
            }}
            return null;
            """
            
            element_info = self.page.evaluate(script)
            return element_info
            
        except Exception as e:
            print(f"Failed to get element at ({x}, {y}): {e}")
            return None
    
    def wait_for_page_load(self, timeout: int = 30000):
        """Wait for page to fully load."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            print(f"Page load timeout: {e}")
    
    def accept_cookies(self):
        """Try to accept cookies if cookie banner is present."""
        if not self.is_initialized:
            self.initialize()
            
        try:
            # Common cookie acceptance selectors
            cookie_selectors = [
                'button:has-text("Accept")',
                'button:has-text("Accept All")',
                'button:has-text("Allow All")',
                'button:has-text("I Accept")',
                'button:has-text("OK")',
                '[id*="accept"]',
                '[class*="accept"]',
                '[data-testid*="accept"]'
            ]
            
            for selector in cookie_selectors:
                try:
                    if self.page.is_visible(selector, timeout=1000):
                        self.page.click(selector)
                        print("Accepted cookies")
                        time.sleep(1)
                        return True
                except:
                    continue
                    
            print("No cookie banner found or failed to accept")
            return False
            
        except Exception as e:
            print(f"Failed to handle cookies: {e}")
            return False


class PlaywrightWebAgent:
    """
    Web browsing agent specifically designed for Playwright integration.
    """
    
    def __init__(self, 
                 agent,  # WebBrowsingAgent instance
                 headless: bool = False,
                 browser_type: str = "chromium",
                 viewport_size: Dict[str, int] = None):
        """
        Initialize the Playwright-based web agent.
        
        Args:
            agent: WebBrowsingAgent instance
            headless: Whether to run browser in headless mode
            browser_type: Browser type ('chromium', 'firefox', 'webkit')
            viewport_size: Viewport dimensions
        """
        self.agent = agent
        self.browser_controller = PlaywrightBrowserController(
            headless=headless,
            browser_type=browser_type,
            viewport_size=viewport_size
        )
        
    def run_task(self, task: str, starting_url: str = None, max_steps: int = 30) -> Dict[str, Any]:
        """
        Run a complete browsing task with Playwright.
        
        Args:
            task: Task description
            starting_url: Initial URL to navigate to
            max_steps: Maximum number of steps
            
        Returns:
            Task execution result
        """
        try:
            # Initialize browser
            self.browser_controller.initialize()
            
            # Navigate to starting URL if provided
            if starting_url:
                self.browser_controller.goto(starting_url)
                self.browser_controller.wait_for_page_load()
                
                # Try to accept cookies
                self.browser_controller.accept_cookies()
            
            # Run the task
            result = self.agent.run_task(task, self.browser_controller, max_steps)
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Task execution failed: {str(e)}",
                "error_type": type(e).__name__
            }
        finally:
            # Clean up
            self.browser_controller.cleanup()
    
    def interactive_session(self, starting_url: str = None):
        """
        Start an interactive session for testing and debugging.
        """
        try:
            self.browser_controller.initialize()
            
            if starting_url:
                self.browser_controller.goto(starting_url)
                self.browser_controller.wait_for_page_load()
                self.browser_controller.accept_cookies()
            
            print("=== Interactive Playwright Web Agent ===")
            print("Browser initialized. Use the following commands:")
            print("  task <description> - Execute a task")
            print("  goto <url> - Navigate to URL")
            print("  screenshot - Take and save screenshot")
            print("  info - Get current page info")
            print("  quit - Exit and cleanup")
            print()
            
            while True:
                try:
                    command = input("> ").strip()
                    
                    if command.startswith("task "):
                        task_desc = command[5:]
                        print(f"Executing task: {task_desc}")
                        result = self.agent.run_task(task_desc, self.browser_controller, 20)
                        print(f"Task result: {result}")
                        
                    elif command.startswith("goto "):
                        url = command[5:]
                        self.browser_controller.goto(url)
                        self.browser_controller.wait_for_page_load()
                        self.browser_controller.accept_cookies()
                        
                    elif command == "screenshot":
                        timestamp = int(time.time())
                        filename = f"screenshot_{timestamp}.png"
                        self.browser_controller.save_screenshot(filename)
                        
                    elif command == "info":
                        info = self.browser_controller.get_page_info()
                        print(f"Page info: {json.dumps(info, indent=2)}")
                        
                    elif command == "quit":
                        break
                        
                    else:
                        print("Unknown command")
                        
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"Error: {e}")
                    
        finally:
            self.browser_controller.cleanup()


# Example usage and test script
def main():
    """Example usage of the Playwright web agent."""
    
    # Import your web browsing agent
    # from web_agent import WebBrowsingAgent
    
    print("Playwright Web Agent Example")
    print("=" * 40)
    
    # You would initialize your agent here
    # agent = WebBrowsingAgent()
    # playwright_agent = PlaywrightWebAgent(agent, headless=False)
    
    # Example tasks
    example_tasks = [
        {
            "task": "Search for 'Python web scraping' on Google and find the first tutorial link",
            "url": "https://google.com"
        },
        {
            "task": "Find the current price of Bitcoin on CoinGecko",
            "url": "https://coingecko.com"
        },
        {
            "task": "Get the weather forecast for New York on Weather.com",
            "url": "https://weather.com"
        }
    ]
    
    print("Example tasks that can be executed:")
    for i, example in enumerate(example_tasks, 1):
        print(f"{i}. {example['task']}")
        print(f"   Starting URL: {example['url']}")
        print()
    
    # Uncomment to run an example:
    # result = playwright_agent.run_task(
    #     example_tasks[0]["task"], 
    #     example_tasks[0]["url"],
    #     max_steps=15
    # )
    # print(f"Result: {result}")
    
    # Or start interactive session:
    # playwright_agent.interactive_session("https://google.com")


if __name__ == "__main__":
    main()