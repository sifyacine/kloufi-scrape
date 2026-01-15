from datetime import datetime
from pydantic import BaseModel
from typing import List, Dict, Any

class Tv(BaseModel):
    """Modèle représentant un téléviseur avec des champs adaptés au format souhaité."""

    site_origine: str = "Ajini.com"
    garantie: str = ""
    garantie_unit: List[str] = []
    titre: str = ""
    description: str = ""
    couleur: str = ""
    prix_unit: str = "DA"
    prix_dec: float = 0.0  # Eviter None
    etat: str = "true"
    as_photo: str = ""
    date_depot: str = datetime.now().isoformat()
    date_crawl: str = datetime.now().isoformat(),
    date_verif: str = datetime.now().isoformat(),
    modele: str = ""
    taille_ecran: str = ""
    dimension: str = ""
    poid_unit: str = ""
    poid: float = 0.0  # Devrait être un float
    images: List[str] = []
    categorie: str = ""
    category: str = "multimedia"
    marque: str = ""
    type_ecran: str = ""
    resolution: str = ""
    url: str = ""
    transaction: str = ""
    livraison: str = ""
    status: int = 200  # Par défaut 200 (succès)

    # Champs supplémentaires
    as_prix: str = ""
    m_interne: str = ""
    m_interne_unit: str = ""

    # Stocker toutes les autres spécifications inconnues
    specs: Dict[str, Any] = {}
