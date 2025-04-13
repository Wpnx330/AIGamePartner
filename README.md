# AI Game Partner

An AI-powered gaming companion that provides real-time assistance and interaction through an overlay window.

## Features

- Transparent overlay window that stays on top of games
- Click-through functionality to avoid interfering with game input
- Configurable positioning (8 different positions around the screen)
- Hotkey support:
  - Ctrl+Shift+End: Toggle overlay visibility
  - Ctrl+Shift+Home: Cycle overlay position
  - Ctrl+Shift+Enter: Show input dialog for AI interaction
- Real-time screen analysis and AI responses
- Customizable appearance (size, font, opacity)

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. Install requirements: `pip install -r requirements.txt`
5. Copy `config.ini.example` to `config.ini`
6. Add your API key to `config.ini`
7. Run the application: `python src/main.py`

## Configuration

The `config.ini` file contains all configurable options:
- AI settings (API key, model)
- Overlay appearance (size, font, position)
- Screenshot settings (interval, max screenshots)

## Requirements

- Python 3.8+
- Anthropic API key (for Claude AI)
- Windows OS (for overlay functionality) 