"""
Main module for AI Game Partner.
Handles the core application loop and component coordination.
"""

import time
import threading
import queue
import logging
import signal
import os
import sys
from datetime import datetime
from typing import Optional
import configparser
import tkinter as tk
from tkinter import simpledialog
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from screen_capture import ScreenCapture, Screenshot
from overlay import GameOverlay
from ai_client import AIClient

# Set up logging
LOG_FILE = 'game_partner.log'

# Remove existing log file if it exists
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

logging.basicConfig(
    level=logging.INFO,  # Change to INFO level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler()  # Keep console output as well
    ]
)

# Set more specific log levels for verbose modules
logging.getLogger('anthropic').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info("Starting new session...")

class GamePartner:
    def __init__(self, config: configparser.ConfigParser):
        """Initialize the AI Game Partner application."""
        self.config = config
        
        # Initialize components
        self.screen_capture = ScreenCapture(config)
        self.ai_client = AIClient(config)
        self.overlay = GameOverlay(config)
        
        # Setup message queue
        self.message_queue = queue.Queue()
        self.ui_update_queue = queue.Queue()
        
        # Track game state
        self.current_game = None
        self.last_analysis_time = 0
        self.analysis_cooldown = max(float(config['AI']['cooldown_seconds']), 5.0)  # Minimum 5 second cooldown
        self.initial_delay = 2.0  # Reduced initial delay to 2 seconds
        
        # Setup hotkeys
        self.setup_hotkeys()
        
        # Start background threads
        self.running = True
        self.analysis_thread = threading.Thread(target=self._analysis_loop)
        self.analysis_thread.daemon = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Setup force quit flag
        self.force_quit = False
        
        logger.info("AI Game Partner initialized")
        
    def _signal_handler(self, signum, frame):
        """Handle system signals for clean shutdown."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        if not self.force_quit:
            self.force_quit = True
            self.overlay.after(0, self.shutdown)
        else:
            logger.warning("Force quitting...")
            os._exit(1)
        
    def setup_hotkeys(self):
        """Setup global hotkeys for the application."""
        # Track currently pressed keys
        self.pressed_keys = set()
        
        def on_press(key):
            try:
                # Add the key to pressed keys
                self.pressed_keys.add(key)
                
                # Check for our hotkey combinations
                if (keyboard.Key.ctrl_l in self.pressed_keys and 
                    keyboard.Key.shift in self.pressed_keys):
                    if key == keyboard.Key.end:
                        logger.info("Ctrl+Shift+End pressed - toggling visibility")
                        self.ui_update_queue.put(lambda: self.overlay.toggle_visibility())
                    elif key == keyboard.Key.home:
                        logger.info("Ctrl+Shift+Home pressed - cycling position")
                        self.ui_update_queue.put(lambda: self.overlay.cycle_position())
                    elif key == keyboard.Key.enter:
                        logger.info("Ctrl+Shift+Enter pressed - showing input")
                        self.ui_update_queue.put(lambda: self.overlay.show_input())
            except Exception as e:
                logger.error(f"Error handling key press: {e}")
                
        def on_release(key):
            try:
                # Remove the key from pressed keys
                self.pressed_keys.discard(key)
            except Exception as e:
                logger.error(f"Error handling key release: {e}")
                
        # Start the hotkey listener
        logger.info("Setting up hotkey listener...")
        try:
            self.hotkey_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release
            )
            self.hotkey_listener.start()
            logger.info("Hotkey listener started")
        except Exception as e:
            logger.error(f"Error setting up hotkey listener: {e}")
            raise
        
    def _process_ui_updates(self):
        """Process any pending UI updates in the main thread."""
        try:
            while True:
                try:
                    update = self.ui_update_queue.get_nowait()
                    if callable(update):
                        update()
                    else:
                        logger.warning(f"Non-callable update received: {update}")
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error processing UI updates: {e}")
            
    def _analysis_loop(self):
        """Background thread for analyzing game state and processing messages."""
        # Wait for initial delay to collect screenshots
        logger.info(f"Waiting {self.initial_delay} seconds before starting analysis...")
        time.sleep(self.initial_delay)
        logger.info("Starting analysis loop...")
        
        while self.running:
            try:
                # Check for new messages
                try:
                    message = self.message_queue.get_nowait()
                    logger.info("Processing user message...")
                    self._process_message(message)
                except queue.Empty:
                    pass
                    
                # Auto-analyze game state periodically
                current_time = time.time()
                if current_time - self.last_analysis_time >= self.analysis_cooldown:
                    logger.info("Checking for screenshots...")
                    screenshots = self.screen_capture.get_recent_screenshots(1)  # Only need 1 now
                    if screenshots:
                        logger.info("Got screenshot, sending to AI for analysis...")
                        self._analyze_game_state()
                        self.last_analysis_time = current_time
                    else:
                        logger.info("No screenshots available yet")
                    
                time.sleep(0.1)  # Small sleep to prevent CPU overuse
                
            except Exception as e:
                logger.error(f"Error in analysis loop: {e}")
                time.sleep(1)  # Sleep a bit before retrying
                
    def _process_message(self, message: str):
        """Process a user message."""
        try:
            # Get only the latest screenshot
            screenshots = self.screen_capture.get_recent_screenshots(1)
            if not screenshots:
                logger.warning("No screenshots available for message processing")
                return

            # Create game state
            game_state = {
                "screenshots": screenshots[-1:],  # Only use latest
                "message": message,
                "game_name": self.current_game,
                "additional_context": {}
            }
            
            # Get AI response
            response = self.ai_client.analyze(game_state)
            
            # Queue UI updates for the main thread
            self.ui_update_queue.put(lambda: self.overlay.add_message(message, time.time(), is_ai=False))
            if response:
                self.ui_update_queue.put(lambda: self.overlay.add_message(response, time.time(), is_ai=True))
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def _analyze_game_state(self):
        """Analyze the current game state."""
        try:
            # Get only the latest screenshot
            screenshots = self.screen_capture.get_recent_screenshots(1)
            if not screenshots:
                logger.warning("No screenshots available for analysis")
                return

            # Create game state
            game_state = {
                "screenshots": screenshots[-1:],  # Only use latest
                "message": None,
                "game_name": self.current_game,
                "additional_context": {}
            }
            
            # Get AI response
            response = self.ai_client.analyze(game_state)
            
            # Queue UI update for the main thread
            if response:
                self.ui_update_queue.put(lambda: self.overlay.add_message(response, time.time(), is_ai=True))
                
        except Exception as e:
            logger.error(f"Error during auto-analysis: {e}")
            
    def run(self):
        """Run the application."""
        try:
            logger.info("Starting AI Game Partner...")
            
            # Start screen capture
            self.screen_capture.start()
            
            # Set message callback
            self.overlay.set_message_callback(lambda msg: self.message_queue.put(msg))
            
            # Start the analysis thread
            self.analysis_thread.start()
            
            # Log hotkey instructions
            logger.info("Hotkeys:")
            logger.info("- Ctrl+Shift+End: Toggle overlay visibility")
            logger.info("- Ctrl+Shift+Home: Cycle overlay position")
            logger.info("- Ctrl+Shift+Enter: Show message input")
            
            # Show the overlay
            logger.info("Showing overlay...")
            self.overlay.deiconify()
            
            # Start UI update processing
            def process_updates():
                try:
                    # Process any pending UI updates
                    while True:
                        try:
                            update = self.ui_update_queue.get_nowait()
                            if callable(update):
                                logger.info("Processing UI update")
                                update()
                                logger.info("UI update processed")
                        except queue.Empty:
                            break
                            
                    # Schedule next update check if still running
                    if self.running:
                        self.overlay.after(50, process_updates)
                except Exception as e:
                    logger.error(f"Error processing UI updates: {e}")
                    
            # Start the update processing
            logger.info("Starting UI update processing...")
            self.overlay.after(50, process_updates)
            
            # Run the overlay window
            logger.info("Starting overlay mainloop...")
            self.overlay.mainloop()
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.shutdown()
            
    def shutdown(self):
        """Shutdown the application."""
        if not self.running:  # Prevent multiple shutdowns
            return
            
        logger.info("Shutting down...")
        logger.info("Shutting down AI Game Partner...")
        
        # Stop background threads first
        self.running = False
        
        # Stop the hotkey listener
        try:
            self.hotkey_listener.stop()
        except Exception as e:
            logger.error(f"Error stopping hotkey listener: {e}")
        
        # Stop screen capture
        logger.info("Stopping screen capture...")
        try:
            self.screen_capture.stop()
            self.screen_capture.cleanup()
        except Exception as e:
            logger.error(f"Error stopping screen capture: {e}")
            
        # Wait for analysis thread to finish
        if self.analysis_thread:
            try:
                self.analysis_thread.join(timeout=2.0)  # Wait up to 2 seconds
            except TimeoutError:
                logger.warning("Analysis thread did not stop in time")
        
        # Close UI elements
        logger.info("Closing UI elements...")
        try:
            self.overlay.destroy()
        except Exception as e:
            logger.error(f"Error closing UI elements: {e}")
        
        # Cleanup AI client
        logger.info("Cleaning up AI client...")
        try:
            self.ai_client.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up AI client: {e}")
            
        logger.info("Shutdown complete")
        sys.exit(0)  # Ensure we exit

def main():
    """Main entry point for the application."""
    try:
        # Load configuration
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        # Create and run the application
        app = GamePartner(config)
        app.run()
        
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main() 