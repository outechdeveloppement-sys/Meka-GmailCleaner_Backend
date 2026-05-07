from pydantic import BaseModel, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

class Filter(BaseModel):
    field: Literal['from', 'older_than', 'size', 'category', 'has']
    value: str

class RuleConditions(BaseModel):
    operator: Literal['AND', 'OR']
    filters: List[Filter]

class Rule(BaseModel):
    id: Optional[str] = None
    name: str
    enabled: bool = True
    createdAt: Optional[datetime] = None
    lastRun: Optional[datetime] = None
    emailsDeleted: int = 0
    conditions: RuleConditions

class User(BaseModel):
    uid: str
    email: EmailStr
    displayName: Optional[str] = None
    gmailConnected: bool = False
    createdAt: datetime

class HistoryEntry(BaseModel):
    jobId: str
    executedAt: datetime
    rulesApplied: List[str]
    emailsDeleted: int
    spaceSavedMB: float

class KimiSuggestion(BaseModel):
    name: str
    description: str
    conditions: RuleConditions

class CleanResult(BaseModel):
    emails_deleted: int
    space_saved_mb: float
    rules_applied: List[str]
