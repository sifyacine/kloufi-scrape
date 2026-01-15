normalization_and_utils = {
    "global_utils": {
        "traitement_prix": "Converts price strings with units (Millions, Milliards) into absolute float values.",
        "parse_date": "Parses various date formats (%d/%m/%Y %H:%M:%S, %d/%m/%Y, etc.) into ISO-8601 strings.",
        "extract_text_or_default": "Safely extracts text using CSS selectors with a fallback default value.",
        "save_to_json": "Appends scraped items as JSON lines to a local file (.jsonl).",
        "insert_data_to_es": "Standardized function to push structured data into Elasticsearch indexes.",
        "str_to_float": "Removes non-numeric characters and converts strings to floats (handles commas/dots).",
        "str_to_int": "Type safety helper to convert strings to integers.",
        "avec_sans_photo": "Utility to label an item as 'Avec photo' or 'Sans photo' based on image list length.",
        "avec_sans_prix": "Utility to label an item as 'Avec prix' or 'Sans prix' based on price value."
    },
    "immobilier": {
        "convert_property_type": "Normalizes property types (Villa, Appartement, Local, etc.) from raw strings.",
        "normalize_pieces": "Extracts the number of rooms/pieces from strings like 'F3', '3 pièces', or '4'.",
        "detect_transaction_from_title": "Infers transaction types (Vente, Location, etc.) by searching for keywords in the ad title.",
        "extract_bien_transaction_from_breadcrumbs": "Validation logic that uses site breadcrumbs to determine the property type and transaction.",
        "wilaya_commune_split": "Logic to split 'Alger - El Achour' into Wilaya (Alger) and Commune (El Achour)."
    },
    "voiture": {
        "normalize_energie": "Standardizes fuel types (Essence, Diesel, GPL, Hybride, Electrique) from various naming conventions.",
        "normalize_transmission": "Standardizes gearbox types (Automatique, Manuelle, Semi-Automatique).",
        "extract_model": "Logic to extract the car model by using the brand name as a reference point in the title.",
        "annee_extraction": "Regex to isolate the 4-digit year from complex date/text strings.",
        "kms_normalization": "Splits mileage values from units (KM) and handles whitespace/formatting."
    },
    "emploi": {
        "normalize_diplome": "Standardizes varied degree names (Licence, Master, Bac+2) into a unified set of education levels.",
        "extract_wilaya": "Isolates the Wilaya from comma-separated address strings or special cases like 'Télétravail'.",
        "extract_salary": "Uses regex to find and normalize salary figures from job description text when not explicitly provided.",
        "niveau_poste_normalization": "Handles multi-valued experience levels (e.g., 'Confirmé | Senior')."
    },
    "electromenager": {
        "process_price": "Specialized cleaning for e-commerce prices (removes DZD, Da, \xa0, etc.).",
        "categorie_normalization": "Maps specific product types to broader category buckets (e.g., 'Téléphone' -> 'Smartphones').",
        "garantie_normalization": "Splits warranty periods into value and unit (Mois, Ans)."
    },
    "multimedia": {
        "os_normalization": "Extracts and standardizes OS names and versions (Windows 11, Android 13, etc.).",
        "ram_normalization": "Regex to pull RAM capacity and units (GO, GB) from technical specs.",
        "storage_normalization": "Isolates internal storage/disk capacity (e.g., '256 Go SSD').",
        "processor_normalization": "Extracts core counts (Quad-Core, Octa-Core) and clock speeds (GHz).",
        "camera_normalization": "Pulls Megapixel (MP) values for front and rear cameras.",
        "dimension_normalization": "Formats complex dimension strings (Length x Width x Height)."
    }
}
