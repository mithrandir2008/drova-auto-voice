import os
import google.generativeai as genai
from PIL import Image
import json
import re
import traceback # Import traceback for better error details

# Local imports
import config
from utils import clean_gemini_response

# Configure Gemini API (using key from config)
try:
    genai.configure(api_key=config.GOOGLE_API_KEY)
except Exception as e:
    raise ConnectionError(f"Failed to configure Google Gemini API: {e}")


def resize_image(img: Image.Image, max_height: int) -> Image.Image:
    """
    Resizes a PIL Image object to a maximum height, maintaining aspect ratio.
    """
    orig_width, orig_height = img.size

    if orig_height > max_height:
        print(f"Original image size: {orig_width}x{orig_height}. Resizing to max height {max_height}px...")
        try:
            ratio = max_height / float(orig_height)
            new_width = int(float(orig_width) * ratio)
            new_height = max_height

            # Use Resampling enum for Pillow >= 9.1.0
            resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
            resized_img = img.resize((new_width, new_height), resample_filter)
            print(f"Image successfully resized to {new_width}x{new_height}.")
            return resized_img

        except Exception as e:
            print(f"Warning: Failed to resize image. Using original. Error: {e}")
            return img
    else:
        # print(f"Image height ({orig_height}px) is within limit ({max_height}px). No resize needed.")
        return img


def get_info_from_screenshot(image_path: str) -> dict | None:
    """
    Uploads screenshot to Gemini, returns extracted JSON data including
    dialogue and persona instructions.
    """
    print(f"\nProcessing image: {image_path}")
    try:
        original_img = Image.open(image_path)
        # Use MAX_IMAGE_HEIGHT from config
        img_to_upload = resize_image(original_img, config.MAX_IMAGE_HEIGHT)

    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return None
    except Exception as e:
        print(f"Error opening or resizing image {image_path}: {e}")
        return None

    try:
        # Use GEMINI_MODEL from config
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        print("Sending request to Gemini API...")
        # Use SYSTEM_PROMPT from config
        response = model.generate_content(
            [config.SYSTEM_PROMPT, img_to_upload],
            request_options={"timeout": 120} # Add timeout
        )
        response.resolve() # Ensure completion

        # Check for safety blocks before accessing text
        if not response.candidates:
            safety_info = "N/A"
            block_reason = "Unknown"
            try:
                if response.prompt_feedback:
                    safety_info = getattr(response.prompt_feedback, 'safety_ratings', "N/A")
                    block_reason = getattr(response.prompt_feedback, 'block_reason', "Unknown")
            except Exception:
                pass # Ignore errors trying to get feedback details
            print(f"Error: Gemini response blocked or empty. Reason: {block_reason}, Safety Ratings: {safety_info}")
            # print(f"Full response object:\n{response}") # Uncomment for deep debugging
            return None

        # Safely access text (handle potential variations in response structure)
        response_text = ""
        try:
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                 response_text = response.candidates[0].content.parts[0].text
            else:
                 print("Error: Could not extract text content from Gemini response structure.")
                 # print(f"Full response: {response}") # Uncomment for deep debugging
                 return None

        except (AttributeError, IndexError, Exception) as e:
            print(f"Error: Could not extract text from Gemini response structure: {e}")
            # print(f"Full response: {response}") # Uncomment for deep debugging
            return None

        if not response_text:
             print("Error: Gemini returned empty text content.")
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

            # --- Validate and Standardize ---
            if not isinstance(data, dict) or not all(k in data for k in ["character_name", "gender", "dialogue"]):
                print("Error: Gemini response JSON missing required keys (character_name, gender, dialogue).")
                return None

            # Standardize Gender (ensure correct capitalization)
            gender = data.get("gender", "Unknown").strip().capitalize()
            if gender not in ["Male", "Female", "Unknown"]:
                print(f"Warning: Received non-standard gender '{data['gender']}'. Setting to Unknown.")
                gender = "Unknown"
            data["gender"] = gender

            # Standardize Character Name (handle whitespace, ensure not empty)
            char_name = data.get("character_name", "Unknown").strip()
            if not char_name:
                char_name = "Unknown"
            data["character_name"] = char_name

            # Standardize Dialogue (ensure string, strip whitespace)
            dialogue = str(data.get("dialogue", "")).strip()
            data["dialogue"] = dialogue

            # Standardize Persona Instructions (ensure string, strip whitespace)
            persona = str(data.get("persona_instructions", "")).strip()
            data["persona_instructions"] = persona

            # --- Return Validated Data ---
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