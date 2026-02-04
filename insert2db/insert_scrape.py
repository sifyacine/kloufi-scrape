"""
Kloufi-Scrape Elasticsearch Insert Module

Handles inserting scraped data into Elasticsearch.
Updated to use centralized configuration and storage.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import from core storage (preferred)
try:
    from core.storage import DataStorage, get_storage, save_item
    USE_CORE_STORAGE = True
except ImportError:
    USE_CORE_STORAGE = False

# Fallback Elasticsearch client
try:
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

# Configuration
es_host = os.getenv('ELASTICSEARCH_HOST', 'http://192.168.9.222:9200')
es_username = os.getenv('ELASTICSEARCH_USERNAME', 'elastic')
es_password = os.getenv('ELASTICSEARCH_PASSWORD', '')

# Lazy-initialized Elasticsearch client
_es_client: Optional[Elasticsearch] = None


def get_es_client() -> Optional[Elasticsearch]:
    """Get or create Elasticsearch client."""
    global _es_client
    
    if not ES_AVAILABLE:
        return None
    
    if _es_client is None and es_password:
        try:
            _es_client = Elasticsearch(
                [es_host],
                basic_auth=(es_username, es_password),
            )
            if not _es_client.ping():
                print(f"Warning: Elasticsearch ping failed for {es_host}")
                _es_client = None
        except Exception as e:
            print(f"Elasticsearch connection error: {e}")
            _es_client = None
    
    return _es_client


def insert_data_to_es(data: Dict[str, Any], index_name: str = None, index: str = None) -> bool:
    """
    Insert data into Elasticsearch.
    
    Args:
        data: Dictionary of data to insert
        index_name: Elasticsearch index name (category)
        index: Alias for index_name (for backward compatibility)
        
    Returns:
        True if successful, False otherwise
    """
    # Support both 'index' and 'index_name' parameters
    if index_name is None and index is not None:
        index_name = index
    elif index_name is None and index is None:
        raise ValueError("Either 'index_name' or 'index' must be provided")
    # Prefer using core storage if available
    if USE_CORE_STORAGE:
        try:
            return save_item(index_name, data)
        except Exception as e:
            print(f"Core storage error, falling back: {e}")
    
    # Fallback to direct Elasticsearch insert
    es = get_es_client()
    if not es:
        print("Elasticsearch not available, data not saved")
        return False
    
    try:
        # Determine document ID
        doc_id = data.get('url') or data.get('numero') or None
        
        # Handle special cases
        if data.get("site_origine") == "Krello.net":
            try:
                existing = es.get(index=index_name, id=doc_id, ignore=[404])
                if existing.get('found'):
                    # Preserve existing date_depot
                    if "date_depot" in existing["_source"]:
                        data["date_depot"] = existing["_source"]["date_depot"]
            except Exception:
                pass
        
        # Handle voiture export field
        if data.get("prix_unit") == "DA" and index_name == "voiture":
            data["export"] = "false"
        
        # Insert document
        result = es.index(index=index_name, id=doc_id, document=data)
        print(f"Data inserted to {index_name}: {result.get('result', 'unknown')}")
        return True
        
    except Exception as e:
        print(f"Error inserting data into Elasticsearch: {str(e)}")
        return False


def bulk_insert_to_es(docs: list, index_name: str) -> bool:
    """
    Bulk insert a list of documents into Elasticsearch.
    Args:
        docs: List of dictionaries to insert
        index_name: Elasticsearch index name
    Returns:
        True if successful, False otherwise
    """
    es = get_es_client()
    if not es:
        print("Elasticsearch not available, data not saved")
        return False
    actions = [
        {
            "_index": index_name,
            "_id": doc.get('url') or doc.get('numero'),
            "_source": doc
        }
        for doc in docs
    ]
    try:
        success, _ = bulk(es, actions)
        print(f"Bulk inserted {success} documents to {index_name}")
        return True
    except Exception as e:
        print(f"Bulk insert error: {e}")
        return False


# Alias for backward compatibility
insert_to_elasticsearch = insert_data_to_es


if __name__ == "__main__":
    # Test connection
    es = get_es_client()
    if es:
        print(f"Connected to Elasticsearch: {es_host}")
        print(f"Cluster info: {es.info()}")
    else:
        print("Elasticsearch not configured or not available")
