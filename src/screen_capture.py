"""
Screen capture module for AI Game Partner.
Handles taking and managing screenshots.
"""

import time
import threading
import queue
import os
from datetime import datetime
from dataclasses import dataclass
import pyautogui
from PIL import Image
import tempfile
import logging
import shutil
from typing import List, Optional
import mss
import mss.tools

logger = logging.getLogger(__name__)

@dataclass
class ScreenshotData:
    """Represents a captured screenshot with metadata."""
    image_path: str
    timestamp: float
    timestamp_str: str

class Screenshot:
    def __init__(self, image_path: str, timestamp: float):
        self.image_path = image_path
        self.timestamp = timestamp

class ScreenCapture:
    def __init__(self, config):
        """
        Initialize the screen capture system.
        
        Args:
            config: Configuration object containing capture settings
        """
        self.config = config
        self.capture_thread = None
        self.running = False
        self.screenshots = []
        self.max_screenshots = int(config['ScreenCapture']['max_screenshots'])
        self.capture_interval = float(config['ScreenCapture']['capture_interval'])
        self.screenshot_dir = os.path.join(tempfile.gettempdir(), 'ai_game_partner_screenshots')
        
        # Clean up and recreate the screenshot directory
        if os.path.exists(self.screenshot_dir):
            shutil.rmtree(self.screenshot_dir)
        os.makedirs(self.screenshot_dir)
        
        logger.info(f"Using static screenshot directory: {self.screenshot_dir}")
        
    def start(self):
        """Start the screen capture thread."""
        if self.running:
            return
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        logger.info("Screen capture started")
        
    def stop(self):
        """Stop the screen capture thread."""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join()
            self.capture_thread = None
        logger.info("Screen capture stopped")
        
    def cleanup(self):
        """Clean up the screenshot directory."""
        try:
            if os.path.exists(self.screenshot_dir):
                shutil.rmtree(self.screenshot_dir)
                logger.info("Cleaned up screenshot directory")
        except Exception as e:
            logger.error(f"Error cleaning up screenshot directory: {e}")
            
    def _capture_screen(self) -> Optional[Image.Image]:
        """Take a screenshot and return it as a PIL Image."""
        try:
            # Create a new mss instance for this thread
            with mss.mss() as sct:
                # Get the primary monitor
                monitor = sct.monitors[1]  # 0 is all monitors, 1 is primary
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                return img
        except Exception as e:
            logger.error(f"Error capturing screen: {e}")
            return None
            
    def _capture_loop(self):
        """Main capture loop running in a background thread."""
        logger.info("Starting screen capture loop...")
        while self.running:
            try:
                # Take screenshot
                img = self._capture_screen()
                if img:
                    # Save to temp file
                    timestamp = time.time()
                    filename = f"screenshot_{int(timestamp)}.png"
                    filepath = os.path.join(self.screenshot_dir, filename)
                    img.save(filepath)
                    
                    # Add to screenshots list
                    self.screenshots.append(Screenshot(filepath, timestamp))
                    logger.info(f"Screenshot saved: {filename}")
                    
                    # Remove old screenshots if we have too many
                    while len(self.screenshots) > self.max_screenshots:
                        old_screenshot = self.screenshots.pop(0)
                        try:
                            os.remove(old_screenshot.image_path)
                            logger.debug(f"Removed old screenshot: {os.path.basename(old_screenshot.image_path)}")
                        except Exception as e:
                            logger.error(f"Error removing old screenshot: {e}")
                else:
                    logger.warning("Failed to capture screenshot")
                
                # Sleep for the capture interval
                time.sleep(self.capture_interval)
                
            except Exception as e:
                logger.error(f"Error in capture loop: {e}")
                time.sleep(1)  # Sleep a bit before retrying
                
    def get_recent_screenshots(self, count: int = 3) -> List[Screenshot]:
        """Get the most recent screenshots."""
        screenshots = self.screenshots[-count:] if self.screenshots else []
        logger.info(f"Retrieved {len(screenshots)} screenshots (requested {count})")
        return screenshots
        
    def get_screenshot_count(self) -> int:
        """Get the current number of screenshots."""
        return len(self.screenshots) 