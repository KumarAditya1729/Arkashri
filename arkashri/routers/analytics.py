# pyre-ignore-all-errors
"""
ML Analytics API endpoints
Provides AI-powered insights and predictive analytics
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from arkashri.services.ml_analytics import ml_analytics_service
from arkashri.services.ai_fabric import generate_contextual_insight
from arkashri.dependencies import get_current_user, get_session
from arkashri.models import Engagement, RiskEntry

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.get("/contextual-lens")
async def get_contextual_lens(
    engagement_id: str,
    current_stage: str,
    session: AsyncSession = Depends(get_session),
    current_user: Dict = Depends(get_current_user)
):
    """Generates dynamic AI advice for the frontend Assistant sidebar."""
    try:
        try:
            eid = uuid.UUID(engagement_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")
        # Fetch high-level engagement details to guide the AI
        engagement = await session.get(Engagement, eid)
        if not engagement:
            raise HTTPException(status_code=404, detail="Engagement not found")
            
        # Count risks for context
        risk_count_query = await session.execute(
            select(func.count(RiskEntry.id)).where(RiskEntry.engagement_id == eid)
        )
        total_risks = risk_count_query.scalar_one_or_none() or 0

        context_data = {
            "client_name": engagement.client_name,
            "status": engagement.status.name if hasattr(engagement.status, 'name') else str(engagement.status),
            "total_recorded_risks": total_risks,
            "jurisdiction": engagement.jurisdiction
        }

        # Invoke the AI service
        insight = await generate_contextual_insight(
            engagement_id=str(engagement.id),
            current_stage=current_stage,
            audit_type=engagement.engagement_type.name if hasattr(engagement.engagement_type, 'name') else str(engagement.engagement_type),
            context_data=context_data
        )
        return insight

    except HTTPException:
        raise  # Re-raise HTTP exceptions (e.g., 404) unchanged
    except Exception as e:
        logger.error("contextual_lens_api_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail=f"Failed to generate contextual insight: {str(e)}")

class AuditDataRequest(BaseModel):
    """Request model for audit pattern analysis"""
    audit_data: List[Dict[str, Any]] = Field(..., description="Audit data to analyze")

class HistoricalDataRequest(BaseModel):
    """Request model for risk prediction"""
    historical_data: List[Dict[str, Any]] = Field(..., description="Historical audit data")

class TextDataRequest(BaseModel):
    """Request model for sentiment analysis"""
    text_data: List[str] = Field(..., description="Text data to analyze")

class AnomalyResponse(BaseModel):
    """Response model for anomaly detection"""
    anomalies: List[Dict[str, Any]]
    patterns: List[Dict[str, Any]]
    insights: List[str]
    analysis_timestamp: str

class RiskPredictionResponse(BaseModel):
    """Response model for risk prediction"""
    predictions: List[Dict[str, Any]]
    risk_factors: List[Dict[str, Any]]
    recommendations: List[str]
    model_accuracy: float
    prediction_timestamp: str

class SentimentResponse(BaseModel):
    """Response model for sentiment analysis"""
    overall_sentiment: Dict[str, Any]
    individual_analyses: List[Dict[str, Any]]
    analysis_timestamp: str

@router.post("/patterns", response_model=AnomalyResponse)
async def analyze_audit_patterns(
    request: AuditDataRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Analyze audit patterns and detect anomalies"""
    try:
        result = await ml_analytics_service.analyze_audit_patterns(request.audit_data)
        return AnomalyResponse(**result)
    except Exception as e:
        logger.error("audit_pattern_analysis_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to analyze audit patterns")

@router.post("/predictions", response_model=RiskPredictionResponse)
async def predict_risk_factors(
    request: HistoricalDataRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Predict risk factors for future audits"""
    try:
        result = await ml_analytics_service.predict_risk_factors(request.historical_data)
        return RiskPredictionResponse(**result)
    except Exception as e:
        logger.error("risk_prediction_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to predict risk factors")

@router.post("/sentiment", response_model=SentimentResponse)
async def analyze_sentiment(
    request: TextDataRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Analyze sentiment from textual data"""
    try:
        result = await ml_analytics_service.analyze_sentiment(request.text_data)
        return SentimentResponse(**result)
    except Exception as e:
        logger.error("sentiment_analysis_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to analyze sentiment")

@router.get("/models/status")
async def get_model_status(current_user: Dict = Depends(get_current_user)):
    """Get status of ML models"""
    try:
        return {
            "anomaly_detector": "loaded" if ml_analytics_service.anomaly_detector else "not_loaded",
            "risk_predictor": "trained" if hasattr(ml_analytics_service.risk_predictor, 'feature_names_in_') else "not_trained",
            "sentiment_analyzer": "available",
            "confidence_threshold": ml_analytics_service.confidence_threshold,
            "prediction_horizon": ml_analytics_service.prediction_horizon
        }
    except Exception as e:
        logger.error("model_status_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get model status")

@router.post("/models/train")
async def train_models(
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user)
):
    """Train ML models in background"""
    try:
        # Add training task to background
        background_tasks.add_task(ml_analytics_service.save_models)
        
        return {
            "message": "Model training started",
            "status": "training_in_background"
        }
    except Exception as e:
        logger.error("model_training_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to start model training")

@router.get("/overview")
async def get_analytics_overview(current_user: Dict = Depends(get_current_user)):
    """Get analytics overview summary"""
    try:
        # Mock overview data - in production, fetch from database
        return {
            "anomaly_detection": {
                "total_anomalies": 12,
                "high_severity": 3,
                "medium_severity": 7,
                "low_severity": 2
            },
            "risk_prediction": {
                "predictions_available": True,
                "model_accuracy": 0.87,
                "prediction_horizon_days": 30,
                "upcoming_risks": 5
            },
            "sentiment_analysis": {
                "overall_sentiment": "positive",
                "confidence": 0.78,
                "documents_analyzed": 156
            },
            "model_performance": {
                "anomaly_detector": "active",
                "risk_predictor": "trained",
                "last_training": "2026-03-09T10:30:00Z"
            }
        }
    except Exception as e:
        logger.error("analytics_overview_error", error=str(e), user_id=current_user.get("id"))
        raise HTTPException(status_code=500, detail="Failed to get analytics overview")
