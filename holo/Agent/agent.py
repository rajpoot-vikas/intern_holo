import asyncio
import base64
import json
import re
from io import BytesIO
from typing import Dict, List, Tuple, Optional, Any, Literal, Union
from dataclasses import dataclass
from enum import Enum

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from pydantic import BaseModel, Field
from Utils.color_logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Model configuration
HF_MODEL_REPO = "Hcompany/Holo1-3B"

# Pydantic models for structured outputs
class ClickAction(BaseModel):
    """Click at specific coordinates on the screen."""
    action: Literal["click"] = "click"
    x: int = Field(description="The x coordinate, number of pixels from the left edge.")
    y: int = Field(description="The y coordinate, number of pixels from the top edge.")

class ClickElementAction(BaseModel):
    """Click at absolute coordinates of a web element with its description"""
    action: Literal["click_element"] = Field(description="Click at absolute coordinates of a web element")
    element: str = Field(description="text description of the element")
    x: int = Field(description="The x coordinate, number of pixels from the left edge.")
    y: int = Field(description="The y coordinate, number of pixels from the top edge.")

class WriteElementAction(BaseModel):
    """Write content at absolute coordinates of a web element identified by its description, then press Enter."""
    action: Literal["write_element_abs"] = Field(description="Write content at absolute coordinates of a web page")
    content: str = Field(description="Content to write")
    element: str = Field(description="Text description of the element")
    x: int = Field(description="The x coordinate, number of pixels from the left edge.")
    y: int = Field(description="The y coordinate, number of pixels from the top edge.")

class ScrollAction(BaseModel):
    """Scroll action with no required element"""
    action: Literal["scroll"] = Field(description="Scroll the page or a specific element")
    direction: Literal["down", "up", "left", "right"] = Field(description="The direction to scroll in")

class GoBackAction(BaseModel):
    """Action to navigate back in browser history"""
    action: Literal["go_back"] = Field(description="Navigate to the previous page")

class RefreshAction(BaseModel):
    """Action to refresh the current page"""
    action: Literal["refresh"] = Field(description="Refresh the current page")

class GotoAction(BaseModel):
    """Action to go to a particular URL"""
    action: Literal["goto"] = Field(description="Goto a particular URL")
    url: str = Field(description="A url starting with http:// or https://")

class WaitAction(BaseModel):
    """Action to wait for a particular amount of time"""
    action: Literal["wait"] = Field(description="Wait for a particular amount of time")
    seconds: int = Field(default=2, ge=0, le=10, description="The number of seconds to wait")

class AnswerAction(BaseModel):
    """Return a final answer to the task. This is the last action to call in an episode."""
    action: Literal["answer"] = "answer"
    content: str = Field(description="The answer content")

ActionSpace = Union[
    ClickElementAction, WriteElementAction, ScrollAction, GoBackAction,
    RefreshAction, WaitAction, AnswerAction, GotoAction
]

class NavigationStep(BaseModel):
    note: str = Field(
        default="",
        description="Task-relevant information extracted from the previous observation. Keep empty if no new info.",
    )
    thought: str = Field(description="Reasoning about next steps (<4 lines)")
    action: ActionSpace = Field(description="Next action to take")

@dataclass
class AgentMemory:
    task: str
    screenshots: List[str] = None  # Base64 encoded screenshots
    actions: List[NavigationStep] = None
    current_url: str = ""
    step_count: int = 0
    
    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []
        if self.actions is None:
            self.actions = []


class Holo1Model:
    """Holo1 model for both localization and navigation tasks"""
    
    def __init__(self, model_repo: str = HF_MODEL_REPO, device: str = "auto"):
        self.model_repo = model_repo
        self.device = device
        self.model = None
        self.processor = None
        self._load_model()
    
    def _load_model(self):
        """Load the Holo1 model and processor"""
        logger.info(f"Loading model {self.model_repo}")
        
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_repo,
            torch_dtype="auto",
            device_map=self.device,
        )
        
        self.processor = AutoProcessor.from_pretrained(self.model_repo)
        logger.info("Model loaded successfully")
    
    def run_inference(self, messages: List[Dict[str, Any]], image: Any, max_new_tokens: int = 128) -> str:
        """Run inference on the model"""
        try:
            # Preparation for inference
            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.processor(
                text=[text],
                images=[image],
                padding=True,
                return_tensors="pt",
            )
            
            # Move to appropriate device
            if torch.backends.mps.is_available():
                inputs = inputs.to("mps")
            elif torch.cuda.is_available():
                inputs = inputs.to("cuda")
            
            generated_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
            generated_ids_trimmed = [
                out_ids[len(in_ids):] 
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            response = self.processor.batch_decode(
                generated_ids_trimmed, 
                skip_special_tokens=True, 
                clean_up_tokenization_spaces=False
            )[0]
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error in model inference: {e}")
            raise

class Holo1Localizer:
    """Holo1 Localization functionality"""
    
    def __init__(self, model: Holo1Model):
        self.model = model
    
    def get_localization_prompt(self, image: Any, instruction: str) -> List[Dict[str, Any]]:
        """Get localization prompt for finding UI elements"""
        guidelines = "Localize an element on the GUI image according to my instructions and output a click position as Click(x, y) with x num pixels from the left edge and y num pixels from the top edge."
        
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image,
                    },
                    {"type": "text", "text": f"{guidelines}\n{instruction}"},
                ],
            }
        ]
    
    def get_localization_prompt_structured(self, image: Any, instruction: str) -> List[Dict[str, Any]]:
        """Get structured localization prompt with JSON schema"""
        guidelines = "Localize an element on the GUI image according to my instructions and output a click position. You must output a valid JSON format."
        
        return [
            {
                "role": "system",
                "content": json.dumps(ClickAction.model_json_schema()),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image,
                    },
                    {"type": "text", "text": f"{guidelines}\n{instruction}"},
                ],
            },
        ]
    
    def localize_element(self, image: Any, element_description: str, use_structured: bool = True) -> Tuple[int, int]:
        """
        Localize UI element in image and return coordinates
        
        Args:
            image: PIL Image or image data
            element_description: Description of element to locate
            use_structured: Whether to use structured output
            
        Returns:
            Tuple of (x, y) coordinates
        """
        try:
            if use_structured:
                prompt = self.get_localization_prompt_structured(image, element_description)
            else:
                prompt = self.get_localization_prompt(image, element_description)
            
            response = self.model.run_inference(prompt, image)
            
            if use_structured:
                try:
                    # First, try to parse the response as valid JSON
                    action_data = json.loads(response)
                    return (action_data["x"], action_data["y"])
                except json.JSONDecodeError:
                    # If JSON parsing fails, fall back to regex to find coordinates
                    logger.warning(f"Could not parse JSON: '{response}'. Falling back to regex.")
                    match = re.search(r'"x":\s*(\d+),\s*"y":\s*(\d+)', response)
                    if match:
                        x = int(match.group(1))
                        y = int(match.group(2))
                        return (x, y)
                    else:
                        raise ValueError(f"Could not extract coordinates from malformed response: {response}")
            else:
                # Parse Click(x, y) format
                if "Click(" in response:
                    coords_str = response.split("Click(")[1].split(")")[0]
                    x, y = map(int, coords_str.split(","))
                    return (x, y)
                else:
                    raise ValueError(f"Invalid coordinate format: {response}")
                    
        except Exception as e:
            logger.error(f"Error localizing element '{element_description}': {e}")
            raise

class Holo1Navigator:
    """Holo1 Navigation functionality"""
    
    SYSTEM_PROMPT: str = """Imagine you are a robot browsing the web, just like humans. Now you need to complete a task.
    In each iteration, you will receive an Observation that includes the last  screenshots of a web browser and the current memory of the agent.
    You have also information about the step that the agent is trying to achieve to solve the task.
    Carefully analyze the visual information to identify what to do, then follow the guidelines to choose the following action.
    You should detail your thought (i.e. reasoning steps) before taking the action.
    Also detail in the notes field of the action the extracted information relevant to solve the task.
    Once you have enough information in the notes to answer the task, return an answer action with the detailed answer in the notes field.
    This will be evaluated by an evaluator and should match all the criteria or requirements of the task.

    Guidelines:
    - store in the notes all the relevant information to solve the task that fulfill the task criteria. Be precise
    - Use both the task and the step information to decide what to do
    - if you want to write in a text field and the text field already has text, designate the text field by the text it contains and its type
    - If there is a cookies notice, always accept all the cookies first
    - The observation is the screenshot of the current page and the memory of the agent.
    - If you see relevant information on the screenshot to answer the task, add it to the notes field of the action.
    - If there is no relevant information on the screenshot to answer the task, add an empty string to the notes field of the action.
    - If you see buttons that allow to navigate directly to relevant information, like jump to ... or go to ... , use them to navigate faster.
    - In the answer action, give as many details a possible relevant to answering the task.
    - if you want to write, don't click before. Directly use the write action
    - to write, identify the web element which is type and the text it already contains
    - If you want to use a search bar, directly write text in the search bar
    - Don't scroll too much. Don't scroll if the number of scrolls is greater than 3
    - Don't scroll if you are at the end of the webpage
    - Only refresh if you identify a rate limit problem
    - If you are looking for a single flights, click on round-trip to select 'one way'
    - Never try to login, enter email or password. If there is a need to login, then go back.
    - If you are facing a captcha on a website, try to solve it.

    - if you have enough information in the screenshot and in the notes to answer the task, return an answer action with the detailed answer in the notes field
    - The current date is {timestamp}.

    # <output_json_format>
    # ```json
    # {output_format}
    # ```
    # </output_json_format>

    """ 
    
    def __init__(self, model: Holo1Model):
        self.model = model
    
    def get_navigation_prompt(self, task: str, image: Any, memory: AgentMemory) -> List[Dict[str, Any]]:
        """Get navigation prompt for deciding next actions"""
        system_prompt = self.SYSTEM_PROMPT.format(
            output_format=NavigationStep.model_json_schema(),
            timestamp="2025-06-18 14:16:03",
        )
        
        # Build history context
        history_context = self._build_history_context(memory)
        
        return [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": system_prompt},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<task>\n{task}\n</task>\n"},
                    {"type": "text", "text": f"<observation step={memory.step_count}>\n"},
                    {"type": "text", "text": f"<history>\n{history_context}\n</history>\n"},
                    {"type": "text", "text": "<screenshot>\n"},
                    {
                        "type": "image",
                        "image": image,
                    },
                    {"type": "text", "text": "\n</screenshot>\n"},
                    {"type": "text", "text": "\n</observation>\n"},
                ],
            },
        ]
    
    def decide_next_action(self, task: str, image: Any, memory: AgentMemory) -> NavigationStep:
        """
        Decide next action based on current state and memory
        
        Args:
            task: The task description
            image: Current browser screenshot
            memory: Agent's memory containing history
            
        Returns:
            NavigationStep with next action to execute
        """
        try:
            prompt = self.get_navigation_prompt(task, image, memory)
            response = self.model.run_inference(prompt, image, max_new_tokens=256)
            
            # Parse JSON response
            action_data = json.loads(response)
            return NavigationStep(**action_data)
            
        except Exception as e:
            logger.error(f"Error deciding next action: {e}")
            # Return a safe fallback action
            return NavigationStep(
                note="Error occurred during decision making",
                thought="An error occurred, waiting before retrying",
                action=WaitAction(seconds=2)
            )
    
    def _build_history_context(self, memory: AgentMemory) -> str:
        """Build context string from agent memory"""
        if not memory.actions:
            return "No previous actions"
        
        context_parts = [] 
        
        # Include last 3 actions for context
        for i, step in enumerate(memory.actions[-3:]):
            context_parts.append(f"Step {len(memory.actions) - 3 + i + 1}:")
            context_parts.append(f"Thought: {step.thought}")
            context_parts.append(f"Action: {step.action.action}")
            if step.note:
                context_parts.append(f"Notes: {step.note}")
            context_parts.append("---")
        
        return "\n".join(context_parts)

class WebNavigationAgent:
    """Main agent that coordinates browser control with Holo1 models"""
    
    def __init__(self, model_repo: str = HF_MODEL_REPO, device: str = "auto"):
        # Initialize Holo1 model
        self.model = Holo1Model(model_repo, device)
        
        # Initialize localizer and navigator
        self.localizer = Holo1Localizer(self.model)
        self.navigator = Holo1Navigator(self.model)
        
        self.driver = None
        self.memory = None
        
    def setup_browser(self, headless: bool = False, window_size: Tuple[int, int] = (1200, 1200)):
        """Setup Chrome browser with appropriate options"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def cleanup(self):
        """Cleanup browser resources"""
        if self.driver:
            self.driver.quit()
    
    def take_screenshot(self) -> Tuple[str, Image.Image]:
        """Take screenshot and return as base64 string and PIL Image"""
        screenshot_png = self.driver.get_screenshot_as_png()
        screenshot_b64 = base64.b64encode(screenshot_png).decode('utf-8')
        screenshot_image = Image.open(BytesIO(screenshot_png))
        return screenshot_b64, screenshot_image
    
    def execute_action(self, step: NavigationStep, screenshot_image: Image.Image):
        """Execute a navigation step using Selenium"""
        action = step.action
        logger.info(f"Executing action: {action.action}")
        
        if step.thought:
            logger.info(f"Thought: {step.thought}")
        
        try:
            if action.action == "click_element":
                # Use localizer to find coordinates
                x, y = self.localizer.localize_element(screenshot_image, action.element)
                
                # Click at coordinates
                ActionChains(self.driver).move_by_offset(x, y).click().perform()
                ActionChains(self.driver).move_by_offset(-x, -y).perform()  # Reset mouse position
                
            elif action.action == "write_element_abs":
                # Use localizer to find coordinates
                x, y = self.localizer.localize_element(screenshot_image, action.element)
                
                # Click and then type
                ActionChains(self.driver).move_by_offset(x, y).click().perform()
                ActionChains(self.driver).send_keys(action.content).perform()
                ActionChains(self.driver).move_by_offset(-x, -y).perform()
                
            elif action.action == "scroll":
                if action.direction == "down":
                    self.driver.execute_script("window.scrollBy(0, 500);")
                elif action.direction == "up":
                    self.driver.execute_script("window.scrollBy(0, -500);")
                elif action.direction == "right":
                    self.driver.execute_script("window.scrollBy(500, 0);")
                elif action.direction == "left":
                    self.driver.execute_script("window.scrollBy(-500, 0);")
                    
            elif action.action == "wait":
                asyncio.sleep(action.seconds)
                
            elif action.action == "goto":
                self.driver.get(action.url)
                
            elif action.action == "go_back":
                self.driver.back()
                
            elif action.action == "refresh":
                self.driver.refresh()
                
            # Update memory with current URL
            self.memory.current_url = self.driver.current_url
            
            # Wait a bit after action
            asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error executing action {action.action}: {e}")
            raise
    
    def run_task(self, task: str, starting_url: str = "https://www.google.com", max_steps: int = 30) -> str:
        """
        Run a task using the web navigation agent
        
        Args:
            task: Description of task to complete
            starting_url: Initial URL to navigate to
            max_steps: Maximum number of steps before forcing completion
            
        Returns:
            Final answer or result
        """
        self.memory = AgentMemory(task=task)
        
        logger.info(f"Starting task: {task}")
        
        # Navigate to starting page
        self.driver.get(starting_url)
        self.memory.current_url = starting_url
        
        for step in range(max_steps):
            logger.info(f"Step {step + 1}/{max_steps}")
            self.memory.step_count = step + 1
            
            # Take screenshot of current state
            screenshot_b64, screenshot_image = self.take_screenshot()
            self.memory.screenshots.append(screenshot_b64)
            
            # Decide next action using navigator
            try:
                navigation_step = self.navigator.decide_next_action(self.memory.task, screenshot_image, self.memory)
                
                # Check if task is complete
                if navigation_step.action.action == "answer":
                    logger.info(f"Task completed with answer: {navigation_step.action.content}")
                    return navigation_step.action.content
                
                # Execute the action
                self.execute_action(navigation_step, screenshot_image)
                
                # Store step in memory
                self.memory.actions.append(navigation_step)
                    
            except Exception as e:
                logger.error(f"Error in step {step + 1}: {e}")
                # Continue to next step
                continue
        
        # If we reach max steps, force an answer
        logger.warning("Reached maximum steps, forcing completion")
        return "Task could not be completed within the step limit"


# Example usage
async def run():
    """Example usage of the web navigation agent"""
    
    # Create agent
    print()
    agent = WebNavigationAgent()
    
    try:
        # Setup browser
        agent.setup_browser(headless=False)  # Set to True for headless mode
        
        # Run a task
        task = "Search for 'artificial intelligence news' on Google and find the title of the first news article"
        result = agent.run_task(task, max_steps=15)
        
        print(f"Task result: {result}")
        
    finally:
        # Always cleanup
        agent.cleanup()


# if __name__ == "__main__":
#     print("\033[92m starting the program \033[0m")
#     asyncio.run(main())


