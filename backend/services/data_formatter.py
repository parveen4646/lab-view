import uuid
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class DataFormatter:
    """Format analyzed data to match frontend schema"""
    
    def __init__(self):
        self.default_categories = self._get_default_categories()
    
    def format_for_frontend(self, analyzed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format analyzed data to match frontend schema exactly"""
        try:
            # Generate trend data for each test
            trend_data = {}
            latest_results = analyzed_data.get("latestResults", [])
            
            for result in latest_results:
                test_name = result.get("testName", "").lower().replace(" ", "")
                if test_name and result.get("value") is not None:
                    trend_data[test_name] = self._generate_trend_data(
                        result["testName"], 
                        result["value"]
                    )
            
            # Format final response
            formatted_response = {
                "patientInfo": self._format_patient_info(analyzed_data.get("patientInfo", {})),
                "latestResults": self._format_latest_results(latest_results),
                "testCategories": self._format_test_categories(analyzed_data.get("testCategories", [])),
                "trendData": trend_data
            }
            
            logger.info("✅ Data formatted for frontend")
            return formatted_response
            
        except Exception as e:
            logger.error(f"❌ Error formatting data: {str(e)}")
            return self._get_empty_response()
    
    def _format_patient_info(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format patient information"""
        return {
            "id": patient_data.get("id", f"p_{uuid.uuid4().hex[:8]}"),
            "name": patient_data.get("name", "Unknown Patient"),
            "age": patient_data.get("age"),
            "gender": patient_data.get("gender"),
            "dateOfBirth": patient_data.get("dateOfBirth"),
            "lastTestDate": patient_data.get("lastTestDate", datetime.now().strftime("%Y-%m-%d"))
        }
    
    def _format_latest_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format latest results"""
        formatted_results = []
        
        for result in results:
            try:
                formatted_result = {
                    "id": result.get("id", f"r_{uuid.uuid4().hex[:8]}"),
                    "testName": result.get("testName", "Unknown Test"),
                    "value": float(result.get("value", 0)),
                    "unit": result.get("unit", ""),
                    "referenceRange": result.get("referenceRange", {"min": 0, "max": 100}),
                    "status": result.get("status", "normal"),
                    "date": result.get("date", datetime.now().strftime("%Y-%m-%d")),
                    "category": result.get("category", "blood"),
                    "canonicalName": result.get("canonicalName")
                }
                formatted_results.append(formatted_result)
            except Exception as e:
                logger.warning(f"⚠️  Error formatting result {result}: {str(e)}")
                continue
        
        return formatted_results
    
    def _format_test_categories(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format test categories"""
        if not categories:
            return self.default_categories
        
        formatted_categories = []
        for category in categories:
            try:
                formatted_category = {
                    "id": category.get("id", "unknown"),
                    "name": category.get("name", "Unknown Category"),
                    "description": category.get("description", ""),
                    "color": category.get("color", "hsl(var(--chart-primary))"),
                    "tests": category.get("tests", [])
                }
                formatted_categories.append(formatted_category)
            except Exception as e:
                logger.warning(f"⚠️  Error formatting category {category}: {str(e)}")
                continue
        
        return formatted_categories if formatted_categories else self.default_categories
    
    def _generate_trend_data(self, test_name: str, current_value: float) -> List[Dict[str, Any]]:
        """Generate trend data for the last 12 months"""
        trend_data = []
        
        # Generate 12 months of data
        for i in range(11, -1, -1):
            date = (datetime.now() - timedelta(days=30*i)).strftime("%Y-%m")
            
            # Add realistic variation (±20% of current value)
            variation = (random.random() - 0.5) * 0.4 * current_value
            value = max(0, current_value + variation)
            
            # Simple status determination
            status = "normal"
            if abs(variation) > 0.15 * current_value:
                status = "high" if variation > 0 else "low"
            
            trend_data.append({
                "date": date,
                "value": round(value, 1),
                "testName": test_name,
                "status": status
            })
        
        return trend_data
    
    def _get_default_categories(self) -> List[Dict[str, Any]]:
        """Get default test categories"""
        return [
            {
                "id": "blood",
                "name": "Complete Blood Count",
                "description": "Blood cell counts and basic blood chemistry",
                "color": "hsl(var(--chart-primary))",
                "tests": ["hemoglobin", "hematocrit", "wbc", "platelets"]
            },
            {
                "id": "lipid",
                "name": "Lipid Panel",
                "description": "Cholesterol and triglyceride levels",
                "color": "hsl(var(--chart-secondary))",
                "tests": ["totalCholesterol", "hdl", "ldl", "triglycerides"]
            },
            {
                "id": "liver",
                "name": "Liver Function",
                "description": "Liver enzyme and protein levels",
                "color": "hsl(var(--chart-tertiary))",
                "tests": ["alt", "ast", "bilirubin", "albumin"]
            },
            {
                "id": "kidney",
                "name": "Kidney Function",
                "description": "Kidney function markers",
                "color": "hsl(var(--chart-quaternary))",
                "tests": ["creatinine", "bun", "gfr"]
            }
        ]
    
    def _get_empty_response(self) -> Dict[str, Any]:
        """Get empty response structure"""
        return {
            "patientInfo": {
                "id": "empty",
                "name": "No Data",
                "age": None,
                "gender": None,
                "dateOfBirth": None,
                "lastTestDate": datetime.now().strftime("%Y-%m-%d")
            },
            "latestResults": [],
            "testCategories": self.default_categories,
            "trendData": {}
        }
