"""
Overlay module for AI Game Partner.
Handles the transparent overlay window and conversation display.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple, List, Dict, Callable
from dataclasses import dataclass
import time
import queue
from pynput import keyboard
from collections import defaultdict
from datetime import datetime
import logging
import platform
import win32gui
import win32con
import win32api

logger = logging.getLogger(__name__)

@dataclass
class OverlayPosition:
    """Represents a position on the screen for the overlay."""
    x: int
    y: int
    anchor: str  # 'nw', 'ne', 'sw', 'se', 'n', 's', 'w', 'e' for positions

@dataclass
class Message:
    """Represents a message in the conversation history."""
    content: str
    timestamp: float
    is_ai: bool = True

class GameOverlay(tk.Tk):
    # Position cycle order: bottom-right -> bottom-middle -> bottom-left -> left-middle -> 
    # top-left -> top-middle -> top-right -> right-middle -> bottom-right
    POSITION_CYCLE = [
        'bottom-right',
        'bottom-middle',
        'bottom-left',
        'left-middle',
        'top-left',
        'top-middle',
        'top-right',
        'right-middle'
    ]
    
    def __init__(self, config):
        """Initialize the overlay window."""
        super().__init__()
        self.config = config
        self.messages: List[Message] = []
        
        # Initialize window handle
        self.hwnd = None
        self.is_visible = True
        
        # Set default position if not specified
        if 'position' not in config['Overlay']:
            config['Overlay']['position'] = 'bottom-right'
            
        # Create main frame first
        self.frame = tk.Frame(
            self,
            bg='#1a1a1a'
        )
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Setup window properties
        self.setup_window()
        
        # Create message display
        self.messages_frame = tk.Frame(
            self.frame,
            bg='#1a1a1a',
            padx=15,
            pady=10
        )
        self.messages_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create input frame (hidden by default)
        self.input_frame = tk.Frame(
            self.frame,
            bg='#1a1a1a'
        )
        self.input_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # Create prompt label
        self.prompt_label = tk.Label(
            self.input_frame,
            text="Prompt: ",
            font=(config['Overlay']['font_family'], int(config['Overlay']['font_size']), config['Overlay']['font_weight']),
            fg='white',
            bg='#1a1a1a'
        )
        self.prompt_label.pack(side=tk.LEFT)
        
        # Create input entry
        self.input_entry = tk.Entry(
            self.input_frame,
            font=(config['Overlay']['font_family'], int(config['Overlay']['font_size'])),
            fg='white',
            bg='#2a2a2a',
            insertbackground='white',
            relief=tk.FLAT,
            width=50
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Create send label
        self.send_label = tk.Label(
            self.input_frame,
            text="SEND (enter)",
            font=(config['Overlay']['font_family'], int(config['Overlay']['font_size']), config['Overlay']['font_weight']),
            fg='#888888',
            bg='#1a1a1a'
        )
        self.send_label.pack(side=tk.RIGHT)
        
        # Hide input frame by default
        self.input_frame.pack_forget()
        
        # Message display setup
        self.visible_messages = int(config['Overlay']['visible_messages'])
        
        # Store callback for message handling
        self.message_callback = None
        
        # Bind enter key to submit
        self.input_entry.bind('<Return>', self._on_submit)
        
        # Bind escape key to hide input
        self.bind('<Escape>', lambda e: self.hide_input())
        
        # Initial position
        self.position = config['Overlay']['position']
        self.update_position()
        
        # Make window click-through
        self.make_click_through()
        
        # Schedule window properties setup
        self.after(100, self._set_window_properties)
        
    def setup_window(self):
        """Setup the overlay window properties."""
        # Remove window decorations
        self.overrideredirect(True)
        
        # Set transparency
        self.attributes('-alpha', float(self.config['Overlay']['background_alpha']))
        
        # Always on top
        self.attributes('-topmost', True)
        
        # Set size
        self.geometry(f"{self.config['Overlay']['width']}x{self.config['Overlay']['height']}")
        
        # Set window style for fullscreen compatibility
        if platform.system() == 'Windows':
            try:
                # Get the window handle
                hwnd = self.winfo_id()
                
                # Set the window style for overlay
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style = win32con.WS_VISIBLE | win32con.WS_POPUP
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                
                # Set extended window style
                exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                exstyle = win32con.WS_EX_TOPMOST | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle)
                
                # Set the layered window attributes
                win32gui.SetLayeredWindowAttributes(
                    hwnd, 
                    win32api.RGB(0,0,0), 
                    int(float(self.config['Overlay']['background_alpha']) * 255), 
                    win32con.LWA_ALPHA
                )
                
            except Exception as e:
                logger.error(f"Error setting up window style: {e}")

    def make_click_through(self):
        """Make the window click-through based on platform."""
        if platform.system() == 'Windows':
            try:
                # Get the window handle
                hwnd = self.winfo_id()
                
                # Add WS_EX_TRANSPARENT to make it click-through
                exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                exstyle |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle)
                
                # Set layered window attributes
                win32gui.SetLayeredWindowAttributes(
                    hwnd,
                    win32api.RGB(0,0,0),
                    int(float(self.config['Overlay']['background_alpha']) * 255),
                    win32con.LWA_ALPHA
                )
                
                # Force window to be topmost
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                )
                
                logger.info("Window made click-through")
                
            except Exception as e:
                logger.error(f"Error making window click-through: {e}")
        else:
            # Linux click-through
            self.wait_visibility(self)
            self.attributes('-alpha', float(self.config['Overlay']['background_alpha']))

    def add_message(self, text: str, timestamp: float, is_ai: bool = True):
        """Add a message to the overlay."""
        try:
            # Create message frame with padding
            msg_frame = tk.Frame(
                self.messages_frame,
                bg='#1a1a1a',
                padx=10,  # Increased side padding
                pady=5
            )
            msg_frame.pack(fill=tk.X, padx=10, pady=2)  # Increased side padding
            
            # Add timestamp
            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
            tk.Label(
                msg_frame,
                text=time_str,
                font=(self.config['Overlay']['font_family'], int(self.config['Overlay']['font_size']), self.config['Overlay']['font_weight']),
                fg='#888888',
                bg='#1a1a1a'
            ).pack(side=tk.LEFT, padx=(5, 15))  # Adjusted timestamp padding
            
            # Add message text with proper wrapping
            msg_label = tk.Label(
                msg_frame,
                text=text,
                font=(self.config['Overlay']['font_family'], int(self.config['Overlay']['font_size']), self.config['Overlay']['font_weight']),
                fg='white',
                bg='#1a1a1a',
                justify=tk.LEFT,
                wraplength=int(int(self.config['Overlay']['width']) * 0.85),  # Slightly wider for better text flow
                anchor='w'
            )
            msg_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))  # Added right padding
            
            # Store message
            self.messages.append((msg_frame, timestamp))
            
            # Trim old messages
            self.update_messages()
            
        except Exception as e:
            logger.error(f"Error adding message: {e}")

    def update_messages(self):
        """Update the visible messages."""
        try:
            # Get max visible messages
            max_messages = int(self.config['Overlay']['visible_messages'])
            
            # Remove old messages if we have too many
            while len(self.messages) > max_messages:
                old_frame, _ = self.messages.pop(0)
                old_frame.destroy()
            
            # Update message frames
            for frame, _ in self.messages:
                frame.pack_configure(fill=tk.X, padx=10, pady=2)
                
            # Force update
            self.messages_frame.update_idletasks()
            
        except Exception as e:
            logger.error(f"Error updating messages: {e}")

    def set_message_callback(self, callback: Callable[[str], None]):
        """Set the callback for handling user messages."""
        self.message_callback = callback
        
    def show_input(self):
        """Show the input field."""
        try:
            logger.info("Showing input dialog...")
            # Temporarily disable click-through
            if platform.system() == 'Windows':
                try:
                    hwnd = self.winfo_id()
                    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    exstyle &= ~win32con.WS_EX_TRANSPARENT  # Remove transparent flag
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle)
                except Exception as e:
                    logger.error(f"Error making window interactive: {e}")
            
            # Show and focus input
            self.input_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
            self.input_entry.delete(0, tk.END)
            self.input_entry.focus_set()
            self.deiconify()
            self.lift()
            self.attributes('-topmost', True)
            
            # Force focus to input
            self.after(100, self.input_entry.focus_set)
            logger.info("Input dialog shown and focused")
            
        except Exception as e:
            logger.error(f"Error showing input: {e}")
        
    def hide_input(self):
        """Hide the input field."""
        try:
            logger.info("Hiding input dialog...")
            # Restore click-through
            if platform.system() == 'Windows':
                try:
                    hwnd = self.winfo_id()
                    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    exstyle |= win32con.WS_EX_TRANSPARENT  # Add transparent flag back
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle)
                except Exception as e:
                    logger.error(f"Error restoring click-through: {e}")
            
            self.input_frame.pack_forget()
            self.input_entry.delete(0, tk.END)
            logger.info("Input dialog hidden")
            
        except Exception as e:
            logger.error(f"Error hiding input: {e}")
        
    def _on_submit(self, event):
        """Handle message submission."""
        message = self.input_entry.get().strip()
        if message and self.message_callback:
            self.message_callback(message)
        self.hide_input()
        
    def toggle_visibility(self):
        """Toggle overlay visibility."""
        try:
            logger.info(f"Toggle visibility called (current state: {self.is_visible})")
            if self.is_visible:
                logger.info("Hiding overlay...")
                self.withdraw()
                self.is_visible = False
                logger.info("Overlay hidden")
            else:
                logger.info("Showing overlay...")
                self.deiconify()
                self.lift()
                self.attributes('-topmost', True)
                self.make_click_through()
                self.update_position()  # Ensure position is correct when showing
                self.is_visible = True
                logger.info("Overlay shown")
            self.update_idletasks()  # Force update
            logger.info(f"Visibility toggled to: {self.is_visible}")
        except Exception as e:
            logger.error(f"Error toggling visibility: {e}")

    def cycle_position(self):
        """Cycle through overlay positions."""
        try:
            logger.info(f"Cycle position called (current position: {self.position})")
            current_idx = self.POSITION_CYCLE.index(self.position)
            next_idx = (current_idx + 1) % len(self.POSITION_CYCLE)
            self.position = self.POSITION_CYCLE[next_idx]
            logger.info(f"Moving to position: {self.position}")
            self.update_position()
            # Make sure we're visible and on top after position change
            if self.is_visible:
                logger.info("Ensuring window is on top after position change")
                self.lift()
                self.attributes('-topmost', True)
                self.make_click_through()
            self.update_idletasks()  # Force update
            logger.info(f"Position changed to: {self.position}")
        except ValueError:
            # If current position not found in cycle, reset to first position
            logger.warning(f"Current position {self.position} not found in cycle, resetting to first position")
            self.position = self.POSITION_CYCLE[0]
            self.update_position()
            logger.info(f"Position reset to: {self.position}")
        except Exception as e:
            logger.error(f"Error cycling position: {e}")

    def update_position(self):
        """Update the overlay position based on the current setting."""
        try:
            logger.info(f"Updating position to: {self.position}")
            # Get screen dimensions
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            window_width = int(self.config['Overlay']['width'])
            window_height = int(self.config['Overlay']['height'])
            
            logger.info(f"Screen dimensions: {screen_width}x{screen_height}")
            logger.info(f"Window dimensions: {window_width}x{window_height}")
            
            # Add padding for edges
            side_padding = 40  # Match bottom padding
            
            # Calculate position based on position name
            if self.position == 'top-left':
                x = side_padding
                y = side_padding
            elif self.position == 'top-middle':
                x = (screen_width - window_width) // 2
                y = side_padding
            elif self.position == 'top-right':
                x = screen_width - window_width - side_padding
                y = side_padding
            elif self.position == 'right-middle':
                x = screen_width - window_width - side_padding
                y = (screen_height - window_height) // 2
            elif self.position == 'bottom-right':
                x = screen_width - window_width - side_padding
                y = screen_height - window_height - 40  # Keep taskbar padding
            elif self.position == 'bottom-middle':
                x = (screen_width - window_width) // 2
                y = screen_height - window_height - 40  # Keep taskbar padding
            elif self.position == 'bottom-left':
                x = side_padding
                y = screen_height - window_height - 40  # Keep taskbar padding
            elif self.position == 'left-middle':
                x = side_padding
                y = (screen_height - window_height) // 2
            else:
                x = side_padding
                y = side_padding
                
            logger.info(f"Calculated position: x={x}, y={y}")
                
            # Update window position and ensure it's visible
            geometry = f"{window_width}x{window_height}+{x}+{y}"
            logger.info(f"Setting geometry: {geometry}")
            self.geometry(geometry)
            self.update_idletasks()  # Force update
            
            # Ensure messages are visible
            self.update_messages()
            
            # Log the position change
            logger.info(f"Window positioned at {x},{y} for {self.position}")
            
        except Exception as e:
            logger.error(f"Error updating position: {e}")

    def close(self):
        """Close the overlay window."""
        self.destroy()
        
    def _set_window_properties(self):
        """Set extended window properties for fullscreen overlay support."""
        if platform.system() != 'Windows':
            return
            
        try:
            if self.hwnd is None:
                self.hwnd = self.winfo_id()
                
                # Set the window style
                style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
                style &= ~win32con.WS_MAXIMIZEBOX
                style &= ~win32con.WS_MINIMIZEBOX
                style &= ~win32con.WS_SYSMENU
                style &= ~win32con.WS_CAPTION
                style |= win32con.WS_POPUP
                win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, style)
                
                # Set extended window style
                exstyle = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
                exstyle |= win32con.WS_EX_LAYERED
                exstyle |= win32con.WS_EX_TRANSPARENT
                exstyle |= win32con.WS_EX_TOPMOST
                exstyle |= win32con.WS_EX_TOOLWINDOW
                exstyle |= win32con.WS_EX_NOACTIVATE
                win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, exstyle)
                
                # Force window to be topmost
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                )
                
                logger.info("Window properties set successfully")
            
        except Exception as e:
            logger.error(f"Error setting window properties: {e}")
            self.after(100, self._set_window_properties) 