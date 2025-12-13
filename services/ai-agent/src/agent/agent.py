import os
import google.generativeai as genai
from google.protobuf.json_format import MessageToJson, Parse
from protos.contracts import orchestrator_pb2
import uuid
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models
from minio import Minio

class IncidentAgent:
    def __init__(self):
        print("Initializing Gemini Analyst...")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY not set. Agent will fail to generate.")
        
        genai.configure(api_key=api_key)
        # self.model = genai.GenerativeModel('gemini-2.0-flash-exp') # Using 2.0 Flash as equivalent to 2.5 request if not available, or keep generic if user insists. 
        
        
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Initialize RAG (Qdrant)
        self.qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        self.qdrant = QdrantClient(host=self.qdrant_host, port=6333)
        self.collection_name = "sre_knowledge"
        
        # Initialize MinIO
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000") # internal docker usage
        self.minio_access = os.getenv("MINIO_ROOT_USER", "minioadmin")
        self.minio_secret = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
        self.bucket_name = "runbooks"
        
        self.minio_client = Minio(
            self.minio_endpoint,
            access_key=self.minio_access,
            secret_key=self.minio_secret,
            secure=False
        )
        
        print(f"Agent initialized. RAG connected to {self.qdrant_host}, Docs at {self.minio_endpoint}")

    def analyze(self, event: orchestrator_pb2.DomainEvent) -> orchestrator_pb2.Decision:
        # 1. Build Context (Vector Search + MinIO Fetch)
        context = self._build_context(event)
        
        # 2. Key Step: Prompt Engineering for SRE behavior
        prompt = self._build_prompt(event, context)
        
        try:
            # 3. Call Gemini
            response = self.model.generate_content(prompt)
            
            # 4. Parse Structured Output (JSON)
            return self._parse_decision(response.text, event)
            
        except Exception as e:
            print(f"Gemini generation failed: {e}")
            return self._fallback_decision(event, str(e))

    def _build_context(self, event):
        try:
            # Create a search query from the event
            query_text = f"{event.service_name} {event.original_event.raw_payload}"
            
            # Embed the query
            print(f"RAG: Embedding query: {query_text[:50]}...")
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=query_text,
                task_type="retrieval_query"
            )
            embedding = result['embedding']
            
            # Search Qdrant
            print("RAG: Searching Knowledge Base...")
            search_response = self.qdrant.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=1
            )
            
            if not search_response.points:
                return "No specific runbook found. Use general troubleshooting."
                
            hit = search_response.points[0]
            print(f"RAG: Found runbook '{hit.payload.get('title')}' (Score: {hit.score})")
            
            # Fetch content from MinIO
            filename = hit.payload.get('minio_path')
            bucket = hit.payload.get('minio_bucket', self.bucket_name)
            
            print(f"RAG: Fetching content for {filename} from MinIO...")
            try:
                response = self.minio_client.get_object(bucket, filename)
                content = response.read().decode('utf-8')
                response.close()
                response.release_conn()
            except Exception as e:
                print(f"MinIO Fetch Failed: {e}")
                return "Runbook found but failed to retrieve content."
            
            return f"""
            RELEVANT RUNBOOK FOUND:
            Title: {hit.payload.get('title')}
            Content:
            {content}
            """
            
        except Exception as e:
            print(f"RAG Failed: {e}")
            return "Context retrieval failed."

    def _build_prompt(self, event, context):
        return f"""
        You are a Senior Site Reliability Engineer (SRE). 
        Analyze the following incident and propose remediation actions.
        
        INCIDENT DETAILS:
        ID: {event.event_id}
        Service: {event.service_name}
        Domain: {event.domain}
        
        CONTEXT (RUNBOOKS):
        {context}
        
        RAW ALERT DATA:
        {event.original_event.raw_payload}

        YOUR TASK:
        1. Identify the root cause based on the runbook and alert data.
        2. Propose safe remediation actions.
        
        STRICT ACTION SCHEMA (YOU MUST FOLLOW THESE PARAMETERS):
        - Action: "restart_pod"
          Target: Pod Name (e.g., "kafka-ingest-123")
          Params: {{ "namespace": "default" }}
          
        - Action: "scale_deployment"
          Target: Deployment Name (e.g., "deployment/kafka-ingest")
          Params: {{ "replicas": "integer_string" }} OR {{ "replicas_increment": "integer_string" }}
          (DO NOT use 'replicas_increase', 'replicas_increase_by', or any other variation. ONLY 'replicas' or 'replicas_increment'.)
          
        - Action: "rolling_restart_deployment"
          Target: Deployment Name (e.g., "deployment/kafka-ingest")
          Params: {{ "namespace": "default" }}

        3. Provide a confidence score (0.0 to 1.0).

        OUTPUT FORMAT:
        Return ONLY valid JSON matching this structure:
        {{
            "analysis": "string explanation",
            "confidence_score": float,
            "proposed_actions": [
                {{
                    "action_type": "string",
                    "target": "string (resource name)",
                    "params": {{ "key": "value" }},
                    "reasoning": "string"
                }}
            ]
        }}
        """

    def _parse_decision(self, llm_output, event):
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        
        try:
            # Clean markup if present
            clean_json = llm_output.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            decision.analysis = data.get("analysis", "No analysis provided")
            decision.confidence_score = data.get("confidence_score", 0.0)
            
            for action_data in data.get("proposed_actions", []):
                action = decision.proposed_actions.add()
                action.action_id = str(uuid.uuid4())
                action.decision_id = decision.decision_id
                action.action_type = action_data.get("action_type", "unknown")
                action.target = action_data.get("target", "unknown")
                action.reasoning = action_data.get("reasoning", "")
                
                # Handle params map
                if "params" in action_data:
                    for k, v in action_data["params"].items():
                        action.params[k] = str(v)
                        
        except Exception as e:
            print(f"Failed to parse LLM JSON: {e}")
            decision.analysis = f"Parse Error: {e}. Raw Output: {llm_output}"
            
        return decision

    def _fallback_decision(self, event, error_msg):
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Agent failed: {error_msg}"
        decision.confidence_score = 0.0
        return decision
