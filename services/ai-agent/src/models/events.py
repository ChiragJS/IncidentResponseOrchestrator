from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

class NormalizedEvent(BaseModel):
    event_id: str
    source: str
    timestamp: str  # ISO string
    severity: str
    raw_payload: Dict[str, Any]
    metadata: Dict[str, str]

class DomainEvent(BaseModel):
    event_id: str
    domain: str
    cluster_id: str
    service_name: str
    related_resources: List[str]
    metrics: Optional[Dict[str, Any]] = None
    original_event: NormalizedEvent

class Action(BaseModel):
    action_id: str
    decision_id: str
    action_type: str
    target: str
    params: Dict[str, str]
    reasoning: Optional[str] = None
    approver: Optional[str] = None

class Decision(BaseModel):
    decision_id: str
    incident_id: str
    analysis: str
    proposed_actions: List[Action]
    confidence_score: float
