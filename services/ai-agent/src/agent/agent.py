import os
import subprocess
import shlex
import time
import re
from google.protobuf.json_format import MessageToJson, Parse
from protos.contracts import orchestrator_pb2
import uuid
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models
from minio import Minio
from llm.llm_provider import LLMProvider


class IncidentAgent:
    def __init__(self):
        print("Initializing AI Agent with LLM Provider...")
        
        # Initialize LLM Provider (handles rate limiting and retries internally)
        self.llm = LLMProvider(
            model=os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash"),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "5")),
            rate_limit_rpm=float(os.getenv("LLM_RATE_LIMIT_RPM", "5.0")),
        )
        
        # Initialize RAG (Qdrant)
        self.qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        self.qdrant = QdrantClient(host=self.qdrant_host, port=6333)
        self.collection_name = "sre_knowledge"
        
        # Initialize MinIO
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.minio_access = os.getenv("MINIO_ROOT_USER", "minioadmin")
        self.minio_secret = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
        self.bucket_name = "runbooks"
        
        self.minio_client = Minio(
            self.minio_endpoint,
            access_key=self.minio_access,
            secret_key=self.minio_secret,
            secure=False
        )
        
        # Alert deduplication cache
        self._alert_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
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
        "orchestrator-",
        "prometheus",
        "alertmanager",
        "grafana",
        "loki",
        "promtail",
        "qdrant",
        "minio",
        "kafka",
    ]

    def _should_ignore_alert(self, service_name: str) -> bool:
        """Check if this alert should be ignored (system components)."""
        for pattern in self.IGNORED_SERVICE_PATTERNS:
            if pattern in service_name:
                return True
        return False

    def _sanitize_input(self, value: str) -> str:
        """Sanitize input to prevent prompt injection."""
        if not value:
            return ""
        # Remove potential injection patterns
        sanitized = re.sub(r'[;\|\&\$`]', '', str(value))
        # Limit length
        return sanitized[:500]

    def _discover_resources(self, namespace: str) -> dict:
        """
        Discover actual K8s resources to provide accurate names to LLM.
        This prevents the LLM from guessing wrong pod/deployment names.
        """
        resources = {
            "pods": [],
            "deployments": [],
            "services": [],
            "replicasets": []
        }
        
        discovery_commands = [
            ("pods", ["kubectl", "get", "pods", "-n", namespace, "-o", "name"]),
            ("deployments", ["kubectl", "get", "deployments", "-n", namespace, "-o", "name"]),
            ("services", ["kubectl", "get", "services", "-n", namespace, "-o", "name"]),
            ("replicasets", ["kubectl", "get", "replicasets", "-n", namespace, "-o", "name"]),
        ]
        
        for resource_type, cmd in discovery_commands:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Parse output like "pod/myapp-abc123" -> "myapp-abc123"
                    items = []
                    for line in result.stdout.strip().split("\n"):
                        if "/" in line:
                            items.append(line.split("/", 1)[1])
                        elif line.strip():
                            items.append(line.strip())
                    resources[resource_type] = items[:20]  # Limit to 20 per type
            except subprocess.TimeoutExpired:
                print(f"DISCOVERY: Timeout getting {resource_type}")
            except Exception as e:
                print(f"DISCOVERY: Failed to get {resource_type}: {e}")
        
        print(f"DISCOVERY: Found {len(resources['pods'])} pods, {len(resources['deployments'])} deployments in {namespace}")
        return resources

    def _find_matching_resources(self, service_name: str, resources: dict) -> dict:
        """Find resources that match the service name from the alert."""
        matches = {
            "pods": [],
            "deployments": [],
        }
        
        # Normalize service name for matching
        service_lower = service_name.lower()
        
        for pod in resources.get("pods", []):
            # Match if pod name contains service name or vice versa
            if service_lower in pod.lower() or any(part in pod.lower() for part in service_lower.split("-")):
                matches["pods"].append(pod)
        
        for deploy in resources.get("deployments", []):
            if service_lower in deploy.lower() or any(part in deploy.lower() for part in service_lower.split("-")):
                matches["deployments"].append(deploy)
        
        return matches

    def _extract_json(self, text: str) -> dict:
        """
        Robustly extract JSON from LLM response.
        Handles markdown code blocks, trailing text, etc.
        """
        if not text:
            return {}
        
        # Try multiple extraction methods
        extraction_methods = [
            # Method 1: Direct parse (already clean JSON)
            lambda t: json.loads(t.strip()),
            # Method 2: Extract from markdown code block
            lambda t: json.loads(re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', t).group(1)),
            # Method 3: Find JSON object pattern
            lambda t: json.loads(re.search(r'\{[\s\S]*\}', t).group(0)),
            # Method 4: Find JSON array pattern  
            lambda t: json.loads(re.search(r'\[[\s\S]*\]', t).group(0)),
        ]
        
        for method in extraction_methods:
            try:
                return method(text)
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        
        print(f"JSON_EXTRACT: All extraction methods failed for: {text[:200]}...")
        return {}

    def analyze(self, event: orchestrator_pb2.DomainEvent) -> orchestrator_pb2.Decision:
        """Main analysis entry point."""
        # Filter out system component alerts
        if self._should_ignore_alert(event.service_name):
            print(f"IGNORED: Skipping system component alert for {event.service_name}")
            return self._ignored_decision(event)
        
        # Check for duplicate alerts
        cache_key = f"{event.service_name}:{event.domain}"
        current_time = time.time()
        
        if cache_key in self._alert_cache:
            last_processed = self._alert_cache[cache_key]
            time_since = current_time - last_processed
            if time_since < self._cache_ttl:
                print(f"RATE LIMIT: Skipping duplicate alert for {event.service_name} (processed {time_since:.0f}s ago)")
                return self._cached_decision(event)
        
        # Update cache
        self._alert_cache[cache_key] = current_time
        
        # Clean up old cache entries
        self._alert_cache = {k: v for k, v in self._alert_cache.items() 
                            if current_time - v < self._cache_ttl * 2}
        
        print(f"PROCESSING: New alert for {event.service_name}")
        
        # Extract namespace from metadata (convert protobuf map to dict)
        metadata = dict(event.original_event.metadata) if event.original_event.metadata else {}
        namespace = metadata.get("namespace", "default")
        namespace = self._sanitize_input(namespace)
        
        # 1. Discover actual K8s resources (prevents wrong name guessing)
        resources = self._discover_resources(namespace)
        matching = self._find_matching_resources(event.service_name, resources)
        
        # 2. Build context from RAG
        context = self._build_context(event)
        
        # 3. Get diagnostic commands (with resource awareness)
        diagnostic_commands = self._get_diagnostic_commands(event, context, namespace, resources, matching)
        
        # 4. Execute diagnostics
        diagnostics = self._run_diagnostics(diagnostic_commands)
        
        # 5. Build analysis prompt
        prompt = self._build_prompt(event, context, diagnostics)
        
        try:
            # 6. Call LLM for final analysis
            response_text = self.llm.generate(prompt)
            
            # 7. Parse decision
            return self._parse_decision(response_text, event)
            
        except Exception as e:
            print(f"LLM generation failed: {e}")
            return self._fallback_decision(event, str(e))

    def _cached_decision(self, event) -> orchestrator_pb2.Decision:
        """Return a cached/skipped decision for duplicate alerts."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Alert for {event.service_name} was recently processed. Skipping."
        decision.confidence_score = 0.0
        return decision

    def _ignored_decision(self, event) -> orchestrator_pb2.Decision:
        """Return a skip decision for ignored system component alerts."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Alert for {event.service_name} ignored (system component)."
        decision.confidence_score = 0.0
        return decision

    def _get_diagnostic_commands(self, event, context: str, namespace: str, 
                                  resources: dict, matching: dict) -> list:
        """
        PHASE 1: Ask LLM to generate diagnostic commands.
        Now includes actual resource names to prevent guessing.
        """
        service_name = self._sanitize_input(event.service_name)
        raw_payload_str = str(event.original_event.raw_payload) if event.original_event.raw_payload else ""
        raw_payload = self._sanitize_input(raw_payload_str[:1000])
        
        # Build resource context for LLM
        resource_context = f"""
AVAILABLE RESOURCES IN NAMESPACE '{namespace}':
- Pods: {matching.get('pods', [])[:10] or resources.get('pods', [])[:10]}
- Deployments: {matching.get('deployments', [])[:5] or resources.get('deployments', [])[:5]}
- All Pods (if needed): {resources.get('pods', [])[:15]}
"""
        
        prompt = f"""You are an SRE assistant. Generate kubectl diagnostic commands for this alert.

ALERT CONTEXT:
- Service: {service_name}
- Namespace: {namespace}
- Alert: {raw_payload}

{resource_context}

RUNBOOK GUIDANCE:
{context[:2000]}

CRITICAL INSTRUCTIONS:
1. Use EXACT resource names from the lists above - DO NOT guess or modify names
2. Only use these command types: get, describe, logs, top
3. Always include the namespace flag: -n {namespace}
4. Suggest 3-5 diagnostic commands
5. If a pod name looks like "myapp-abc123-xyz", use that EXACT name
6. For logs, add --tail=100 to limit output

OUTPUT FORMAT (valid JSON only):
{{
    "commands": [
        "kubectl describe pod EXACT_POD_NAME -n {namespace}",
        "kubectl logs EXACT_POD_NAME -n {namespace} --tail=100"
    ]
}}
"""

        try:
            response_text = self.llm.generate(prompt)
            data = self._extract_json(response_text)
            commands = data.get("commands", [])
            
            # Validate and filter commands
            validated = []
            for cmd in commands[:5]:
                cmd = cmd.strip()
                if any(cmd.startswith(allowed) for allowed in self.ALLOWED_COMMANDS):
                    validated.append(cmd)
                    print(f"DIAGNOSTICS: Approved: {cmd}")
                else:
                    print(f"DIAGNOSTICS: BLOCKED (whitelist): {cmd}")
            
            # If no valid commands, generate safe fallbacks
            if not validated:
                validated = self._generate_fallback_commands(namespace, resources, matching)
            
            return validated
            
        except Exception as e:
            print(f"DIAGNOSTICS: LLM failed: {e}")
            return self._generate_fallback_commands(namespace, resources, matching)

    def _generate_fallback_commands(self, namespace: str, resources: dict, matching: dict) -> list:
        """Generate safe fallback diagnostic commands."""
        commands = []
        
        # Try matching pods first
        if matching.get("pods"):
            pod = matching["pods"][0]
            commands.append(f"kubectl describe pod {pod} -n {namespace}")
            commands.append(f"kubectl logs {pod} -n {namespace} --tail=100")
        # Fall back to any pods
        elif resources.get("pods"):
            pod = resources["pods"][0]
            commands.append(f"kubectl describe pod {pod} -n {namespace}")
        
        # Always get recent events
        commands.append(f"kubectl get events -n {namespace} --sort-by=.lastTimestamp | tail -20")
        
        print(f"DIAGNOSTICS: Using {len(commands)} fallback commands")
        return commands[:5]

    def _build_context(self, event) -> str:
        """Build context from RAG (vector search + MinIO fetch)."""
        try:
            raw_payload_str = str(event.original_event.raw_payload) if event.original_event.raw_payload else ""
            query_text = f"{event.service_name} {raw_payload_str}"
            
            print(f"RAG: Embedding query: {query_text[:50]}...")
            embedding = self.llm.embed(query_text)
            
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
            
            filename = hit.payload.get('minio_path')
            bucket = hit.payload.get('minio_bucket', self.bucket_name)
            
            try:
                response = self.minio_client.get_object(bucket, filename)
                content = response.read().decode('utf-8')
                response.close()
                response.release_conn()
            except Exception as e:
                print(f"MinIO Fetch Failed: {e}")
                return "Runbook found but failed to retrieve content."
            
            return f"""
RELEVANT RUNBOOK:
Title: {hit.payload.get('title')}
Content:
{content[:3000]}
"""
            
        except Exception as e:
            print(f"RAG Failed: {e}")
            return "Context retrieval failed."

    def _run_diagnostics(self, commands: list) -> str:
        """Execute kubectl commands with proper parsing and error handling."""
        diagnostics = []
        
        print(f"DIAGNOSTICS: Executing {len(commands)} commands...")
        
        for cmd in commands:
            # Security re-check
            if not any(cmd.strip().startswith(allowed) for allowed in self.ALLOWED_COMMANDS):
                print(f"DIAGNOSTICS: BLOCKED (security): {cmd}")
                continue
            
            try:
                # Use shlex for proper shell-like parsing
                # Handle pipes specially
                if "|" in cmd:
                    # For piped commands, use shell=True but only for safe commands
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True, 
                        text=True, 
                        timeout=30
                    )
                else:
                    # Parse command properly
                    cmd_parts = shlex.split(cmd)
                    result = subprocess.run(
                        cmd_parts,
                        capture_output=True, 
                        text=True, 
                        timeout=30
                    )
                
                print(f"DIAGNOSTICS: Ran: {cmd[:80]}...")
                
                if result.returncode == 0 and result.stdout:
                    output = result.stdout[:3000]
                    diagnostics.append(f"=== {cmd} ===\n{output}")
                elif result.stderr:
                    # Include error info - helpful for LLM analysis
                    error_msg = result.stderr[:500]
                    diagnostics.append(f"=== {cmd} ===\nCommand failed: {error_msg}")
                    print(f"DIAGNOSTICS: Error: {error_msg[:100]}")
                else:
                    diagnostics.append(f"=== {cmd} ===\n(No output)")
                    
            except subprocess.TimeoutExpired:
                diagnostics.append(f"=== {cmd} ===\nTimeout after 30s")
                print(f"DIAGNOSTICS: Timeout: {cmd}")
            except ValueError as e:
                # shlex parsing error
                print(f"DIAGNOSTICS: Parse error for '{cmd}': {e}")
                diagnostics.append(f"=== {cmd} ===\nParse error: {e}")
            except Exception as e:
                diagnostics.append(f"=== {cmd} ===\nFailed: {e}")
                print(f"DIAGNOSTICS: Error: {e}")
        
        if not diagnostics:
            return "No diagnostic information could be gathered."
        
        return "\n\n".join(diagnostics)

    def _build_prompt(self, event, context: str, diagnostics: str) -> str:
        """Build the final analysis prompt."""
        return f"""You are a Senior Site Reliability Engineer (SRE). 
Analyze the following incident and propose remediation actions.

INCIDENT DETAILS:
- ID: {event.event_id}
- Service: {event.service_name}
- Domain: {event.domain}

RUNBOOK CONTEXT:
{context}

LIVE DIAGNOSTIC OUTPUT:
{diagnostics}

RAW ALERT:
{str(event.original_event.raw_payload) if event.original_event.raw_payload else 'N/A'}

YOUR TASK:
1. Analyze the diagnostic output to identify the root cause
2. Cross-reference with the runbook for remediation guidance
3. Propose safe, specific remediation actions

AVAILABLE ACTIONS:
- "restart_pod": Restart a specific pod
  Target: exact pod name, Params: {{"namespace": "string"}}
  
- "scale_deployment": Scale a deployment
  Target: deployment name, Params: {{"replicas": "int"}} OR {{"replicas_increment": "int"}}
  
- "rolling_restart_deployment": Restart all pods in deployment
  Target: deployment name, Params: {{"namespace": "string"}}

- "rollback_deployment": Rollback deployment to previous revision
  Target: deployment name, Params: {{"namespace": "string"}}
  Use when: bad deployment, recent code change caused issues, need to revert

OUTPUT FORMAT (JSON only):
{{
    "analysis": "Brief explanation of root cause and findings",
    "confidence_score": 0.0-1.0,
    "proposed_actions": [
        {{
            "action_type": "restart_pod|scale_deployment|rolling_restart_deployment|rollback_deployment",
            "target": "exact resource name",
            "params": {{"key": "value"}},
            "reasoning": "why this action helps"
        }}
    ]
}}
"""

    def _parse_decision(self, llm_output: str, event) -> orchestrator_pb2.Decision:
        """Parse LLM output into Decision protobuf with retry on failure."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        
        # Try to extract JSON
        data = self._extract_json(llm_output)
        
        if not data:
            # Retry with correction prompt if parse failed
            print("PARSE: Initial extraction failed, attempting retry...")
            try:
                retry_prompt = f"""The following LLM output needs to be converted to valid JSON.
Extract the analysis, confidence score, and proposed actions.

Original output:
{llm_output[:2000]}

Return ONLY valid JSON in this format:
{{"analysis": "...", "confidence_score": 0.5, "proposed_actions": []}}
"""
                retry_response = self.llm.generate(retry_prompt)
                data = self._extract_json(retry_response)
            except Exception as e:
                print(f"PARSE: Retry failed: {e}")
        
        if data:
            decision.analysis = data.get("analysis", "Analysis completed.")
            decision.confidence_score = float(data.get("confidence_score", 0.5))
            
            for action_data in data.get("proposed_actions", []):
                action = decision.proposed_actions.add()
                action.action_id = str(uuid.uuid4())
                action.decision_id = decision.decision_id
                action.action_type = action_data.get("action_type", "unknown")
                action.target = action_data.get("target", "unknown")
                action.reasoning = action_data.get("reasoning", "")
                
                if "params" in action_data and isinstance(action_data["params"], dict):
                    for k, v in action_data["params"].items():
                        action.params[k] = str(v)
        else:
            decision.analysis = f"Parse Error. Raw: {llm_output[:500]}"
            decision.confidence_score = 0.0
            
        return decision

    def _fallback_decision(self, event, error_msg: str) -> orchestrator_pb2.Decision:
        """Return a fallback decision when analysis fails."""
        decision = orchestrator_pb2.Decision()
        decision.decision_id = str(uuid.uuid4())
        decision.incident_id = event.event_id
        decision.analysis = f"Agent failed: {error_msg}"
        decision.confidence_score = 0.0
        return decision
