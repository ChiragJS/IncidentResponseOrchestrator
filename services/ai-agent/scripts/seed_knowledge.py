import os
import google.generativeai as genai
from qdrant_client import QdrantClient
from qdrant_client.http import models
import uuid

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "sre_knowledge"
API_KEY = os.getenv("GEMINI_API_KEY")

# Sample Knowledge Base (Runbooks)
RUNBOOKS = [
    {
        "title": "Kubernetes PodCrashLoopBackOff",
        "content": """
        Issue: Pod status is CrashLoopBackOff.
        Symptoms: Pod starts, crashes effectively immediately, and restarts.
        Common Causes:
        1. Application panic/crash on startup (bug).
        2. Missing environment variables or configuration.
        3. Liveness probe failure (misconfigured).
        4. OOMKilled (Out of Memory) - check if exit code is 137.
        Remediation Steps:
        1. Check logs: `kubectl logs <pod> --previous`
        2. Describe pod: `kubectl describe pod <pod>` to look for OOMKilled.
        3. Check events: `kubectl get events`
        4. If OOM, increase memory limits.
        5. If app crash, revert to previous stable image tag.
        """
    },
    {
        "title": "Database Connection Timeout",
        "content": """
        Issue: Application cannot connect to Database (Timeout).
        Symptoms: Log errors "Connection timed out", 500 errors.
        Common Causes:
        1. Database is down or restarting.
        2. Network policy blocking access.
        3. Connection pool exhaustion.
        4. Wrong credentials.
        Remediation Steps:
        1. Verify DB status: Check if DB pod/service is running.
        2. Check connectivity: `nc -zv <db-host> <port>` from app pod.
        3. Check active connections: If full, restart app or increase pool size.
        4. Check credentials in Secret.
        """
    },
    {
        "title": "High CPU Usage Alert",
        "content": """
        Issue: CPU usage > 90% for sustained period.
        Symptoms: Slow response times, latency spikes.
        Remediation Steps:
        1. Identify top consumers: `top` or monitoring dashboard.
        2. Is it expected load? If yes, HPA should handle it.
        3. If no HPA, manually scale up: `kubectl scale deployment <name> --replicas=<n+1>`
        4. Check for infinite loops in code (recent deployment).
        5. Capture profile (pprof) if possible.
        """
    }
]

def seed():
    print("Connecting to Qdrant...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    genai.configure(api_key=API_KEY)
    
    # 1. Recreate Collection
    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    )
    print(f"Collection '{COLLECTION_NAME}' created.")

    # 2. Embed and Upload
    points = []
    for i, doc in enumerate(RUNBOOKS):
        print(f"Embedding: {doc['title']}...")
        
        # Use Gemini for embeddings
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=doc["content"],
            task_type="retrieval_document",
            title=doc["title"]
        )
        embedding = result['embedding']
        
        points.append(models.PointStruct(
            id=i,
            vector=embedding,
            payload=doc
        ))

    # 3. Upsert
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    print(f"Successfully seeded {len(points)} documents!")

if __name__ == "__main__":
    if not API_KEY:
        print("Error: GEMINI_API_KEY is not set.")
    else:
        seed()
