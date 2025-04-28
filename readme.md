# Screenshot Character Voiceover

This project analyzes a screenshot (e.g., from a game or visual novel) to identify the speaking character and their dialogue using Google Gemini. It then maps the character to a Text-to-Speech (TTS) voice (either from ElevenLabs or Google Cloud TTS) and generates audio for the dialogue. The system remembers character-voice mappings to maintain consistency across multiple images featuring the same character.

## Features

*   **Character & Dialogue Extraction:** Uses Google Gemini Vision capabilities to parse characters and speech bubbles from images.
*   **Dual TTS Backend Support:** Easily switch between ElevenLabs and Google Cloud Text-to-Speech via configuration.
*   **Persistent Voice Mapping:** Assigns a unique voice to each recognized character (within the chosen TTS service) and saves the mapping locally (`character_voices.json`).
*   **Automatic Voice Assignment:** Assigns available voices based on detected gender (Male/Female/Unknown), attempting to use unassigned voices first.
*   **Configurable:** API keys, TTS provider choice, and other settings managed via a `.env` file.
*   **Audio Playback & Saving:** Plays the generated audio directly and optionally saves it to an MP3 file.

## Prerequisites

*   **Python:** Version 3.9 or higher recommended.
*   **pip:** Python package installer (usually included with Python).
*   **API Keys:**
    *   **Google Gemini API Key:** Obtain from [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   **ElevenLabs API Key:** Obtain from the [ElevenLabs Website](https://elevenlabs.io/). (Needed if using ElevenLabs)
*   **Google Cloud Account & Credentials (for Google TTS):**
    *   A Google Cloud Platform project with the Text-to-Speech API enabled.
    *   A Service Account Key file (`.json`).
    *   The `GOOGLE_APPLICATION_CREDENTIALS` environment variable set to the path of your service account key file OR the path specified directly in the `.env` file. See [Google Cloud Authentication Docs](https://cloud.google.com/docs/authentication/provide-credentials-adc#local-dev).
*   **Required Libraries:** `sounddevice` and `soundfile` might require system libraries (like `libsndfile`) for audio playback on some systems (especially Linux). `portaudio` might be needed for `sounddevice`.

## Installation

1.  **Clone the repository (or download the files):**
    ```bash
    git clone <your-repo-url> # Or download and extract zip
    cd <repository-directory>
    ```

2.  **Create and activate a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Create a `.env` file** in the project's root directory.
2.  **Copy the following content** into your `.env` file and **replace the placeholder values** with your actual credentials and desired settings:

    ```dotenv
    # --- API Keys ---
    GOOGLE_API_KEY="YOUR_GEMINI_API_KEY_HERE"
    ELEVENLABS_API_KEY="YOUR_ELEVENLABS_API_KEY_HERE" # Required only if TTS_PROVIDER='elevenlabs'

    # --- Service Selection ---
    # Choose the Text-to-Speech provider: 'elevenlabs' or 'google'
    TTS_PROVIDER="elevenlabs"

    # --- Google Cloud Specific (Only needed if TTS_PROVIDER='google') ---
    # Set this environment variable system-wide OR uncomment and set the path here
    # GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/google_cloud_credentials.json"

    # --- Optional: Default Fallback Voice ID ---
    # Provide a voice ID known to work for the *default* TTS_PROVIDER set above
    # For ElevenLabs: e.g., "JBFqnCBsd6RMkjVDRZzb" (Rachel)
    # For Google TTS: e.g., "en-US-Standard-A" (Female) or "en-US-Wavenet-B" (Male)
    DEFAULT_FALLBACK_VOICE_ID="JBFqnCBsd6RMkjVDRZzb"
    ```

3.  **Key Configuration Points:**
    *   `GOOGLE_API_KEY`: Your API key for Google Gemini.
    *   `ELEVENLABS_API_KEY`: Your API key for ElevenLabs (only needed if `TTS_PROVIDER` is `elevenlabs`).
    *   `TTS_PROVIDER`: Set this to `elevenlabs` or `google` to choose the TTS service. **This determines which service's voices are fetched and used.**
    *   `GOOGLE_APPLICATION_CREDENTIALS`: If using `TTS_PROVIDER="google"`, make sure the environment variable is set globally, or uncomment this line and provide the full path to your Google Cloud service account JSON key file.
    *   `DEFAULT_FALLBACK_VOICE_ID`: Set this to a *valid* voice ID for the service specified in `TTS_PROVIDER`. This voice is used if a character is "Unknown" or if no suitable voice can be assigned from the available pool.

## Usage

**Step 1: Fetch Voices (Required on first run & after switching TTS provider)**

Before running the main script, you need to fetch the list of available voices from your chosen TTS provider.

1.  Ensure `TTS_PROVIDER` is set correctly in your `.env` file.
2.  Run the `fetch_voices.py` script:
    ```bash
    python scripts/fetch_voices.py
    ```
3.  This will contact the configured TTS API (ElevenLabs or Google), retrieve a list of available voices (filtered for English), and save them in a standardized format to `voices.json`.

**Step 2: Run the Main Orchestrator**

1.  Make sure `TTS_PROVIDER` in `.env` matches the voices you fetched into `voices.json`.
2.  Run the `main_orchestrator.py` script, providing the path to your screenshot image:
    ```bash
    python main_orchestrator.py /path/to/your/screenshot.png
    ```
3.  **To save the audio output** to a file, use the `-o` or `--output` flag:
    ```bash
    python main_orchestrator.py /path/to/your/screenshot.png -o output/dialogue_audio.mp3
    ```
    (The `output/` directory will be created if it doesn't exist.)

**What happens:**

*   The script sends the image to Gemini to extract character info.
*   It checks `character_voices.json` for an existing voice mapping for the character.
*   If no mapping exists, it selects an available, unassigned voice from `voices.json` based on the character's gender (or tries female/male pools if gender is Unknown).
*   If a new voice is assigned, `character_voices.json` is updated.
*   The extracted dialogue is sent to the configured TTS service (`elevenlabs` or `google`) using the selected voice ID.
*   The resulting audio is played back and optionally saved to the specified file.

## Switching TTS Providers

To change the Text-to-Speech service used (e.g., from ElevenLabs to Google TTS):

1.  **Update `.env`:** Change the `TTS_PROVIDER` value (e.g., from `elevenlabs` to `google`). Also, ensure the corresponding API key (`ELEVENLABS_API_KEY` or Google credentials) and `DEFAULT_FALLBACK_VOICE_ID` are appropriate for the *new* provider.
2.  **Clear Old Mappings (Recommended):** Voice IDs are specific to each TTS provider. Delete the existing `character_voices.json` file to start fresh voice assignments for the new provider. Otherwise, the script will try to use old (and now invalid) voice IDs.
3.  **Fetch New Voices:** Rerun the voice fetching script to populate `voices.json` with voices from the *newly selected* provider:
    ```bash
    python scripts/fetch_voices.py
    ```
4.  **Run Main Script:** Now you can run `main_orchestrator.py` as usual. It will use the new TTS provider and build new character mappings in `character_voices.json`.

## File Structure Overview

*   `.env`: Stores API keys and configuration secrets.
*   `config.py`: Loads `.env` and defines application settings and constants.
*   `requirements.txt`: Lists Python package dependencies.
*   `main_orchestrator.py`: The main script that orchestrates the process (image analysis -> voice selection -> TTS).
*   `image_analyzer.py`: Handles image loading, resizing, and communication with the Google Gemini API for analysis.
*   `voice_selector.py`: Contains the logic for loading `voices.json` and `character_voices.json`, and for assigning/retrieving character-specific voice IDs locally.
*   `tts_elevenlabs.py`: Contains functions (`synthesize`, `get_voices`) specific to interacting with the ElevenLabs API.
*   `tts_google.py`: Contains functions (`synthesize`, `get_voices`) specific to interacting with the Google Cloud Text-to-Speech API.
*   `data_manager.py`: Utility functions for safely loading and saving JSON data files.
*   `utils.py`: General helper functions (e.g., cleaning API responses).
*   `voices.json`: Stores the list of available voices fetched from the configured TTS provider (created/updated by `fetch_voices.py`).
*   `character_voices.json`: Stores the mapping between character names (lowercase) and their assigned TTS voice IDs (created/updated by `main_orchestrator.py` via `voice_selector.py`).
*   `scripts/`: Directory for utility scripts.
    *   `fetch_voices.py`: Script to fetch voices from the configured TTS provider.
    *   `data/`: Directory containing data files.
    *   `voices.json`: Stores the list of available voices fetched from the configured TTS provider (created/updated by `fetch_voices.py` inside the `data/` directory).
    *   `character_voices.json`: Stores the mapping between character names (lowercase) and their assigned TTS voice IDs (created/updated by `main_orchestrator.py` via `voice_selector.py` inside the `data/` directory).

## Potential Improvements

*   More robust error handling for API calls and file operations.
*   More sophisticated voice selection logic (e.g., using voice similarity, allowing manual overrides).
*   Support for more TTS providers.
*   Improved logging.
*   Handling multiple characters detected in a single image.
*   A simple GUI interface.