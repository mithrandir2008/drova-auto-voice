import os
import google.generativeai as genai
# Updated imports might be needed depending on exact elevenlabs version features
from elevenlabs.client import ElevenLabs
from elevenlabs import play, save # Removed Voice, VoiceSettings unless specifically needed later
from dotenv import load_dotenv
import argparse
from PIL import Image
import json
import re
import random # For potential random selection if pools exhausted

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

# Initialize ElevenLabs Client (do it once)
try:
    eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
except Exception as e:
    raise ConnectionError(f"Failed to initialize ElevenLabs client: {e}")


# --- ElevenLabs Settings (Defaults/Fallbacks) ---
# This is now primarily a fallback if mapping fails
DEFAULT_FALLBACK_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" # Example: Rachel (used if no voice assigned/found)
# Check if this model is compatible with most voices you fetched, or choose a broad one
# like eleven_multilingual_v2
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5" # Changed to a more general model
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"

# --- Gemini Settings ---
GEMINI_MODEL = 'gemini-2.0-flash' 
print(f"Using Gemini model: {GEMINI_MODEL}")

# --- System Prompt for Gemini ---
SYSTEM_PROMPT = """
Analyze the character prominently featured in the screenshot provided.
Identify the character's name, gender (Male/Female/Unknown), and any dialogue they are speaking
(look for speech bubbles or text directly attributed to them). Use "Unknown" if the name or gender cannot be determined.

Return ONLY a valid JSON object with the following structure:
{
  "character_name": "<Character's Name or Unknown>",
  "gender": "<Male/Female/Unknown>",
  "dialogue": "<The character's exact spoken words as seen in the image, or an empty string if none>"
}

Do not include any explanatory text before or after the JSON object.
Ensure the 'dialogue' field contains only the text spoken by the character.
If no dialogue is clearly visible or attributable to the character, return an empty string for 'dialogue'.
"""

# --- Helper Functions ---

def clean_gemini_response(text: str) -> str:
    """Removes potential markdown formatting around JSON."""
    match = re.search(r"```json\s*({.*?})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def load_json_data(filepath: str, default: dict = None) -> dict:
    """Safely loads JSON data from a file."""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"Info: File not found: {filepath}. Starting with default data.")
            return default
    except json.JSONDecodeError:
        print(f"Warning: Error decoding JSON from {filepath}. Starting with default data.")
        return default
    except IOError as e:
        print(f"Warning: Could not read file {filepath}. Reason: {e}. Starting with default data.")
        return default

def save_json_data(data: dict, filepath: str):
    """Safely saves data to a JSON file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        # print(f"Data successfully saved to {filepath}") # Optional: uncomment for verbose saving
    except IOError as e:
        print(f"Error: Could not write to file {filepath}. Reason: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving to JSON: {e}")


from PIL import Image # Make sure PIL.Image is imported

def resize_image(img: Image.Image, max_height: int = 720) -> Image.Image:
    """
    Resizes a PIL Image object to a maximum height, maintaining aspect ratio.

    Args:
        img: The input PIL Image object.
        max_height: The target maximum height in pixels.

    Returns:
        The resized PIL Image object, or the original if resizing is not needed
        or fails.
    """
    orig_width, orig_height = img.size

    if orig_height > max_height:
        print(f"Original image size: {orig_width}x{orig_height}. Resizing to max height {max_height}px...")
        try:
            # Calculate the new width to maintain aspect ratio
            ratio = max_height / float(orig_height)
            new_width = int(float(orig_width) * ratio)
            new_height = max_height # Target height

            # Resize the image - LANCZOS is good for downscaling quality
            # Use Resampling enum for Pillow >= 9.1.0
            resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
            resized_img = img.resize((new_width, new_height), resample_filter)
            print(f"Image successfully resized to {new_width}x{new_height}.")
            return resized_img # Return the new resized image

        except Exception as e:
            print(f"Warning: Failed to resize image. Using original. Error: {e}")
            return img # Return original image on failure
    else:
        print(f"Image height ({orig_height}px) is within limit ({max_height}px). No resize needed.")
        return img # Return original image if no resize needed
    

def get_info_from_screenshot(image_path: str) -> dict | None:
    """Uploads screenshot to Gemini, returns extracted JSON data."""
    print(f"\nProcessing image: {image_path}")
    try:
        original_img = Image.open(image_path)
        img_to_upload = resize_image(original_img, max_height=720) # Call the function

    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return None
    except Exception as e:
        print(f"Error opening image {image_path}: {e}")
        return None

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        print("Sending request to Gemini API...")
        response = model.generate_content([SYSTEM_PROMPT, img_to_upload], request_options={"timeout": 120}) # Add timeout
        response.resolve()

        # Check for safety blocks before accessing text
        if not response.candidates:
             safety_ratings = response.prompt_feedback.safety_ratings if hasattr(response.prompt_feedback, 'safety_ratings') else "N/A"
             block_reason = response.prompt_feedback.block_reason if hasattr(response.prompt_feedback, 'block_reason') else "Unknown"
             print(f"Error: Gemini response blocked or empty. Reason: {block_reason}, Safety Ratings: {safety_ratings}")
             return None
        # Safely access text
        response_text = ""
        try:
             if response.text:
                  response_text = response.text
             else: # Sometimes content is nested differently
                 response_text = response.candidates[0].content.parts[0].text
        except (AttributeError, IndexError):
            print("Error: Could not extract text from Gemini response structure.")
            print(f"Full response: {response}") # Log full response for debugging
            return None


        cleaned_text = clean_gemini_response(response_text)
        # print(f"Raw Gemini response text:\n---\n{response_text}\n---") # Debug
        print(f"Cleaned Gemini response text:\n---\n{cleaned_text}\n---")

        try:
            if not cleaned_text:
                 print("Error: Gemini returned empty or unusable content after cleaning.")
                 return None

            data = json.loads(cleaned_text)
            print(f"Successfully parsed JSON data: {data}")

            # Validate structure and content
            if not isinstance(data, dict) or not all(key in data for key in ["character_name", "gender", "dialogue"]):
                print("Error: Gemini response is not a valid JSON object with expected keys (character_name, gender, dialogue).")
                return None # Treat as error if structure is wrong

            # Standardize Gender
            data["gender"] = data.get("gender", "Unknown").strip().capitalize()
            if data["gender"] not in ["Male", "Female", "Unknown"]:
                print(f"Warning: Received non-standard gender '{data['gender']}'. Setting to Unknown.")
                data["gender"] = "Unknown"

            # Standardize Character Name (handle potential whitespace)
            data["character_name"] = data.get("character_name", "Unknown").strip()
            if not data["character_name"]: # Treat empty name as Unknown
                 data["character_name"] = "Unknown"

            # Standardize Dialogue
            data["dialogue"] = data.get("dialogue", "").strip()


            return data

        except json.JSONDecodeError:
            print(f"Error: Failed to decode JSON from Gemini response.")
            print(f"Received text for JSON parsing was: {cleaned_text}")
            return None
        except Exception as e:
            print(f"Error processing Gemini JSON response: {e}")
            return None

    except Exception as e:
        print(f"An error occurred while contacting the Gemini API: {e}")
        # Consider more specific error handling for google.api_core.exceptions if needed
        return None


def speak_dialogue(client: ElevenLabs, text: str, voice_id: str, model_id: str, output_format: str, output_filename: str | None = None):
    """Sends text to ElevenLabs API, plays audio, optionally saves."""
    if not text or not text.strip():
        print("No dialogue provided to speak.")
        return
    if not voice_id:
        print("Error: No Voice ID provided for speech synthesis.")
        return

    print(f"\nSending dialogue to ElevenLabs using Voice ID {voice_id}: '{text}'")
    try:
        # Use the globally initialized client
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format=output_format,
        )

        print("Audio received from ElevenLabs. Playing...")
        play(audio)
        print("Playback finished.")

        if output_filename:
            try:
                save(audio, output_filename)
                print(f"Audio also saved to: {output_filename}")
            except Exception as e:
                print(f"Error saving audio file '{output_filename}': {e}")

    except Exception as e:
        # Catch potential specific API errors if the library raises them
        print(f"An error occurred with the ElevenLabs API: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process screenshot, map character to voice, speak dialogue.")
    parser.add_argument("image_path", help="Path to the screenshot image file.")
    parser.add_argument(
        "--voice_list",
        default="elevenlabs_voices.json",
        help="Path to the JSON file containing available ElevenLabs voices (default: elevenlabs_voices.json)."
        )
    parser.add_argument(
        "--mapping_file",
        default="character_voices.json",
        help="Path to the JSON file storing character-to-voice mappings (default: character_voices.json)."
        )
    parser.add_argument(
        "-o", "--output",
        help="Optional: Save the generated audio to this MP3 file path.",
        default=None
        )
    args = parser.parse_args()

    # --- Load Data ---
    print("Loading available voices and character mappings...")
    available_voices = load_json_data(args.voice_list, default={'male': [], 'female': []})
    character_voice_map = load_json_data(args.mapping_file, default={})

    # Create a set of voice IDs already assigned in the map for quick lookup
    assigned_voice_ids = set(character_voice_map.values())
    print(f"Loaded {len(available_voices.get('male', []))} male voices, {len(available_voices.get('female', []))} female voices.")
    print(f"Loaded {len(character_voice_map)} existing character voice mappings.")
    print("-" * 30)

    # --- Process Screenshot ---
    character_info = get_info_from_screenshot(args.image_path)

    if character_info:
        char_name = character_info.get("character_name", "Unknown")
        gender = character_info.get("gender", "Unknown") # Should be Capitalized now
        dialogue = character_info.get("dialogue", "")

        print("\n--- Extracted Information ---")
        print(f"Character Name: {char_name}")
        print(f"Gender: {gender}")
        print(f"Dialogue: '{dialogue}'")
        print("---------------------------\n")

        # --- Voice Selection Logic ---
        selected_voice_id = None
        map_updated = False

        # Use lowercase for map keys for consistency
        map_key = char_name.lower()

        if char_name == "Unknown" or not char_name:
            print("Character name is Unknown. Using default fallback voice.")
            selected_voice_id = DEFAULT_FALLBACK_VOICE_ID
        elif map_key in character_voice_map:
            selected_voice_id = character_voice_map[map_key]
            print(f"Found existing voice mapping for '{char_name}': {selected_voice_id}")
        else:
            print(f"No existing voice mapping found for '{char_name}'. Assigning new voice...")
            # Determine primary voice pool based on gender
            primary_pool = []
            secondary_pool = []
            if gender == "Male":
                primary_pool = available_voices.get('male', [])
                secondary_pool = available_voices.get('female', [])
            elif gender == "Female":
                primary_pool = available_voices.get('female', [])
                secondary_pool = available_voices.get('male', [])
            else: # Unknown gender - try female first, then male
                print("Gender is Unknown. Trying female voices first, then male.")
                primary_pool = available_voices.get('female', [])
                secondary_pool = available_voices.get('male', [])

            voice_found = False
            # Try primary pool first
            for voice_info in primary_pool:
                voice_id = voice_info.get('id')
                if voice_id and voice_id not in assigned_voice_ids:
                    selected_voice_id = voice_id
                    assigned_voice_ids.add(selected_voice_id) # Track assignment
                    character_voice_map[map_key] = selected_voice_id # Update map
                    map_updated = True
                    voice_found = True
                    print(f"Assigned new {gender if gender != 'Unknown' else 'primary pool'} voice: {voice_info.get('name')} ({selected_voice_id})")
                    break # Found a voice

            # Try secondary pool if primary failed or was empty
            if not voice_found:
                 print(f"No unassigned voice found in the primary pool ({gender if gender != 'Unknown' else 'female'}). Trying secondary pool...")
                 for voice_info in secondary_pool:
                     voice_id = voice_info.get('id')
                     if voice_id and voice_id not in assigned_voice_ids:
                         selected_voice_id = voice_id
                         assigned_voice_ids.add(selected_voice_id) # Track assignment
                         character_voice_map[map_key] = selected_voice_id # Update map
                         map_updated = True
                         voice_found = True
                         print(f"Assigned new secondary pool voice: {voice_info.get('name')} ({selected_voice_id})")
                         break # Found a voice

            # Fallback if no voice could be assigned
            if not voice_found:
                print("Warning: Could not find an unassigned voice in available pools. Using default fallback voice.")
                selected_voice_id = DEFAULT_FALLBACK_VOICE_ID
                # Optional: Decide if you want to map the fallback ID to the character
                # character_voice_map[map_key] = selected_voice_id
                # map_updated = True

        # --- Save Mapping if Updated ---
        if map_updated:
            print(f"Updating character voice mapping file: {args.mapping_file}")
            save_json_data(character_voice_map, args.mapping_file)

        # --- Speak Dialogue ---
        if dialogue:
            speak_dialogue(
                client=eleven_client, # Pass the initialized client
                text=dialogue,
                voice_id=selected_voice_id, # Use the determined voice ID
                model_id=ELEVENLABS_MODEL_ID,
                output_format=ELEVENLABS_OUTPUT_FORMAT,
                output_filename=args.output
            )
        else:
            print("No dialogue found in the screenshot to speak.")

    else:
        print("Failed to get character information from the screenshot.")

    print("\nScript finished.")