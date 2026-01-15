import os
import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Load environment variables from .env file
load_dotenv()
es_host = os.getenv('ELASTICSEARCH_HOST', 'http://elastic1:9200')
es_username = os.getenv('ELASTICSEARCH_USERNAME', 'elastic')
es_password = os.getenv('ELASTICSEARCH_PASSWORD', '')

es = Elasticsearch(
    [es_host],
    http_auth=(es_username, es_password),
)

def insert_data_to_es(data, index_name):
    try:        
        if data["site_origine"] == "Krello.net":
            # Search by id (url)
            try:
                existing_item = es.get(index=index_name, id=data['url'], ignore=404)                
                # If the document exists
                if existing_item['found']:
                    # Only keep the existing `date_depot` if it exists
                    if "date_depot" in existing_item["_source"]:
                        data["date_depot"] = existing_item["_source"]["date_depot"]
                    
                    # Insert or update document (without changing date_depot)
                    insert = es.index(index=index_name, id=data['url'], body=data)
                    print("Insert", insert)
                else:
                    # If the document does not exist, insert it normally
                    insert = es.index(index=index_name, id=data['url'], body=data)
                    print("Insert (new record)", insert)

            except Exception as e:
                insert = es.index(index=index_name, id=data['url'], body=data)

        else:
            if data["prix_unit"] == "DA" and index_name == "voiture":
                data["export"] = "false"
            insert = es.index(index=index_name, id=data['url'], body=data)
            print("Data inserted", insert)

    except Exception as e:
        print(f"Error inserting data into Elasticsearch: {str(e)}")

    except requests.exceptions.RequestException as e:
        print(f"Error inserting data into Elasticsearch: {str(e)}")
