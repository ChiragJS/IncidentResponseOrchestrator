import os
import subprocess
import time
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
        
        # Alert deduplication cache - prevents duplicate Gemini calls for same incident
        self._alert_cache = {}  # {cache_key: last_processed_timestamp}
        self._cache_ttl = 300  # 5 minutes - skip duplicate alerts within this window
        
        print(f"Agent initialized. RAG connected to {self.qdrant_host}, Docs at {self.minio_endpoint}")

    # Security whitelist - only read-only kubectl commands allowed
    ALLOWED_COMMANDS = [
        "kubectl get",
        "kubectl describe",
        "kubectl logs",
        "kubectl top",
    ]

    # Ignore alerts from system components
    IGNORED_SERVICE_PATTERNS = [
        "init-runbooks",
        "kube-state-metrics",
        "orchestrator-",  # All orchestrator system pods
        "prometheus",
        "alertmanager",
        "grafana",
        "loki",
        "promtail",
        "qdrant",
        "minio",
        "kafka",
    ]

    def _should_ignore_alert(self, service_name):
        """Check if this alert should be ignored (system components)."""
        for pattern in self.IGNORED_SERVICE_PATTERNS:
            if pattern in service_name:
                return True
        return False

    def analyze(self, event: orchestrator_pb2.DomainEvent) -> orchestrator_pb2.Decision:
        # Filter out system component alerts
        if self._should_ignore_alert(event.service_name):
            print(f"IGNORED: Skipping system component alert for {event.service_name}")
            return self._ignored_decision(event)
        
        # Check for duplicate alerts (rate limiting)
        cache_key = f"{event.service_name}:{event.domain}"
        current_time = time.time()
        
        if cache_key in self._alert_cache:
            last_processed = self._alert_cache[cache_key]
            time_since = current_time - last_processed
            if time_since < self._cache_ttl:
                print(f"RATE LIMIT: Skipping duplicate alert for {event.service_name} (processed {time_since:.0f}s ago, TTL={self._cache_ttl}s)")
                return self._cached_decision(event)
        
        # Update cache
        self._alert_cache[cache_key] = current_time
        
        # Clean up old cache entries
        self._alert_cache = {k: v for k, v in self._alert_cache.items() 
                            if current_time - v < self._cache_ttl * 2}
        
        print(f"PROCESSING: New alert for {event.service_name} (cache key: {cache_key})")
        
        # 1. Build Context (Vector Search + MinIO Fetch)
        context = self._build_context(event)
        
        # 2. PHASE 1: Ask Gemini what diagnostics to run based on runbook
        diagnostic_commands = self._get_diagnostic_commands(event, context)
        
        # 3. Execute approved diagnostic commands
        diagnostics = self._run_diagnostics(event, diagnostic_commands)
        
        # 4. PHASE 2: Prompt Engineering for SRE behavior with diagnostic results
        prompt = self._build_prompt(event, context, diagnostics)
        
        try:
            # 5. Call Gemini for final analysis
            response = self.model.generate_content(prompt)
            print("RATE LIMIT: Sleeping 20s after analysis API call...")
            time.sleep(20)
            
            # 6. Parse Structured Output (JSON)
            return self._parse_decision(response.text, event)
            
        except Exception as e:
            print(f"Gemini generation failed: {e}")
            return self._fallback_decision(event, str(e))

    def _cached_decision(self, event):
        """Return a cached/skipped decision for duplicate alerts."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Alert for {event.service_name} was recently processed. Skipping to prevent API rate limiting."
        decision.confidence_score = 0.0  # Indicates no analysis was performed
        return decision

    def _ignored_decision(self, event):
        """Return a skip decision for ignored system component alerts."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Alert for {event.service_name} ignored (system component)."
        decision.confidence_score = 0.0
        return decision

    def _get_diagnostic_commands(self, event, context):
        """PHASE 1: Ask Gemini to pick diagnostic commands from runbook."""
        
        # Debug: print the full metadata
        print(f"DEBUG: event.original_event.metadata = {dict(event.original_event.metadata)}")
        print(f"DEBUG: event.service_name = {event.service_name}")
        
        namespace = event.original_event.metadata.get("namespace", "default")
        pod_name = event.original_event.metadata.get("pod", "") or event.original_event.metadata.get("service", "") or event.service_name
        
        print(f"DEBUG: Extracted pod_name={pod_name}, namespace={namespace}")
        
        prompt = f"""You are an SRE assistant. Based on the runbook and alert, output ONLY the kubectl diagnostic commands to run.
        
ALERT CONTEXT:
Service: {event.service_name}
Namespace: {namespace}
Raw Alert: {event.original_event.raw_payload}

RUNBOOK CONTENT:
{context}

INSTRUCTIONS:
1. Suggest up to 5 read-only kubectl commands (get, describe, logs, top) to diagnose the issue.
2. If the alert indicates a crash loop or missing pod, include commands to inspect the Deployment or ReplicaSet as well.
3. Use the namespace '{namespace}' for all commands.
4. Output valid JSON only.

OUTPUT SCHEMA:
{{
    "commands": [
        "kubectl describe pod {pod_name} -n {namespace}",
        "kubectl logs deployment/{event.service_name} -n {namespace} --all-containers"
    ]
}}
"""

        try:
            response = self.model.generate_content(prompt)
            print("RATE LIMIT: Sleeping 20s after diagnostic API call...")
            time.sleep(20)
            
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            commands = data.get("commands", [])
            
            # Validate against whitelist
            validated = []
            for cmd in commands[:5]:
                if any(cmd.strip().startswith(allowed) for allowed in self.ALLOWED_COMMANDS):
                    validated.append(cmd)
                    print(f"DIAGNOSTICS: Approved command: {cmd}")
                else:
                    print(f"DIAGNOSTICS: BLOCKED command (not in whitelist): {cmd}")
            
            return validated
            
        except Exception as e:
            print(f"DIAGNOSTICS: Failed to get commands from Gemini: {e}")
            # Fallback
            return [f"kubectl describe pod {pod_name} -n {namespace}"]

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
            
            # Rate limit workaround
            print("RATE LIMIT: Sleeping 20s after embedding API call...")
            time.sleep(20)
            
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

    def _resolve_pod_name(self, name, namespace):
        """(Deprecated) Gemini should invoke correct commands directly."""
        return name

    def _run_diagnostics(self, event, commands):
        """Execute kubectl commands chosen by Gemini (validated against whitelist)."""
        diagnostics = []
        
        print(f"DIAGNOSTICS: Executing {len(commands)} commands...")
        
        for cmd in commands:
            # Double-check whitelist
            if not any(cmd.strip().startswith(allowed) for allowed in self.ALLOWED_COMMANDS):
                print(f"DIAGNOSTICS: BLOCKED (security): {cmd}")
                continue
            
            # Directly use the command from Gemini (User Request: No replacements)
            resolved_cmd = cmd
            
            try:
                print(f"DIAGNOSTICS: Running: {resolved_cmd}")
                
                # Execute the command
                result = subprocess.run(
                    resolved_cmd.split(),
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0 and result.stdout:
                    # Truncate long output
                    output = result.stdout[:3000] if len(result.stdout) > 3000 else result.stdout
                    diagnostics.append(f"=== {resolved_cmd} ===\n{output}")
                    
                    # Log for visibility
                    print(f"\n--- {resolved_cmd} ---")
                    print(output[:1500])  # Log first 1500 chars
                    print("--- end ---\n")
                elif result.stderr:
                    diagnostics.append(f"=== {resolved_cmd} ===\nError: {result.stderr[:500]}")
                    print(f"DIAGNOSTICS: Command failed: {result.stderr[:200]}")
                    
            except subprocess.TimeoutExpired:
                diagnostics.append(f"=== {resolved_cmd} ===\nTimeout after 30s")
                print(f"DIAGNOSTICS: Timeout: {resolved_cmd}")
            except Exception as e:
                diagnostics.append(f"=== {resolved_cmd} ===\nFailed: {e}")
                print(f"DIAGNOSTICS: Error: {e}")
        
        if not diagnostics:
            return "No diagnostic information could be gathered."
        
        return "\n\n".join(diagnostics)

    def _build_prompt(self, event, context, diagnostics=""):
        return f"""
        You are a Senior Site Reliability Engineer (SRE). 
        Analyze the following incident and propose remediation actions.
        
        INCIDENT DETAILS:
        ID: {event.event_id}
        Service: {event.service_name}
        Domain: {event.domain}
        
        CONTEXT (RUNBOOKS):
        {context}
        
        LIVE DIAGNOSTIC OUTPUT (kubectl commands executed):
        {diagnostics}
        
        RAW ALERT DATA:
        {event.original_event.raw_payload}

        YOUR TASK:
        1. Analyze the diagnostic output to identify the root cause.
        2. Cross-reference with the runbook for remediation guidance.
        3. Propose safe remediation actions.
        
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

        4. Provide a confidence score (0.0 to 1.0).

        OUTPUT FORMAT:
        Return ONLY valid JSON matching this structure:
        {{
            "analysis": "string explanation including diagnostic findings",
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
