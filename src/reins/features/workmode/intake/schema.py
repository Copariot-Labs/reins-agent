from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime
import uuid


IssueType = Literal[
    "repair",
    "complaint",
    "safety",
    "service_request",
    "other"
]

Priority = Literal["low", "medium", "high", "urgent"]


@dataclass
class ResidentIssue:
    raw_text: str
    issue_type: IssueType
    priority: Priority
    location: Optional[str] = None
    description: str = ""
    required_action: str = ""

    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())