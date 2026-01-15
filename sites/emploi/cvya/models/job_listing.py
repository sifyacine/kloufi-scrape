from datetime import datetime, date
from typing import List
from pydantic import BaseModel, HttpUrl


class JobListing(BaseModel):
    """
    Represents the data structure of a job listing.
    """

    date_crawl: datetime
    url: HttpUrl
    site_origine: str
    titre: str
    niveau: List[str]
    numero: str
    date_depot: date
    transaction: str
    contrat: str
    diplome: List[str]
    diplome_src: List[str]
    domaine: str
    description: str
    employeur: str
    poste: str
    adresse: str
    wilaya: str
    status: int
    date_verif: datetime
    images: List[str]
    as_photo: str
    prix: str
    prix_unit: str
    prix_dec: str
    as_prix: str
    vehicle: bool
