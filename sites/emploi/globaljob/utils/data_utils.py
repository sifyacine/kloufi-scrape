# data_utils.py
import csv
import json
import os
from models.job_listing import JobListing

CATEGORY_MAP = {
    "Commerce & Vente": "Commercial & Marketing",
    "Industrie & Production": "Industries",
    "Informatique & Internet": "IT & Développement",
    "Transport & Chauffeurs": "Logistique & Transport",
    "Medecine & Santé": "Santé & Médical",
    "Autre": "Divers"
}

def traitement_prix(salaire_dec, salaire_unit):
    if salaire_dec and salaire_unit:
        try:
            salaire_dec = float(salaire_dec)
            multiplier = 10000 if salaire_unit == "Millions" else 10000000 if salaire_unit == "Milliards" else 1
            return salaire_dec * multiplier
        except ValueError:
            return None
    return None

def map_diplome(diplome):
    mapping = {
        "Niveau secondaire": "Diplôme de collège",
        "Baccalauréat": "Bac",
        "Bac +2": "Diplôme universitaire",
        "Licence": "Diplôme universitaire",
        "Bac + 3": "Diplôme universitaire",
        "Master 1": "Master",
        "Master 2": "Master",
        "Ingéniorat": "Diplôme universitaire",
        "Certification": "Diplôme professionnel / technique"
    }
    return mapping.get(diplome, diplome)

def traitement_wilaya(address):
    try:
        return address.split(',')[0].strip()
    except Exception:
        return "N/A"

def normalize_experience(exp_str):
    mapping = {
        "Débutant < 2 ans": "Jeune Diplômé",
        "Jeune Diplômé": "Jeune Diplômé",
        "Expérience entre 2 ans et 5 ans": "Débutant / Junior",
        "Expérience entre 5 ans et 10 ans": "Confirmé / Expérimenté",
        "Expérience > 10 ans": "Confirmé / Expérimenté",
        "Etudiant": "Etudiant"
    }
    return mapping.get(exp_str.strip(), exp_str)

def traitement_domaine(domaine):
    return CATEGORY_MAP.get(domaine, domaine)

def format_job_data(job):
    required_fields = [
        "titre", "description", "salaire_dec", "salaire_unit", "adresse", "wilaya",
        "experience", "domaine", "diplome", "type_contrat", "date_publication", "url"
    ]
    
    formatted_job = {field: job.get(field, "") for field in required_fields}
    formatted_job["wilaya"] = traitement_wilaya(job.get("adresse", ""))
    formatted_job["salaire"] = traitement_prix(job.get("salaire_dec"), job.get("salaire_unit"))
    formatted_job["experience"] = normalize_experience(job.get("experience", ""))
    formatted_job["domaine"] = traitement_domaine(job.get("domaine", ""))
    formatted_job["diplome"] = map_diplome(job.get("diplome", ""))
    
    return formatted_job

def save_jobs_to_csv(jobs: list, filename: str):
    if not jobs:
        print("No jobs to save.")
        return
    try:
        # Use model_fields if available; fallback to __fields__ for compatibility
        fieldnames = list(JobListing.model_fields.keys()) if hasattr(JobListing, "model_fields") else list(JobListing.__fields__.keys())
        with open(filename, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for job in jobs:
                writer.writerow(format_job_data(job))
        print(f"Saved {len(jobs)} jobs to '{filename}'.")
    except Exception as e:
        print(f"Error saving to CSV: {e}")


def save_jobs_to_json(jobs, filename):
    """Save job listings to a JSON file without reformatting."""
    seen_titles = set()
    processed_jobs = []
    
    for job in jobs:
        titre = job.get("titre")
        if titre and titre not in seen_titles:
            seen_titles.add(titre)
            processed_jobs.append(job)
    
    # Create directories if they don't exist
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(processed_jobs, f, indent=4, ensure_ascii=False)
        print(f"✅ Successfully saved {len(processed_jobs)} jobs to {filename}")
    except Exception as e:
        print(f"❌ Failed to save JSON: {e}")