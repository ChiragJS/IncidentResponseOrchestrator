
import os
import sys
import glob
import logging
from minio import Minio
from qdrant_client import QdrantClient
from qdrant_client.http import models
import google.generativeai as genai
from pypdf import PdfReader

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
BUCKET_NAME = "runbooks"

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = 6333
COLLECTION_NAME = "sre_knowledge"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY is required")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

def init_minio():
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)
        logging.info(f"Created bucket '{BUCKET_NAME}'")
    return client

def init_qdrant():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    # Re-create collection for fresh start
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    )
    logging.info(f"Created collection '{COLLECTION_NAME}'")
    return client

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        try:
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logging.error(f"Failed to read PDF {file_path}: {e}")
            return ""
    elif ext in ['.md', '.txt', '.json', '.yaml', '.yml']:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Failed to read text file {file_path}: {e}")
            return ""
    else:
        logging.warning(f"Unsupported file type: {ext}")
        return ""

def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest_runbooks.py <directory_with_docs>")
        sys.exit(1)

    doc_dir = sys.argv[1]
    
    minio_client = init_minio()
    qdrant_client = init_qdrant()
    
    files = glob.glob(os.path.join(doc_dir, "*"))
    logging.info(f"Found {len(files)} files in directory")

    points = []
    
    for idx, file_path in enumerate(files):
        filename = os.path.basename(file_path)
        
        # Skip hidden files
        if filename.startswith('.'):
            continue
            
        logging.info(f"Processing {filename}...")

        # 1. Extract Text First (Fail fast if empty/unsupported)
        content = extract_text(file_path)
        if not content.strip():
            logging.warning(f"Skipping {filename} (empty or unsupported)")
            continue
            
        # 2. Upload to MinIO
        try:
            minio_client.fput_object(BUCKET_NAME, filename, file_path)
            logging.info(f"Uploaded {filename} to MinIO")
        except Exception as e:
            logging.error(f"Failed to upload {filename}: {e}")
            continue

        # Generate embedding
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=content,
            task_type="retrieval_document"
        )
        embedding = result['embedding']

        # 3. Prepare Vector Point
        point = models.PointStruct(
            id=idx,
            vector=embedding,
            payload={
                "filename": filename,
                "minio_bucket": BUCKET_NAME,
                "minio_path": filename,
                "title": filename
            }
        )
        points.append(point)

    # 4. Index in Qdrant
    if points:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        logging.info(f"Indexed {len(points)} documents in Qdrant")

if __name__ == "__main__":
    main()
