import json
import time
from typing import Any, Dict, List, Optional, Union
from PIL import Image
import io
import base64
from transformers import AutoModelForImageTextToText, AutoProcessor
import torch
from pydantic import BaseModel, Field
from typing import Literal

# Import your existing modules
from navigation import get_navigation_prompt, NavigationStep, ActionSpace
from localization import get_localization_prompt_structured_output, ClickAction

class WebBrowsingAgent:
    """
    A powerful web browsing agent that combines navigation and localization capabilities
    using the Holo1 model, similar to Surfer-H architecture.
    """
    
    def __init__(self, model_name: str = "Hcompany/Holo1-7B"):
        """Initialize the agent with Holo1 model."""
        print("Loading Holo1 model...")
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
        )
        self.processor = AutoProcessor.from_pretrained(model_name)
        print("Model loaded successfully!")
        
        # Agent state
        self.current_step = 1
        self.memory = []
        self.task_notes = ""
        self.max_steps = 50
        self.scroll_count = 0
        
    def reset(self):
        """Reset agent state for a new task."""
        self.current_step = 1
        self.memory = []
        self.task_notes = ""
        self.scroll_count = 0
        
    def run_inference(self, messages: List[Dict[str, Any]], image: Optional[Image.Image] = None, max_tokens: int = 512) -> str:
        """Run inference with the Holo1 model."""
        try:
            # Prepare the text input
            text = self.processor.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True
            )
            
            # Process inputs
            inputs = self.processor(
                text=[text],
                images=[image] if image else None,
                padding=True,
                return_tensors="pt",
            )
            
            # Move to device
            device = next(self.model.parameters()).device
            inputs = inputs.to(device)
            
            # Generate response
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs, 
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=self.processor.tokenizer.eos_token_id
                )
            
            # Decode response
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
            print(f"Inference error: {e}")
            return ""
    
    def navigate(self, task: str, screenshot: Image.Image) -> NavigationStep:
        """
        Perform navigation reasoning given a task and screenshot.
        """
        # Create navigation prompt
        messages = get_navigation_prompt(task, screenshot, self.current_step)
        
        # Add memory context if available
        if self.memory:
            memory_context = "\n".join([
                f"Step {i+1}: {step}" for i, step in enumerate(self.memory[-5:])  # Last 5 steps
            ])
            messages[1]["content"].insert(-1, {
                "type": "text", 
                "text": f"<memory>\n{memory_context}\n</memory>\n"
            })
        
        # Add current notes if available
        if self.task_notes:
            messages[1]["content"].insert(-1, {
                "type": "text",
                "text": f"<current_notes>\n{self.task_notes}\n</current_notes>\n"
            })
        
        # Get response from model
        response = self.run_inference(messages, screenshot, max_tokens=1024)
        
        try:
            # Parse JSON response
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()
            
            step_data = json.loads(response)
            navigation_step = NavigationStep(**step_data)
            
            # Update task notes if new information is available
            if navigation_step.note and navigation_step.note.strip():
                self.task_notes += f"\nStep {self.current_step}: {navigation_step.note}"
            
            return navigation_step
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error parsing navigation response: {e}")
            print(f"Raw response: {response}")
            # Return a default wait action
            return NavigationStep(
                note="",
                thought="Failed to parse response, waiting before retry",
                action={"action": "wait", "seconds": 2}
            )
    
    def localize_element(self, screenshot: Image.Image, instruction: str) -> Optional[ClickAction]:
        """
        Localize an element on the screen given an instruction.
        """
        messages = get_localization_prompt_structured_output(screenshot, instruction)
        
        response = self.run_inference(messages, screenshot, max_tokens=256)
        
        try:
            # Parse JSON response
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()
                
            click_data = json.loads(response)
            return ClickAction(**click_data)
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error parsing localization response: {e}")
            print(f"Raw response: {response}")
            return None
    
    def execute_step(self, task: str, screenshot: Image.Image, browser_controller) -> Dict[str, Any]:
        """
        Execute one step of the browsing task.
        
        Args:
            task: The task description
            screenshot: Current screenshot of the browser
            browser_controller: Object that can execute browser actions
            
        Returns:
            Dictionary with step results
        """
        if self.current_step > self.max_steps:
            return {
                "status": "max_steps_reached",
                "message": "Maximum steps reached",
                "final_answer": self.task_notes
            }
        
        # Get navigation decision
        nav_step = self.navigate(task, screenshot)
        
        # Log the step
        step_log = f"Step {self.current_step}: {nav_step.thought}"
        self.memory.append(step_log)
        print(f"\n{step_log}")
        print(f"Action: {nav_step.action}")
        
        # Execute the action
        try:
            action_result = self._execute_action(nav_step.action, screenshot, browser_controller)
            
            # Update step counter
            self.current_step += 1
            
            # Check if this is the final answer
            action_type = nav_step.action.action if hasattr(nav_step.action, 'action') else nav_step.action.get("action")
            if action_type == "answer":
                final_content = nav_step.action.content if hasattr(nav_step.action, 'content') else nav_step.action.get("content", self.task_notes)
                return {
                    "status": "completed",
                    "message": "Task completed successfully",
                    "final_answer": final_content,
                    "total_steps": self.current_step - 1
                }
            
            return {
                "status": "continuing",
                "step": self.current_step - 1,
                "action": nav_step.action,
                "result": action_result,
                "notes": nav_step.note
            }
            
        except Exception as e:
            print(f"Error executing action: {e}")
            return {
                "status": "error",
                "message": str(e),
                "step": self.current_step
            }
    
    def _execute_action(self, action: ActionSpace, screenshot: Image.Image, browser_controller) -> str:
        """Execute a specific action using the browser controller."""
        # Handle both dict and Pydantic model formats
        if hasattr(action, 'action'):
            # Pydantic model format
            action_type = action.action
        else:
            # Dict format
            action_type = action.get("action")
        
        if action_type == "click_element":
            # Direct click with provided coordinates
            if hasattr(action, 'x'):
                x, y = action.x, action.y
                element = getattr(action, 'element', 'Unknown element')
            else:
                x, y = action.get("x"), action.get("y")
                element = action.get("element", "Unknown element")
            browser_controller.click(x, y)
            return f"Clicked on '{element}' at coordinates ({x}, {y})"
            
        elif action_type == "write_element_abs":
            # Write text at specified coordinates
            if hasattr(action, 'x'):
                x, y = action.x, action.y
                content = action.content
                element = getattr(action, 'element', 'Unknown element')
            else:
                x, y = action.get("x"), action.get("y")
                content = action.get("content", "")
                element = action.get("element", "Unknown element")
            browser_controller.click(x, y)  # Focus the element first
            time.sleep(0.5)
            browser_controller.type_text(content)
            return f"Wrote '{content}' in '{element}' at coordinates ({x}, {y})"
            
        elif action_type == "scroll":
            if hasattr(action, 'direction'):
                direction = action.direction
            else:
                direction = action.get("direction", "down")
            self.scroll_count += 1
            if self.scroll_count > 3:
                return "Scroll limit reached, skipping scroll action"
            browser_controller.scroll(direction)
            return f"Scrolled {direction}"
            
        elif action_type == "go_back":
            browser_controller.go_back()
            return "Navigated back"
            
        elif action_type == "refresh":
            browser_controller.refresh()
            return "Refreshed page"
            
        elif action_type == "goto":
            if hasattr(action, 'url'):
                url = action.url
            else:
                url = action.get("url", "")
            browser_controller.goto(url)
            return f"Navigated to {url}"
            
        elif action_type == "wait":
            if hasattr(action, 'seconds'):
                seconds = action.seconds
            else:
                seconds = action.get("seconds", 2)
            time.sleep(seconds)
            return f"Waited {seconds} seconds"
            
        elif action_type == "restart":
            self.reset()
            browser_controller.restart()
            return "Restarted task"
            
        elif action_type == "answer":
            # This is handled in execute_step
            if hasattr(action, 'content'):
                return f"Task completed: {action.content}"
            else:
                return "Task completed"
            
        else:
            return f"Unknown action type: {action_type}"
    
    def run_task(self, task: str, browser_controller, max_steps: Optional[int] = None) -> Dict[str, Any]:
        """
        Run a complete browsing task.
        
        Args:
            task: Task description
            browser_controller: Browser controller object
            max_steps: Maximum number of steps (optional)
            
        Returns:
            Final result dictionary
        """
        if max_steps:
            self.max_steps = max_steps
            
        self.reset()
        print(f"Starting task: {task}")
        
        while self.current_step <= self.max_steps:
            # Get current screenshot
            screenshot = browser_controller.get_screenshot()
            
            # Execute one step
            result = self.execute_step(task, screenshot, browser_controller)
            
            if result["status"] in ["completed", "error", "max_steps_reached"]:
                return result
                
            # Small delay between steps
            time.sleep(1)
        
        return {
            "status": "max_steps_reached",
            "message": "Task did not complete within maximum steps",
            "final_answer": self.task_notes,
            "total_steps": self.current_step - 1
        }
    
    def interactive_mode(self, browser_controller):
        """
        Run the agent in interactive mode for testing and debugging.
        """
        print("=== Web Browsing Agent - Interactive Mode ===")
        print("Commands:")
        print("  task <description> - Start a new task")
        print("  step - Execute one step of current task")
        print("  screenshot - Show current screenshot info")
        print("  reset - Reset agent state")
        print("  quit - Exit interactive mode")
        print()
        
        current_task = None
        
        while True:
            try:
                command = input("> ").strip().lower()
                
                if command.startswith("task "):
                    current_task = command[5:]
                    self.reset()
                    print(f"Task set: {current_task}")
                    
                elif command == "step":
                    if not current_task:
                        print("No task set. Use 'task <description>' first.")
                        continue
                        
                    screenshot = browser_controller.get_screenshot()
                    result = self.execute_step(current_task, screenshot, browser_controller)
                    print(f"Step result: {result}")
                    
                elif command == "screenshot":
                    screenshot = browser_controller.get_screenshot()
                    print(f"Screenshot size: {screenshot.size}")
                    
                elif command == "reset":
                    self.reset()
                    print("Agent state reset")
                    
                elif command == "quit":
                    print("Exiting interactive mode")
                    break
                    
                else:
                    print("Unknown command")
                    
            except KeyboardInterrupt:
                print("\nExiting interactive mode")
                break
            except Exception as e:
                print(f"Error: {e}")


# Example browser controller interface (you'll need to implement this)
class BrowserController:
    """
    Interface for browser control operations.
    You'll need to implement this based on your browser automation setup
    (e.g., Selenium, Playwright, etc.)
    """
    
    def get_screenshot(self) -> Image.Image:
        """Get current screenshot as PIL Image."""
        raise NotImplementedError
        
    def click(self, x: int, y: int):
        """Click at coordinates (x, y)."""
        raise NotImplementedError
        
    def type_text(self, text: str):
        """Type text at current cursor position."""
        raise NotImplementedError
        
    def scroll(self, direction: str):
        """Scroll in given direction ('up', 'down', 'left', 'right')."""
        raise NotImplementedError
        
    def go_back(self):
        """Navigate back in browser history."""
        raise NotImplementedError
        
    def refresh(self):
        """Refresh current page."""
        raise NotImplementedError
        
    def goto(self, url: str):
        """Navigate to URL."""
        raise NotImplementedError
        
    def restart(self):
        """Restart/reset browser state."""
        raise NotImplementedError


# Example usage
if __name__ == "__main__":
    # Initialize the agent
    agent = WebBrowsingAgent()
    
    # You'll need to implement your browser controller
    # browser = YourBrowserController()
    
    # Example task execution
    # result = agent.run_task(
    #     "Find the price of iPhone 15 on Amazon", 
    #     browser,
    #     max_steps=20
    # )
    # print(f"Task result: {result}")
    
    # Or run in interactive mode for testing
    # agent.interactive_mode(browser)
    
    print("Web Browsing Agent initialized successfully!")
    print("Implement your BrowserController class and start using the agent.")