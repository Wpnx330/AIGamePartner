"""
AI Client module for AI Game Partner.
Handles communication with Claude API and screenshot analysis using LangChain.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import CallbackManager
from langchain_community.callbacks import get_openai_callback
from langchain.memory import ConversationBufferWindowMemory
import base64
import configparser
from anthropic import Anthropic
import json

logger = logging.getLogger(__name__)

@dataclass
class GameState:
    """Represents the current state of the game session."""
    screenshots: List[str]  # List of Screenshot objects
    message: Optional[str] = None  # User message if any
    game_name: Optional[str] = None  # Name of the game being played
    additional_context: Optional[Dict[str, Any]] = None  # Additional context about the game state

@dataclass
class AIResponse:
    """Represents a response from the AI."""
    suggestion: str
    timestamp: float
    context: Dict  # Additional context about the analysis
    token_usage: Dict[str, int]  # Track token usage for monitoring

class AIClient:
    def __init__(self, config: configparser.ConfigParser):
        """Initialize the AI client."""
        logger.info("Loading API key from config...")
        self.api_key = config['API']['claude_api_key']
        if not self.api_key:
            raise ValueError("claude_api_key not set in config.ini")
            
        logger.info("Initializing AI client...")
        self.client = Anthropic(api_key=self.api_key)
        self.model = config['API']['model']
        self.temperature = float(config['AI']['temperature'])
        self.max_tokens = int(config['AI']['max_tokens'])
        self.max_response_length = int(config['AI']['max_response_length'])
        
        # Initialize conversation history
        self.conversation_history = []
        self.max_history = int(config['AI']['memory_window_size'])
        logger.info("AI client initialization complete")
        
    def analyze(self, game_state: Dict) -> str:
        """Analyze the game state and return a response."""
        try:
            logger.debug("Creating message context...")
            
            # Build the prompt
            human_message = f"Analyze these {len(game_state['screenshots'])} screenshots.\n\
            \n\
            Remember:\n\
            - Keep your response under {self.max_response_length} characters\n\
            - Focus on what's new/changed\n\
            - One clear, actionable suggestion\n\
            - If no game is detected and there's no user message, respond with 'Waiting for gameplay...'\n\
            - If there's a user message, respond to it conversationally while mentioning that you're waiting for gameplay\n\
            \n\
            Additional context: {game_state.get('additional_context', 'None provided')}"
            
            if game_state.get('message'):
                human_message = f"User message: {game_state['message']}\n\n{human_message}"
                
            if game_state.get('game_name'):
                human_message = f"Game: {game_state['game_name']}\n\n{human_message}"
            
            # Create messages array with conversation history
            messages = []
            
            # Add conversation history
            messages.extend(self.conversation_history)
            
            # Add current message
            messages.append({
                "role": "user",
                "content": [{"type": "text", "text": human_message}]
            })
            
            logger.debug("Sending request to Claude API...")
            
            # Get response from Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system="You are an AI game partner analyzing screenshots of a game.\n\
        Your role is to provide strategic advice and suggestions based on the game state.\n\
        \n\
        IMPORTANT INSTRUCTIONS:\n\
        1. If you don't detect any active gameplay in the screenshots (e.g., if you see an IDE, desktop, or other non-game content):\n\
           - If there's no user message, respond ONLY with: 'Waiting for gameplay...'\n\
           - If there is a user message, respond conversationally while mentioning you're waiting for gameplay\n\
             Example: 'Hi there! I'm waiting for gameplay to start, but feel free to chat with me in the meantime!'\n\
        2. When you do detect gameplay, keep your responses VERY concise, under 150 characters.\n\
        \n\
        When gameplay is detected, follow these guidelines:\n\
        1. Focus on the most important changes since your last suggestion\n\
        2. Give specific, actionable advice in 1-2 short sentences\n\
        3. If you notice patterns, mention them briefly\n\
        4. Prioritize immediate tactical moves over long-term strategy\n\
        5. If uncertain about something in the image, mention it very briefly\n\
        6. Use short, clear sentences\n\
        7. Avoid lengthy explanations or multiple options\n\
        \n\
        Example responses for active gameplay:\n\
        - \"Enemy team flanking from the left side. Fall back to high ground.\"\n\
        - \"Low on health and ammo. Use the nearby health pack before engaging.\"\n\
        - \"Two enemies isolated at point B. Good opportunity to push with your ultimate.\"\n\
        \n\
        Example responses when no gameplay is detected:\n\
        - \"Waiting for gameplay...\"\n\
        - \"Hi! I'm ready to help once the game starts. What game will we be playing?\"\n\
        - \"Thanks for the message! I'll start analyzing once gameplay begins.\"\n\
        \n\
        Remember to reference previous messages when appropriate to maintain conversation continuity.\n",
                messages=messages
            )
            
            # Update conversation history
            self.conversation_history.append({
                "role": "user",
                "content": [{"type": "text", "text": human_message}]
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": [{"type": "text", "text": response.content[0].text}]
            })
            
            # Trim history if it exceeds max size
            while len(self.conversation_history) > self.max_history * 2:  # *2 because each exchange has 2 messages
                self.conversation_history.pop(0)
            
            logger.info("Received response from Claude API")
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            return f"Error analyzing game state: {str(e)}"
            
    def cleanup(self):
        """Clean up any resources."""
        self.conversation_history.clear()
        logger.info("Conversation history cleared")
        
    def can_make_request(self) -> bool:
        """Check if enough time has passed since the last request."""
        return time.time() - self.last_request_time >= self.cooldown
        
    def time_until_next_request(self) -> float:
        """Get the number of seconds until the next request can be made."""
        if self.can_make_request():
            return 0
        return self.cooldown - (time.time() - self.last_request_time)
        
    def _encode_image(self, image_path: str) -> str:
        """Convert an image file to base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
            
    def _create_system_prompt(self, game_state: GameState) -> str:
        """Create the system prompt with game context."""
        return f"""You are an AI game partner analyzing screenshots of {game_state.game_name or 'a game'}.
        Your role is to provide strategic advice and suggestions based on the game state.
        
        IMPORTANT: Keep your responses VERY concise, ideally under {self.max_response_length} characters.
        The response will be displayed in a small overlay window, so brevity is crucial.
        
        Guidelines:
        1. Focus on the most important changes since your last suggestion
        2. Give specific, actionable advice in 1-2 short sentences
        3. If you notice patterns, mention them briefly
        4. Prioritize immediate tactical moves over long-term strategy
        5. If uncertain about something in the image, mention it very briefly
        6. Use short, clear sentences
        7. Avoid lengthy explanations or multiple options
        
        Example responses (notice the brevity and actionability):
        - "Enemy team flanking from the left side. Fall back to high ground."
        - "Low on health and ammo. Use the nearby health pack before engaging."
        - "Two enemies isolated at point B. Good opportunity to push with your ultimate."
        - "Team scattered - regroup at the payload before next fight."
        - "Enemy sniper watching mid. Take the side route through caves."
        
        Your responses will appear in an overlay like this:
        [13:45:23] Watch for enemy flankers on the left side.
        [13:45:53] Enemy team regrouping at point B. Consider rotating.
        [13:46:23] Low health - fall back and heal before next engagement.
        
        Notice how each message is:
        - One or two short sentences
        - Specific and actionable
        - Focused on the most important information
        - Easy to read at a glance
        
        Additional context:
        {game_state.additional_context or 'No additional context provided'}
        """
        
    def get_prompt_template(self, game_name: Optional[str] = None) -> str:
        """
        Get the appropriate prompt template for the game.
        
        Args:
            game_name: Optional name of the game for game-specific prompts
            
        Returns:
            String template for the AI prompt
        """
        # TODO: Implement game-specific prompt templates
        return """
        You are an AI game partner analyzing a screenshot of {game_name}.
        Please provide strategic advice and suggestions based on the current game state.
        
        Current game state:
        {game_state}
        
        Additional context:
        {context}
        
        Please provide:
        1. A brief analysis of the current situation
        2. Specific suggestions or recommendations
        3. Any potential risks or opportunities to consider
        """ 