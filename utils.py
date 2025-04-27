import re

def clean_gemini_response(text: str) -> str:
    """Removes potential markdown formatting around JSON."""
    # Look for ```json ... ``` block
    match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Look for any {...} block as a fallback
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Return stripped text if no JSON block found (might be just the JSON)
    return text.strip()

# Add any other general utility functions here if needed