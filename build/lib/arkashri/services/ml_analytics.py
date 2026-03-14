# pyre-ignore-all-errors
"""
ML Analytics and Predictive Insights Service
Provides machine learning analytics, anomaly detection, and risk prediction
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import os

import structlog

_ML_ENABLED = os.getenv("ENABLE_ML", "false").lower() == "true"
if _ML_ENABLED:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report

from arkashri.config import get_settings
from arkashri.logging_config import analytics_logger

logger = structlog.get_logger(__name__)

class MLAnalyticsService:
    """Machine Learning Analytics Service"""
    
    def __init__(self):
        self.settings = get_settings()
        self.models_path = Path(getattr(self.settings, 'ml_model_path', './models/analytics'))
        self.confidence_threshold = getattr(self.settings, 'ml_confidence_threshold', 0.85)
        self.prediction_horizon = getattr(self.settings, 'ml_prediction_horizon_days', 30)
        
        # Initialize models
        # Skip heavy ML model loading on low-resource envs (ENABLE_ML != true)
        if _ML_ENABLED:
            self.scaler = StandardScaler()
            self.models_path.mkdir(parents=True, exist_ok=True)
            self._load_models()
        else:
            self.scaler = None
            logger.info("ml_models_skipped", reason="ENABLE_ML not set — running in rule-only mode")
    
    def _load_models(self):
        """Load pre-trained models or initialize new ones"""
        try:
            # Try to load existing models
            anomaly_model_path = self.models_path / "anomaly_detector.pkl"
            risk_model_path = self.models_path / "risk_predictor.pkl"
            
            if anomaly_model_path.exists():
                import joblib
                self.anomaly_detector = joblib.load(anomaly_model_path)
                logger.info("anomaly_model_loaded", path=str(anomaly_model_path))
            else:
                self.anomaly_detector = IsolationForest(
                    contamination=0.1,
                    random_state=42
                )
                logger.info("anomaly_model_initialized")
            
            if risk_model_path.exists():
                self.risk_predictor = joblib.load(risk_model_path)
                logger.info("risk_model_loaded", path=str(risk_model_path))
            else:
                self.risk_predictor = RandomForestClassifier(
                    n_estimators=100,
                    random_state=42,
                    max_depth=10
                )
                logger.info("risk_model_initialized")
                
        except Exception as e:
            logger.error("model_loading_error", error=str(e))
            # Initialize default models
            self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
            self.risk_predictor = RandomForestClassifier(n_estimators=100, random_state=42)
    
    async def analyze_audit_patterns(self, audit_data: List[Dict]) -> Dict:
        """Analyze audit patterns and detect anomalies"""
        try:
            if not audit_data:
                return {"anomalies": [], "patterns": [], "insights": []}
            
            # Convert to DataFrame
            df = pd.DataFrame(audit_data)
            
            # Feature engineering
            features = self._extract_audit_features(df)
            
            # Detect anomalies
            if len(features) > 0:
                anomaly_scores = self.anomaly_detector.fit_predict(features)
                anomalies = self._identify_anomalies(df, anomaly_scores)
            else:
                anomalies = []
            
            # Analyze patterns
            patterns = self._analyze_patterns(df)
            
            # Generate insights
            insights = self._generate_insights(df, anomalies, patterns)
            
            logger.info("audit_patterns_analyzed", 
                       audit_count=len(audit_data), 
                       anomalies_found=len(anomalies),
                       patterns_found=len(patterns))
            
            return {
                "anomalies": anomalies,
                "patterns": patterns,
                "insights": insights,
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("audit_analysis_error", error=str(e))
            return {"error": str(e)}
    
    async def predict_risk_factors(self, historical_data: List[Dict]) -> Dict:
        """Predict risk factors for future audits"""
        try:
            if not historical_data:
                return {"predictions": [], "risk_factors": [], "recommendations": []}
            
            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            
            # Prepare features
            X, y = self._prepare_risk_features(df)
            
            if len(X) < 10:  # Need minimum data for prediction
                return {"predictions": [], "risk_factors": [], "recommendations": []}
            
            # Train model if not already trained
            if not hasattr(self.risk_predictor, 'feature_names_in_'):
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                self.risk_predictor.fit(X_train, y_train)
                
                # Evaluate model
                y_pred = self.risk_predictor.predict(X_test)
                accuracy = accuracy_score(y_test, y_pred)
                logger.info("risk_model_trained", accuracy=accuracy)
            
            # Predict future risks
            future_features = self._generate_future_features(df)
            if len(future_features) > 0:
                risk_predictions = self.risk_predictor.predict(future_features)
                risk_probabilities = self.risk_predictor.predict_proba(future_features)
            else:
                risk_predictions = []
                risk_probabilities = []
            
            # Generate risk factors and recommendations
            risk_factors = self._identify_risk_factors(df, risk_predictions, risk_probabilities)
            recommendations = self._generate_risk_recommendations(risk_factors)
            
            logger.info("risk_prediction_completed", 
                       historical_records=len(historical_data),
                       future_predictions=len(risk_predictions))
            
            return {
                "predictions": [
                    {
                        "date": (datetime.utcnow() + timedelta(days=i)).isoformat(),
                        "risk_level": pred,
                        "confidence": float(max(prob)),
                        "risk_factors": self._get_risk_factors_for_prediction(pred)
                    }
                    for i, (pred, prob) in enumerate(zip(risk_predictions, risk_probabilities))
                ][:self.prediction_horizon],
                "risk_factors": risk_factors,
                "recommendations": recommendations,
                "model_accuracy": getattr(self.risk_predictor, 'accuracy', 0.0),
                "prediction_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("risk_prediction_error", error=str(e))
            return {"error": str(e)}
    
    async def analyze_sentiment(self, text_data: List[str]) -> Dict:
        """Analyze sentiment from textual data"""
        try:
            if not text_data:
                return {"sentiment": "neutral", "confidence": 0.0, "analysis": []}
            
            # Simple sentiment analysis (in production, use more sophisticated models)
            sentiments = []
            for text in text_data:
                sentiment_score = self._calculate_sentiment(text)
                sentiments.append({
                    "text": text,
                    "sentiment": sentiment_score["sentiment"],
                    "confidence": sentiment_score["confidence"],
                    "keywords": sentiment_score["keywords"]
                })
            
            # Overall sentiment
            overall_sentiment = self._aggregate_sentiments(sentiments)
            
            logger.info("sentiment_analysis_completed", 
                       texts_analyzed=len(text_data),
                       overall_sentiment=overall_sentiment["sentiment"])
            
            return {
                "overall_sentiment": overall_sentiment,
                "individual_analyses": sentiments,
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("sentiment_analysis_error", error=str(e))
            return {"error": str(e)}
    
    def _extract_audit_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract features from audit data for anomaly detection"""
        features = []
        
        for _, row in df.iterrows():
            feature_vector = [
                row.get('duration_hours', 0),
                row.get('findings_count', 0),
                row.get('risk_score', 0),
                row.get('team_size', 1),
                row.get('client_size_score', 0),
                row.get('complexity_score', 0),
                row.get('automation_score', 0)
            ]
            features.append(feature_vector)
        
        return np.array(features)
    
    def _identify_anomalies(self, df: pd.DataFrame, anomaly_scores: np.ndarray) -> List[Dict]:
        """Identify and describe anomalies"""
        anomalies = []
        
        for i, (idx, row) in enumerate(df.iterrows()):
            if anomaly_scores[i] == -1:  # Anomaly detected
                anomalies.append({
                    "audit_id": row.get('audit_id', f'audit_{i}'),
                    "anomaly_type": self._classify_anomaly_type(row),
                    "severity": "high" if abs(anomaly_scores[i]) > 0.5 else "medium",
                    "description": self._generate_anomaly_description(row),
                    "anomaly_score": float(abs(anomaly_scores[i])),
                    "timestamp": row.get('created_at', datetime.utcnow().isoformat())
                })
        
        return anomalies
    
    def _analyze_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """Analyze patterns in audit data"""
        patterns = []
        
        # Time-based patterns
        if 'created_at' in df.columns:
            df['created_at'] = pd.to_datetime(df['created_at'])
            df['hour'] = df['created_at'].dt.hour
            df['day_of_week'] = df['created_at'].dt.dayofweek
            
            # Peak hours
            peak_hours = df['hour'].value_counts().head(3)
            patterns.append({
                "pattern_type": "peak_audit_hours",
                "description": "Most active audit hours",
                "data": peak_hours.to_dict()
            })
            
            # Day patterns
            day_patterns = df['day_of_week'].value_counts()
            patterns.append({
                "pattern_type": "weekly_distribution",
                "description": "Audit distribution by day of week",
                "data": day_patterns.to_dict()
            })
        
        # Risk patterns
        if 'risk_score' in df.columns:
            risk_distribution = df['risk_score'].describe()
            patterns.append({
                "pattern_type": "risk_distribution",
                "description": "Risk score distribution",
                "data": risk_distribution.to_dict()
            })
        
        return patterns
    
    def _generate_insights(self, df: pd.DataFrame, anomalies: List[Dict], patterns: List[Dict]) -> List[str]:
        """Generate actionable insights from analysis"""
        insights = []
        
        # Anomaly insights
        if anomalies:
            high_severity_anomalies = [a for a in anomalies if a['severity'] == 'high']
            if high_severity_anomalies:
                insights.append(f"Found {len(high_severity_anomalies)} high-severity anomalies requiring immediate attention")
        
        # Pattern insights
        for pattern in patterns:
            if pattern['pattern_type'] == 'peak_audit_hours':
                peak_hour = max(pattern['data'].items(), key=lambda x: x[1])[0]
                insights.append(f"Peak audit activity occurs at {peak_hour}:00 - consider resource allocation")
        
        # Efficiency insights
        if 'duration_hours' in df.columns and 'findings_count' in df.columns:
            efficiency = df['findings_count'] / df['duration_hours']
            avg_efficiency = efficiency.mean()
            if avg_efficiency > 5:  # More than 5 findings per hour
                insights.append("High finding rate detected - consider improving audit procedures")
        
        return insights
    
    def _prepare_risk_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features for risk prediction"""
        feature_columns = [
            'duration_hours', 'findings_count', 'risk_score',
            'team_size', 'client_size_score', 'complexity_score'
        ]
        
        # Create risk level as target
        df['risk_level'] = pd.cut(df['risk_score'], 
                                bins=[0, 3, 6, 10], 
                                labels=['low', 'medium', 'high', 'critical'])
        
        # Select available features
        available_features = [col for col in feature_columns if col in df.columns]
        X = df[available_features].fillna(0).values
        y = df['risk_level'].values
        
        return X, y
    
    def _generate_future_features(self, df: pd.DataFrame) -> np.ndarray:
        """Generate features for future risk prediction"""
        # Use recent trends to predict future
        recent_data = df.tail(10)  # Last 10 records
        
        if len(recent_data) < 3:
            return np.array([])
        
        # Calculate trends
        features = []
        for i in range(self.prediction_horizon):
            # Simple trend projection
            trend_features = [
                recent_data['duration_hours'].mean() + (i * 0.1),
                recent_data['findings_count'].mean() + (i * 0.05),
                recent_data['risk_score'].mean() + (i * 0.02),
                recent_data['team_size'].mean(),
                recent_data['client_size_score'].mean(),
                recent_data['complexity_score'].mean()
            ]
            features.append(trend_features)
        
        return np.array(features)
    
    def _identify_risk_factors(self, df: pd.DataFrame, predictions: np.ndarray, probabilities: np.ndarray) -> List[Dict]:
        """Identify key risk factors"""
        risk_factors = []
        
        # High-risk predictions
        high_risk_indices = np.where(predictions == 'critical')[0]
        if len(high_risk_indices) > 0:
            risk_factors.append({
                "risk_factor": "Critical risk periods detected",
                "severity": "high",
                "description": f"Prediction indicates {len(high_risk_indices)} critical risk periods",
                "mitigation": "Increase audit coverage and team size"
            })
        
        # Low confidence predictions
        low_confidence_indices = np.where(np.max(probabilities, axis=1) < self.confidence_threshold)[0]
        if len(low_confidence_indices) > 0:
            risk_factors.append({
                "risk_factor": "Low prediction confidence",
                "severity": "medium",
                "description": f"{len(low_confidence_indices)} predictions have low confidence",
                "mitigation": "Collect more historical data for better predictions"
            })
        
        return risk_factors
    
    def _generate_risk_recommendations(self, risk_factors: List[Dict]) -> List[str]:
        """Generate recommendations based on risk factors"""
        recommendations = []
        
        for factor in risk_factors:
            if "critical" in factor.get("description", "").lower():
                recommendations.append("Schedule additional senior auditors for critical periods")
            
            if "low confidence" in factor.get("description", "").lower():
                recommendations.append("Implement more detailed audit documentation")
            
            if "team size" in factor.get("mitigation", "").lower():
                recommendations.append("Consider team expansion or workload redistribution")
        
        return list(set(recommendations))  # Remove duplicates
    
    def _calculate_sentiment(self, text: str) -> Dict:
        """Simple sentiment analysis"""
        # Positive words
        positive_words = ['good', 'excellent', 'complete', 'successful', 'effective', 'improved', 'compliant']
        # Negative words
        negative_words = ['bad', 'failed', 'incomplete', 'risk', 'issue', 'problem', 'non-compliant']
        
        words = text.lower().split()
        positive_count = sum(1 for word in words if word in positive_words)
        negative_count = sum(1 for word in words if word in negative_words)
        
        total_words = len(words)
        if total_words == 0:
            return {"sentiment": "neutral", "confidence": 0.0, "keywords": []}
        
        sentiment_score = (positive_count - negative_count) / total_words
        
        if sentiment_score > 0.1:
            sentiment = "positive"
        elif sentiment_score < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        confidence = min(abs(sentiment_score) * 2, 1.0)
        keywords = [word for word in words if word in positive_words + negative_words]
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "keywords": keywords
        }
    
    def _aggregate_sentiments(self, sentiments: List[Dict]) -> Dict:
        """Aggregate individual sentiment analyses"""
        if not sentiments:
            return {"sentiment": "neutral", "confidence": 0.0}
        
        positive_count = sum(1 for s in sentiments if s['sentiment'] == 'positive')
        negative_count = sum(1 for s in sentiments if s['sentiment'] == 'negative')
        neutral_count = sum(1 for s in sentiments if s['sentiment'] == 'neutral')
        
        total = len(sentiments)
        if total == 0:
            return {"sentiment": "neutral", "confidence": 0.0}
        
        if positive_count > negative_count and positive_count > neutral_count:
            overall_sentiment = "positive"
        elif negative_count > positive_count and negative_count > neutral_count:
            overall_sentiment = "negative"
        else:
            overall_sentiment = "neutral"
        
        confidence = max(positive_count, negative_count, neutral_count) / total
        
        return {
            "sentiment": overall_sentiment,
            "confidence": confidence
        }
    
    def _classify_anomaly_type(self, row: pd.Series) -> str:
        """Classify the type of anomaly"""
        duration = row.get('duration_hours', 0)
        findings = row.get('findings_count', 0)
        risk = row.get('risk_score', 0)
        
        if duration > 100:
            return "duration_anomaly"
        elif findings > 50:
            return "findings_anomaly"
        elif risk > 8:
            return "risk_anomaly"
        else:
            return "general_anomaly"
    
    def _generate_anomaly_description(self, row: pd.Series) -> str:
        """Generate description for anomaly"""
        duration = row.get('duration_hours', 0)
        findings = row.get('findings_count', 0)
        risk = row.get('risk_score', 0)
        
        descriptions = []
        if duration > 100:
            descriptions.append(f"unusually long duration ({duration} hours)")
        if findings > 50:
            descriptions.append(f"high number of findings ({findings})")
        if risk > 8:
            descriptions.append(f"elevated risk score ({risk})")
        
        return "; ".join(descriptions) if descriptions else "unusual pattern detected"
    
    def _get_risk_factors_for_prediction(self, prediction: str) -> List[str]:
        """Get risk factors for a prediction"""
        risk_mapping = {
            'low': ['standard procedures', 'routine compliance'],
            'medium': ['moderate complexity', 'additional review needed'],
            'high': ['elevated risk', 'senior oversight required'],
            'critical': ['high risk', 'immediate attention needed']
        }
        return risk_mapping.get(prediction, ['unknown risk factors'])
    
    def save_models(self):
        """Save trained models"""
        try:
            import joblib
            
            self.models_path.mkdir(parents=True, exist_ok=True)
            
            # Save anomaly detector
            if self.anomaly_detector:
                joblib.dump(self.anomaly_detector, self.models_path / "anomaly_detector.pkl")
                logger.info("anomaly_model_saved")
            
            # Save risk predictor
            if self.risk_predictor and hasattr(self.risk_predictor, 'feature_names_in_'):
                joblib.dump(self.risk_predictor, self.models_path / "risk_predictor.pkl")
                logger.info("risk_model_saved")
                
        except Exception as e:
            logger.error("model_saving_error", error=str(e))

# Global service instance — initialized lazily (no ML models on startup unless ENABLE_ML=true)
ml_analytics_service = MLAnalyticsService()
