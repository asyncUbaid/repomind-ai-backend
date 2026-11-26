from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.impact_chain import ImpactChain
from app.ai.models import create_embeddings
from app.api.routes.auth import get_current_user
from app.api.routes.repositories import owner_repository
from app.db.database import get_db
from app.db.models import AnalysisReport, User
from app.schemas.analysis import FeatureImpactReport, ImpactAnalysisResponse
from app.services.retrieval_service import RetrievalService

router = APIRouter(tags=["analysis"])


class ImpactRequest(BaseModel):
    feature_request: str = Field(min_length=1, max_length=4000)


def format_impact_context(results: list[dict]) -> str:
    parts = []
    for result in results:
        payload = result["payload"]
        parts.append(
            f"File: {payload.get('file_path')}\n"
            f"Lines: {payload.get('start_line')}-{payload.get('end_line')}\n"
            f"Symbol: {payload.get('symbol_name') or 'none'}\n"
            f"Content:\n{payload.get('content', '')}"
        )
    return "\n\n".join(parts)


@router.post("/api/repositories/{repository_id}/analyze-impact", response_model=FeatureImpactReport)
def analyze_impact(
    repository_id: int,
    payload: ImpactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeatureImpactReport:
    repository = owner_repository(repository_id, current_user, db)
    if not repository.latest_commit_sha:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has not been indexed for a commit",
        )

    results = RetrievalService(create_embeddings()).retrieve(
        payload.feature_request,
        repository_id=repository.id,
        commit_sha=repository.latest_commit_sha,
        limit=5,
    )
    if not results:
        report = FeatureImpactReport(
            feature_request=payload.feature_request,
            summary="The available indexed repository context is insufficient to identify likely affected files.",
            affected_files=[],
            implementation_steps=[],
            risks=["Analysis is based on no retrieved repository evidence."],
            assumptions=["Relevant source files may need indexing or a broader retrieval query."],
        )
    else:
        try:
            report = ImpactChain().analyze(
                payload.feature_request,
                format_impact_context(results),
            )
            if report.feature_request != payload.feature_request:
                report.feature_request = payload.feature_request
        except Exception:
            report = FeatureImpactReport(
                feature_request=payload.feature_request,
                summary="The local model could not produce a validated feature impact report.",
                affected_files=[],
                implementation_steps=[],
                risks=[
                    "Repository context was retrieved, but structured AI analysis was unavailable.",
                ],
                assumptions=["The report requires the Ollama chat model and a completed index."],
            )

    db.add(
        AnalysisReport(
            repository_id=repository.id,
            user_id=current_user.id,
            report_type="feature_impact",
            query=payload.feature_request,
            report_data=report.model_dump(),
        )
    )
    db.commit()
    return report


@router.get("/api/analysis/{analysis_id}", response_model=ImpactAnalysisResponse)
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisReport:
    report = db.scalar(
        select(AnalysisReport).where(
            AnalysisReport.id == analysis_id,
            AnalysisReport.user_id == current_user.id,
        )
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found")
    return report
