# Screenshot Character Voiceover

This project uses Google Gemini to analyze a screenshot (e.g., from a game or visual novel), identify the speaking character, their dialogue, and generate a unique AI persona for them. It then maps the character to a Text-to-Speech (TTS) voice from one of four supported providers and generates audio for the dialogue.

The system can be run in two modes: processing a single image file from the command line, or running in the background as an **interactive hotkey-driven tool** for real-time voiceovers.

## Features

*   **AI-Generated Character Personas:** Uses Google Gemini Vision to not only extract character info but also generate a detailed persona (personality, vocal style, tone) based on their appearance and the game's context.
*   **Persona-Driven Synthesis:** For **OpenAI** and **Gemini TTS**, the generated persona is used as an instruction to guide the voice synthesis, resulting in more expressive and context-aware speech.
*   **Multiple TTS Backend Support:** Easily switch between four TTS providers via a simple configuration change:
    *   **ElevenLabs**
    *   **Google Cloud Text-to-Speech**
    *   **OpenAI TTS** (Supports persona instructions)
    *   **Gemini TTS** (Supports persona instructions)
*   **Interactive Hotkey Mode:** Run `interactive_listener.py` to capture and process your screen with a single keypress, perfect for use while gaming.
*   **Persistent Voice & Persona Mapping:** Assigns a unique voice and stores the AI-generated persona for each recognized character. This is saved locally in provider-specific files (e.g., `openai_character_voices.json`) to maintain consistency.
*   **Automatic Voice Assignment:** Intelligently assigns available voices based on detected gender, attempting to use unassigned voices first before reusing them.
*   **Easy Cache Management:** A `--clear-cache` command-line flag is available to easily delete voice lists and character mappings for a clean start.
*   **Audio Playback & Saving:** Plays the generated audio directly and can optionally save it to a file.

## Prerequisites

*   **Python:** Version 3.10 or higher.
*   **pip:** Python package installer.
*   **API Keys:**
    *   **Google Gemini API Key:** Obtain from [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   **ElevenLabs API Key:** (Needed if using `elevenlabs`).
    *   **OpenAI API Key:** (Needed if using `openai`).
*   **Google Cloud Credentials** (Needed if using `google` TTS):
    *   A Google Cloud Platform project with the Text-to-Speech API enabled.
    *   A Service Account Key JSON file.
*   **System Libraries:** `sounddevice` might require system libraries like `portaudio` or `libsndfile` for audio playback, especially on Linux.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <repository-directory>
    ```

2.  **Create and activate a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows: .\venv\Scripts\activate
    # On macOS/Linux: source venv/bin/activate
    ```

3.  **Install dependencies from `requirements.txt`:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  Create a **`.env`** file in the project's root directory.
2.  Feel free to reuse the `.sampleenv` file and fill in your credentials. **You only need to provide keys for the service(s) you intend to use.**

    ```

## Usage

On the first run with a new `TTS_PROVIDER`, the application will **automatically fetch and cache** the available voices for that service. You do not need to run a separate script for this.

### Mode 1: Interactive Hotkey Mode (Recommended)

This mode runs in the background and listens for a hotkey press to capture the screen, analyze it, and speak the dialogue.

1. Set your desired `TTS_PROVIDER` in the `.env` file.

2.  Run the `interactive_listener.py` script:
    ```bash
    python interactive_listener.py
    ```
    
3. Press the **` ` `** key (tilde/backtick, usually above Tab) to trigger a capture.

4.  Press the **`esc`** key to shut down the script gracefully.

**Note: Ideally you can simply bind the key to what triggers next dialog e.g., mouse left click/gamepad input. That way you don't have a separate key to press. Yes, this may lead to more false triggers but it is generally robust so you won't hear a random voice :)** 

### Mode 2: Single Image Processing

This mode processes a single image file you provide and then exits.

1.  Set your desired `TTS_PROVIDER` in the `.env` file.
2.  Run the `main_orchestrator.py` script, providing the path to your screenshot:
    ```bash
    python main_orchestrator.py /path/to/your/screenshot.png
    ```
3.  **To save the audio output**, use the `-o` or `--output` flag:
    ```bash
    python main_orchestrator.py /path/to/your/screenshot.png -o output/dialogue.mp3
    ```

### Clearing the Cache

To start fresh with new voice assignments for your currently configured provider, use the `--clear-cache` flag with either script. This will delete the corresponding `voices.json` and `character_voices.json` files from the `data/` directory.

```bash
# Example for interactive mode
python interactive_listener.py --clear-cache

# Example for single image mode
python main_orchestrator.py /path/to/screenshot.png --clear-cache
```
