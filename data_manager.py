import json
import os

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
    except Exception as e:
        print(f"Warning: An unexpected error occurred loading {filepath}: {e}. Starting with default data.")
        return default

def save_json_data(data: dict, filepath: str):
    """Safely saves data to a JSON file."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        # print(f"Data successfully saved to {filepath}") # Optional: uncomment for verbose saving
    except IOError as e:
        print(f"Error: Could not write to file {filepath}. Reason: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving to JSON {filepath}: {e}")