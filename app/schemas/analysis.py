from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImpactEvidence(BaseModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class AffectedFile(BaseModel):
    file_path: str
    impact_level: Literal["high", "medium", "low"]
    impact_basis: Literal["direct_observed", "ai_inferred"]
    reason: str
    recommended_changes: list[str]
    evidence: list[ImpactEvidence]


class FeatureImpactReport(BaseModel):
    feature_request: str
    summary: str
    affected_files: list[AffectedFile] = []
    implementation_steps: list[str] = []
    risks: list[str] = []
    assumptions: list[str] = []


class ImpactAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    report_type: str
    query: str
    report_data: FeatureImpactReport
    created_at: datetime
