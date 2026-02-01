"""
Kloufi-Scrape Data Storage

Unified data storage interface for both local testing and production.
- Local: Saves to JSON files in junk_test/
- Production: Saves to Elasticsearch
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import re

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import (
    get_environment,
    get_data_path,
    get_elasticsearch_config,
    get_scraper_config,
    ES_INDICES,
    Environment,
)
from scraper.utils.logger import get_logger

logger = get_logger("storage")

# Optional Elasticsearch import
try:
    from elasticsearch import Elasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False
    logger.warning("Elasticsearch not installed. Install with: pip install elasticsearch")


class DataStorage:
    """
    Unified storage interface.
    
    Automatically routes data to the correct storage based on environment:
    - LOCAL: JSON files in junk_test/
    - PRODUCTION/DOCKER: Elasticsearch
    """
    
    def __init__(self, category: str, site_name: Optional[str] = None):
        """
        Initialize storage for a category.
        
        Args:
            category: Category name (immobilier, voiture, etc.)
            site_name: Optional site name for organizing JSON files
        """
        self.category = category
        self.site_name = site_name
        self.config = get_scraper_config()
        self.env = get_environment()
        
        # Elasticsearch client (lazy init)
        self._es_client: Optional[Elasticsearch] = None
        
        # Stats
        self._items_saved = 0
        self._errors = 0
    
    @property
    def es_client(self) -> Optional[Elasticsearch]:
        """Get or create Elasticsearch client."""
        if not ES_AVAILABLE:
            return None
        
        if self._es_client is None and self.config.save_to_elasticsearch:
            es_config = get_elasticsearch_config()
            if es_config.is_configured:
                try:
                    self._es_client = Elasticsearch(
                        [es_config.host],
                        basic_auth=(es_config.username, es_config.password),
                        verify_certs=es_config.verify_certs,
                    )
                    # Test connection
                    if self._es_client.ping():
                        logger.info(f"Connected to Elasticsearch: {es_config.host}")
                    else:
                        logger.error("Elasticsearch ping failed")
                        self._es_client = None
                except Exception as e:
                    logger.error(f"Elasticsearch connection error: {e}")
                    self._es_client = None
        
        return self._es_client
    
    def _get_index_name(self) -> str:
        """Get the Elasticsearch index name for this category."""
        return ES_INDICES.get(self.category, self.category)
    
    def _get_json_path(self) -> Path:
        """Get the JSON output directory."""
        base_path = get_data_path()
        
        if self.site_name:
            path = base_path / self.category / self.site_name
        else:
            path = base_path / self.category
        
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _generate_filename(self, data: Dict[str, Any]) -> str:
        """Generate a unique filename for JSON storage."""
        # Try to extract an identifier
        identifier = "item"
        
        if data.get("numero"):
            identifier = re.sub(r"[^0-9A-Za-z_-]", "", str(data["numero"]))[:64]
        elif data.get("url"):
            # Extract last part of URL
            url_part = os.path.basename(data["url"].rstrip("/"))
            if url_part:
                identifier = re.sub(r"[^0-9A-Za-z_-]", "", url_part)[:64]
        elif data.get("titre"):
            identifier = re.sub(r"[^0-9A-Za-z_-]", "", data["titre"].replace(" ", "-"))[:64]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{timestamp}_{identifier}.json"
    
    def _get_document_id(self, data: Dict[str, Any]) -> str:
        """Get the document ID for Elasticsearch."""
        # Use URL as primary ID
        if data.get("url"):
            return data["url"]
        # Fallback to numero
        if data.get("numero"):
            return str(data["numero"])
        # Generate one
        return f"{self.category}_{datetime.now().timestamp()}"
    
    # ========================================================================
    # SAVE METHODS
    # ========================================================================
    
    def save_to_json_file(self, data: Dict[str, Any]) -> bool:
        """Save data to a JSON file."""
        try:
            path = self._get_json_path()
            filename = self._generate_filename(data)
            filepath = path / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Saved to JSON: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"JSON save error: {e}")
            return False
    
    def save_to_jsonl(self, data: Dict[str, Any], filename: Optional[str] = None) -> bool:
        """Append data to a JSONL file (one JSON object per line)."""
        try:
            path = self._get_json_path()
            
            if filename is None:
                filename = f"{self.category}_{self.site_name or 'data'}.jsonl"
            
            filepath = path / filename
            
            with open(filepath, "a", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
                f.write("\n")
            
            logger.debug(f"Appended to JSONL: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"JSONL save error: {e}")
            return False
    
    def save_to_elasticsearch(self, data: Dict[str, Any]) -> bool:
        """Save data to Elasticsearch."""
        if not self.es_client:
            logger.warning("Elasticsearch not available, skipping ES save")
            return False
        
        try:
            index_name = self._get_index_name()
            doc_id = self._get_document_id(data)
            
            # Handle special cases (like Krello date_depot preservation)
            if data.get("site_origine") == "Krello.net":
                try:
                    existing = self.es_client.get(index=index_name, id=doc_id, ignore=[404])
                    if existing.get("found") and existing["_source"].get("date_depot"):
                        data["date_depot"] = existing["_source"]["date_depot"]
                except Exception:
                    pass
            
            # Handle voiture export field
            if data.get("prix_unit") == "DA" and index_name == "voiture":
                data["export"] = "false"
            
            # Index the document
            result = self.es_client.index(
                index=index_name,
                id=doc_id,
                document=data,
            )
            
            logger.debug(f"Saved to ES [{index_name}]: {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Elasticsearch save error: {e}")
            return False
    
    def save(self, data: Dict[str, Any]) -> bool:
        """
        Save data using the appropriate method based on configuration.
        
        This is the main method to use for storing scraped data.
        """
        success = False
        
        # Add metadata
        if "date_crawl" not in data:
            data["date_crawl"] = datetime.now().isoformat()
        
        # Save to JSON if configured
        if self.config.save_to_json:
            if self.save_to_json_file(data):
                success = True
        
        # Save to Elasticsearch if configured
        if self.config.save_to_elasticsearch:
            if self.save_to_elasticsearch(data):
                success = True
        
        # Track stats
        if success:
            self._items_saved += 1
        else:
            self._errors += 1
            # Fallback: always save to JSON on ES failure
            if not self.config.save_to_json:
                self.save_to_jsonl(data, "failed_items.jsonl")
        
        return success
    
    def save_batch(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Save multiple items.
        
        Returns dict with success/failure counts.
        """
        success_count = 0
        error_count = 0
        
        for item in items:
            if self.save(item):
                success_count += 1
            else:
                error_count += 1
        
        return {
            "success": success_count,
            "errors": error_count,
        }
    
    # ========================================================================
    # STATS
    # ========================================================================
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get storage statistics."""
        return {
            "items_saved": self._items_saved,
            "errors": self._errors,
        }
    
    def reset_stats(self):
        """Reset statistics."""
        self._items_saved = 0
        self._errors = 0


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Cache of storage instances
_storage_cache: Dict[str, DataStorage] = {}


def get_storage(category: str, site_name: Optional[str] = None) -> DataStorage:
    """Get or create a storage instance for a category/site."""
    key = f"{category}:{site_name or ''}"
    if key not in _storage_cache:
        _storage_cache[key] = DataStorage(category, site_name)
    return _storage_cache[key]


def save_item(category: str, data: Dict[str, Any], site_name: Optional[str] = None) -> bool:
    """Convenience function to save a single item."""
    storage = get_storage(category, site_name)
    return storage.save(data)


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test storage
    storage = DataStorage("immobilier", "test_site")
    
    test_data = {
        "titre": "Test Apartment",
        "url": "https://example.com/test-123",
        "prix": "15000000",
        "description": "A test listing",
    }
    
    print(f"Environment: {get_environment().value}")
    print(f"Data path: {get_data_path()}")
    print(f"Save to JSON: {storage.config.save_to_json}")
    print(f"Save to ES: {storage.config.save_to_elasticsearch}")
    
    result = storage.save(test_data)
    print(f"Save result: {result}")
    print(f"Stats: {storage.stats}")
