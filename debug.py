#!/usr/bin/env python3
"""
Debug version of the Holo1 web browsing agent integration.
This version includes better error handling and debugging information.
"""

import json
import os
import traceback
from typing import Any, Literal
from transformers import AutoModelForImageTextToText, AutoProcessor
from PIL import Image
import sys

# Import your modules
try:
    from navigation import get_navigation_prompt, NavigationStep, ActionSpace
    from localization import get_localization_prompt_structured_output, ClickAction
    print("✓ Successfully imported navigation and localization modules")
except ImportError as e:
    print(f"✗ Failed to import modules: {e}")
    sys.exit(1)

class DebugWebBrowsingAgent:
    """Debug version of the WebBrowsingAgent with enhanced logging."""
    
    def __init__(self, model_name: str = "Hcompany/Holo1-3B"):
        """Initialize the agent with Holo1 model."""
        print("Loading Holo1 model...")
        try:
            self.model = AutoModelForImageTextToText.from_pretrained(
                model_name,
                torch_dtype="auto",
                device_map="auto",
            )
            self.processor = AutoProcessor.from_pretrained(model_name)
            print("Model loaded successfully!")
        except Exception as e:
            print(f"Failed to load model: {e}")
            raise
        
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
        
    def run_inference(self, messages, image=None, max_tokens=512):
        """Run inference with better error handling."""
        try:
            # Preparation for inference
            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            
            # Debug: Print the first part of the text
            print(f"🔍 Input text preview: {text[:200]}...")
            
            inputs = self.processor(
                text=[text],
                images=[image] if image else None,
                padding=True,
                return_tensors="pt",
            )
            
            # Move to device
            device = next(self.model.parameters()).device
            inputs = inputs.to(device)
            
            print(f"🔍 Generating response with max_tokens={max_tokens}")
            generated_ids = self.model.generate(**inputs, max_new_tokens=max_tokens)
            generated_ids_trimmed = [
                out_ids[len(in_ids):] 
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            response = self.processor.batch_decode(
                generated_ids_trimmed, 
                skip_special_tokens=True, 
                clean_up_tokenization_spaces=False
            )[0]
            
            print(f"🔍 Raw model response: {response}")
            return response.strip()
            
        except Exception as e:
            print(f"❌ Inference error: {e}")
            traceback.print_exc()
            return ""
    
    def navigate(self, task: str, screenshot: Image.Image) -> NavigationStep:
        """Navigate with enhanced debugging."""
        print(f"\n🧭 Navigation Step {self.current_step}")
        print(f"   Task: {task}")
        print(f"   Screenshot size: {screenshot.size}")
        
        # Create navigation prompt
        messages = get_navigation_prompt(task, screenshot, self.current_step)
        
        # Add memory context if available
        if self.memory:
            memory_context = "\n".join([
                f"Step {i+1}: {step}" for i, step in enumerate(self.memory[-3:])  # Last 3 steps
            ])
            print(f"   Memory context: {len(self.memory)} previous steps")
        
        # Add current notes if available
        if self.task_notes:
            print(f"   Current notes: {self.task_notes[:100]}...")
        
        # Get response from model
        response = self.run_inference(messages, screenshot, max_tokens=1024)
        
        if not response:
            print("❌ Empty response from model")
            return NavigationStep(
                note="",
                thought="No response from model, waiting",
                action={"action": "wait", "seconds": 2}
            )
        
        try:
            # Parse JSON response
            json_content = response
            if response.startswith("```json"):
                json_content = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                json_content = response.split("```")[1].split("```")[0].strip()
            
            print(f"🔍 Parsing JSON: {json_content[:200]}...")
            
            step_data = json.loads(json_content)
            print(f"✓ Successfully parsed JSON: {step_data}")
            
            navigation_step = NavigationStep(**step_data)
            print(f"✓ Successfully created NavigationStep")
            print(f"   Action type: {navigation_step.action}")
            
            # Update task notes if new information is available
            if navigation_step.note and navigation_step.note.strip():
                self.task_notes += f"\nStep {self.current_step}: {navigation_step.note}"
            
            return navigation_step
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            print(f"   Raw response: {response}")
            return NavigationStep(
                note="",
                thought="Failed to parse JSON response, waiting before retry",
                action={"action": "wait", "seconds": 2}
            )
        except Exception as e:
            print(f"❌ Error creating NavigationStep: {e}")
            print(f"   Step data: {step_data}")
            traceback.print_exc()
            return NavigationStep(
                note="",
                thought="Failed to create navigation step, waiting before retry",
                action={"action": "wait", "seconds": 2}
            )
    
    def execute_step(self, task: str, screenshot: Image.Image, browser_controller):
        """Execute step with enhanced debugging."""
        print(f"\n🎯 Executing Step {self.current_step}")
        
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
        print(f"💭 Thought: {nav_step.thought}")
        print(f"🎬 Action: {nav_step.action}")
        
        # Execute the action
        try:
            action_result = self._execute_action(nav_step.action, screenshot, browser_controller)
            print(f"✅ Action result: {action_result}")
            
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
            print(f"❌ Error executing action: {e}")
            traceback.print_exc()
            return {
                "status": "error",
                "message": str(e),
                "step": self.current_step
            }
    
    def _execute_action(self, action: ActionSpace, screenshot: Image.Image, browser_controller) -> str:
        """Execute action with detailed logging."""
        # Handle both dict and Pydantic model formats
        if hasattr(action, 'action'):
            # Pydantic model format
            action_type = action.action
            print(f"🔧 Executing Pydantic action: {action_type}")
        else:
            # Dict format
            action_type = action.get("action")
            print(f"🔧 Executing dict action: {action_type}")
        
        try:
            if action_type == "click_element":
                # Direct click with provided coordinates
                if hasattr(action, 'x'):
                    x, y = action.x, action.y
                    element = getattr(action, 'element', 'Unknown element')
                else:
                    x, y = action.get("x"), action.get("y")
                    element = action.get("element", "Unknown element")
                
                print(f"🖱️  Clicking on '{element}' at ({x}, {y})")
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
                
                print(f"⌨️  Writing '{content}' in '{element}' at ({x}, {y})")
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
                
                print(f"📜 Scrolling {direction}")
                browser_controller.scroll(direction)
                return f"Scrolled {direction}"
                
            elif action_type == "wait":
                if hasattr(action, 'seconds'):
                    seconds = action.seconds
                else:
                    seconds = action.get("seconds", 2)
                
                print(f"⏳ Waiting {seconds} seconds")
                import time
                time.sleep(seconds)
                return f"Waited {seconds} seconds"
                
            elif action_type == "answer":
                if hasattr(action, 'content'):
                    answer = action.content
                else:
                    answer = action.get("content", "Task completed")
                
                print(f"✅ Final answer: {answer}")
                return f"Task completed: {answer}"
                
            else:
                print(f"❓ Unknown action type: {action_type}")
                return f"Unknown action type: {action_type}"
                
        except Exception as e:
            print(f"❌ Error in _execute_action: {e}")
            traceback.print_exc()
            raise


def main():
    """Main function to test the debug agent."""
    print("🚀 Starting Debug Web Browsing Agent")
    
    try:
        # Initialize the debug agent
        agent = DebugWebBrowsingAgent()
        
        # Import playwright controller
        from playwright_controller import PlaywrightBrowserController
        
        # Initialize browser
        browser = PlaywrightBrowserController(
            headless=False,
            viewport_size={"width": 1280, "height": 720}
        )
        browser.initialize()
        
        # Navigate to Amazon
        print("🌐 Navigating to Amazon...")
        browser.goto("https://amazon.com")
        browser.wait_for_page_load()
        browser.accept_cookies()
        
        # Get screenshot
        screenshot = browser.get_screenshot()
        print(f"📸 Screenshot captured: {screenshot.size}")
        
        # Test a single step
        print("🧪 Testing single step execution...")
        result = agent.execute_step(
            "Find the search box and search for 'iPhone 15'",
            screenshot,
            browser
        )
        
        print(f"\n🎯 Step Result:")
        print(f"   Status: {result['status']}")
        print(f"   Message: {result.get('message', 'N/A')}")
        
        # Clean up
        browser.cleanup()
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        traceback.print_exc()
    finally:
        print("🧹 Cleaning up...")


if __name__ == "__main__":
    main()