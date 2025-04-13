"""
Input dialog module for AI Game Partner.
Handles user message input to the AI.
"""

import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger(__name__)

class InputDialog:
    def __init__(self, config, message_queue):
        """
        Initialize the input dialog.
        
        Args:
            config: Configuration object containing UI settings
            message_queue: Queue to store user messages for next AI analysis
        """
        self.config = config
        self.message_queue = message_queue
        self.is_visible = False
        
        # Create dialog window
        self.window = tk.Toplevel()
        self.window.title("Message AI Partner")
        self.window.attributes('-topmost', True)
        
        # Set theme colors
        bg_color = config['Overlay']['background_color']
        fg_color = config['Overlay']['text_color']
        self.window.configure(bg=bg_color)
        
        # Create main frame with padding
        self.frame = ttk.Frame(self.window, padding="5", style='Custom.TFrame')
        self.frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create and configure text input
        self.text_input = tk.Entry(  # Using tk.Entry instead of ttk.Entry for better color control
            self.frame,
            width=50,
            font=(config['Overlay']['font_family'],
                  int(config['Overlay']['font_size']),
                  'normal'),
            bg=bg_color,
            fg=fg_color,
            insertbackground=fg_color  # Cursor color
        )
        self.text_input.grid(row=0, column=0, pady=5, sticky=(tk.W, tk.E))
        
        # Configure custom styles
        style = ttk.Style()
        style.configure('Custom.TFrame',
                       background=bg_color)
        
        # Bind events
        self.text_input.bind('<Return>', self._submit)  # Only submit on regular Enter key
        self.window.protocol("WM_DELETE_WINDOW", self.hide)  # Just hide on window close
        
        # Hide initially
        self.hide()
        
    def _submit(self, event=None):
        """Queue the current input text for next AI analysis."""
        text = self.text_input.get().strip()
        if text:
            # Add message to queue
            logger.info(f"Queuing user message: {text}")
            self.message_queue.put(text)
            # Clear and hide
            self.text_input.delete(0, tk.END)
            self.hide()
            
    def show(self):
        """Show the input dialog."""
        if not self.is_visible:
            # Reset state
            self.text_input.delete(0, tk.END)
            
            # Position near the overlay
            self.window.deiconify()
            self.window.lift()
            self.text_input.focus_set()
            self.is_visible = True
            
    def hide(self):
        """Hide the input dialog."""
        self.window.withdraw()
        self.is_visible = False
        
    def toggle(self):
        """Toggle the visibility of the input dialog."""
        if self.is_visible:
            self.hide()  # Just hide, don't submit
        else:
            self.show()
            
    def destroy(self):
        """Destroy the input dialog."""
        self.window.destroy() 