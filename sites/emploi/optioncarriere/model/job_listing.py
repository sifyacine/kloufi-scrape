from datetime import datetime
from pydantic import BaseModel
from typing import List

class JobListing(BaseModel):
    """Model representing a job listing with required fields."""
    
    date_crawl: str = datetime.now().isoformat()
    url: str = ""
    site_origine: str = ""
    titre: str = ""
    niveau: List[str] = []
    numero: str = ""
    date_depot: str = ""
    transaction: str = ""
    contrat: str = ""
    diplome: List[str] = []
    diplome_src: List[str] = []
    domaine: str = ""
    description: str = ""
    employeur: str = ""
    poste: str = ""
    adresse: str = ""
    wilaya: str = ""
    status: int = 200
    date_verif: str = datetime.now().isoformat()
    images: List[str] = []
    as_photo: str = ""
    prix: str = ""
    prix_unit: str = ""
    prix_dec: str = ""
    as_prix: str = ""
    vehicle: bool = False
