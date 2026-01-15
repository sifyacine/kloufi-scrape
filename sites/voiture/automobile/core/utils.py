import json
import os
from .config import Config

def save_data(data, filename):
    """
    Saves data to a JSON file in the data directory.
    
    Args:
        data (list or dict): The data to save.
        filename (str): The name of the file (e.g., 'autobessah_data.json').
    """
    Config.ensure_dirs()
    filepath = os.path.join(Config.DATA_DIR, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Data successfully saved to {filepath}")
    except Exception as e:
        print(f"Error saving data to {filepath}: {e}")

def clean_text(text):
    """
    Basic text cleaning helper.
    """
    if text:
        return text.strip()
    return ""
