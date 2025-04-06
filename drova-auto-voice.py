# SYSTEM_PROMPT_GEMINI = '''"You are a highly skilled AI assistant specializing in extracting dialogue from video game text. Your task is to analyze the provided text and identify the name of the character speaking and the exact text of their dialogue.

# You must return the output in a valid JSON format, adhering to the following structure:

# ```json
# {
#   "character_name": "<Character's Name>",
#    "gender": "<Male/Female/Unknown>,
#   "dialogue": "<The character's exact spoken words>"
# }'''


import os
import google.generativeai as genai
from elevenlabs.client import ElevenLabs
from elevenlabs import play, save, Voice, VoiceSettings
from dotenv import load_dotenv
import argparse
from PIL import Image
import json
import re

# --- Configuration ---

# Load environment variables from .env file
load_dotenv()

# Configure Google Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file or environment variables.")
genai.configure(api_key=GOOGLE_API_KEY)

# Configure ElevenLabs API
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not found in .env file or environment variables.")

# --- ElevenLabs Settings (Customize as needed) ---
# Find Voice IDs here: https://elevenlabs.io/voice-library
# Or use client.voices.get_all() after initializing the client
ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" # Example: Rachel (can be changed)
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5" 
# Common options: eleven_multilingual_v2, eleven_mono_v3.0.0
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"

# --- Gemini Settings ---
GEMINI_MODEL = 'gemini-2.0-flash' 

# --- System Prompt for Gemini ---
# This prompt instructs Gemini on how to analyze the image and what format to return.
SYSTEM_PROMPT = """
Analyze the character prominently featured in the screenshot provided.
Identify the character's name, gender, and any dialogue they are speaking
(look for speech bubbles or text directly attributed to them).

Return ONLY a valid JSON object with the following structure:
{
  "character_name": "<Character's Name or Unknown if cannot determine>",
  "gender": "<Male/Female/Unknown>",
  "dialogue": "<The character's exact spoken words as seen in the image, or an empty string if none>"
}

Do not include any explanatory text before or after the JSON object.
Ensure the 'dialogue' field contains only the text spoken by the character.
If no dialogue is clearly visible or attributable to the character, return an empty string for 'dialogue'.
"""

# --- Functions ---

def clean_gemini_response(text: str) -> str:
    """
    Removes potential markdown formatting (like ```json ... ```)
    around the JSON response from Gemini.
    """
    # Regex to find JSON block possibly enclosed in markdown ```json ... ```
    match = re.search(r"```json\s*({.*?})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: try to find JSON directly if no markdown found
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Return original text if no clear JSON structure is found
    return text.strip()


def get_info_from_screenshot(image_path: str) -> dict | None:
    """
    Uploads a screenshot to Gemini and returns the extracted JSON data.
    """
    print(f"Processing image: {image_path}")
    try:
        img = Image.open(image_path)
    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return None
    except Exception as e:
        print(f"Error opening image: {e}")
        return None

    try:
        # Initialize the Gemini model
        model = genai.GenerativeModel(GEMINI_MODEL)

        # Send the prompt and image to the model
        print("Sending request to Gemini API...")
        response = model.generate_content([SYSTEM_PROMPT, img])
        response.resolve() # Wait for the response

        # Clean and parse the JSON response
        cleaned_text = clean_gemini_response(response.text)
        print(f"Raw Gemini response text:\n---\n{response.text}\n---")
        print(f"Cleaned Gemini response text:\n---\n{cleaned_text}\n---")

        try:
            # Handle potential API blocking or empty response
            if not cleaned_text:
                 if response.prompt_feedback.block_reason:
                      print(f"Error: Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
                      return None
                 else:
                      print("Error: Gemini returned an empty response.")
                      return None

            data = json.loads(cleaned_text)
            print(f"Successfully parsed JSON data: {data}")

            # Basic validation of expected keys
            if not all(key in data for key in ["character_name", "gender", "dialogue"]):
                print("Warning: Gemini response missing one or more expected keys.")
                # Fill missing keys with defaults if needed, or handle as error
                data.setdefault("character_name", "Unknown")
                data.setdefault("gender", "Unknown")
                data.setdefault("dialogue", "")

            return data

        except json.JSONDecodeError:
            print(f"Error: Failed to decode JSON from Gemini response.")
            print(f"Received text was: {cleaned_text}")
            return None
        except Exception as e:
            print(f"Error processing Gemini response: {e}")
            return None

    except Exception as e:
        print(f"An error occurred while contacting the Gemini API: {e}")
        # Check for specific Gemini API errors if the library provides them
        return None


def speak_dialogue(text: str, voice_id: str, model_id: str, output_format: str, output_filename: str | None = None):
    """
    Sends text to ElevenLabs API and plays the generated audio.
    Optionally saves the audio to a file.
    """
    if not text or not text.strip():
        print("No dialogue provided to speak.")
        return

    print(f"\nSending dialogue to ElevenLabs: '{text}'")
    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # Define voice settings if needed (optional)
        # voice_settings = VoiceSettings(
        #     stability=0.7,
        #     similarity_boost=0.75
        # )

        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format=output_format,
            # voice_settings=voice_settings # Uncomment to use custom settings
        )

        print("Audio received from ElevenLabs. Playing...")

        # Play the audio directly
        play(audio)
        print("Playback finished.")

        # Optionally save the audio
        if output_filename:
            try:
                save(audio, output_filename)
                print(f"Audio also saved to: {output_filename}")
            except Exception as e:
                print(f"Error saving audio file: {e}")


    except Exception as e:
        print(f"An error occurred with the ElevenLabs API: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a screenshot to extract character info and speak dialogue.")
    parser.add_argument("image_path", help="Path to the screenshot image file.")
    parser.add_argument("-o", "--output", help="Optional: Save the generated audio to this MP3 file path.", default=None)
    args = parser.parse_args()

    # 1. Get information from the screenshot using Gemini
    character_info = get_info_from_screenshot(args.image_path)

    if character_info:
        print("\n--- Extracted Information ---")
        print(f"Character Name: {character_info.get('character_name', 'N/A')}")
        print(f"Gender: {character_info.get('gender', 'N/A')}")
        print(f"Dialogue: {character_info.get('dialogue', 'N/A')}")
        print("---------------------------\n")

        # 2. Extract dialogue
        dialogue = character_info.get("dialogue", "")

        # 3. Send dialogue to ElevenLabs and play
        if dialogue and dialogue.strip():
            speak_dialogue(
                text=dialogue,
                voice_id=ELEVENLABS_VOICE_ID,
                model_id=ELEVENLABS_MODEL_ID,
                output_format=ELEVENLABS_OUTPUT_FORMAT,
                output_filename=args.output
            )
        else:
            print("No dialogue found in the screenshot to speak.")
    else:
        print("Failed to get information from the screenshot.")
