#!/usr/bin/env python3
"""
Model Registration Flow Testing Script
Executes complete model registration workflow with comprehensive testing
"""

import os
import sys
import json
import time
import requests
import tempfile
import numpy as np
from typing import Dict, Optional, Any, List
from datetime import datetime
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# Try to import MLflow
try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("⚠️  MLflow not installed. Some tests will be skipped.")

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class ModelRegistrationTester:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "stages": {},
            "summary": {
                "total_stages": 0,
                "passed_stages": 0,
                "failed_stages": 0,
                "warnings": 0
            }
        }
        
        # Endpoints
        self.registry_endpoint = "https://registry.hokus.ai"
        self.mlflow_endpoint = f"{self.registry_endpoint}/api/mlflow"
        
        # MLflow setup if available
        if MLFLOW_AVAILABLE:
            os.environ["MLFLOW_TRACKING_URI"] = self.mlflow_endpoint
            if self.api_key:
                os.environ["MLFLOW_TRACKING_TOKEN"] = self.api_key
                
    def create_sample_model(self) -> Dict:
        """Create a sample sklearn model for testing"""
        print("\n🤖 Creating Sample Model...")
        
        try:
            # Generate synthetic dataset
            X, y = make_classification(
                n_samples=1000,
                n_features=10,
                n_informative=8,
                n_redundant=2,
                random_state=42
            )
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Train model
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)
            
            # Calculate metrics
            y_pred = model.predict(X_test)
            metrics = {
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred),
                "recall": recall_score(y_test, y_pred),
                "f1_score": f1_score(y_test, y_pred)
            }
            
            print(f"  ✅ Model created successfully")
            print(f"  📊 Metrics: Accuracy={metrics['accuracy']:.3f}, F1={metrics['f1_score']:.3f}")
            
            return {
                "success": True,
                "model": model,
                "metrics": metrics,
                "metadata": {
                    "model_type": "RandomForestClassifier",
                    "n_estimators": 100,
                    "n_features": 10,
                    "training_samples": len(X_train)
                }
            }
            
        except Exception as e:
            print(f"  ❌ Error creating model: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def test_experiment_creation(self) -> Dict:
        """Test creating an MLflow experiment"""
        print("\n🧪 Testing Experiment Creation...")
        
        if not MLFLOW_AVAILABLE:
            print("  ⚠️  MLflow not available, skipping experiment tests")
            return {"skipped": True, "reason": "MLflow not installed"}
            
        experiment_name = f"hokusai_test_{int(time.time())}"
        
        try:
            # Set up authentication header
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            # Create experiment via API
            response = requests.post(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/create",
                json={"name": experiment_name},
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                experiment_id = response.json().get("experiment_id")
                print(f"  ✅ Experiment created: {experiment_name} (ID: {experiment_id})")
                
                # Try to list experiments to verify
                list_response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                    json={"max_results": 10},
                    headers=headers,
                    timeout=10
                )
                
                if list_response.status_code == 200:
                    experiments = list_response.json().get("experiments", [])
                    print(f"  ✅ Found {len(experiments)} experiments")
                    
                return {
                    "success": True,
                    "experiment_id": experiment_id,
                    "experiment_name": experiment_name,
                    "total_experiments": len(experiments) if list_response.status_code == 200 else None
                }
            else:
                print(f"  ❌ Failed to create experiment: {response.status_code}")
                print(f"     Response: {response.text[:200]}")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
                
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def test_model_logging(self, model_data: Dict, experiment_id: Optional[str] = None) -> Dict:
        """Test logging a model to MLflow"""
        print("\n📝 Testing Model Logging...")
        
        if not MLFLOW_AVAILABLE:
            print("  ⚠️  MLflow not available, testing via API only")
            return self._test_model_logging_api(model_data)
            
        if not model_data.get("success"):
            print("  ⚠️  No model to log, skipping")
            return {"skipped": True, "reason": "No model available"}
            
        try:
            # Create a run
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            # Start run
            run_data = {
                "experiment_id": experiment_id or "0",
                "start_time": int(time.time() * 1000),
                "tags": {
                    "mlflow.source.type": "LOCAL",
                    "mlflow.user": "hokusai_test"
                }
            }
            
            response = requests.post(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/runs/create",
                json=run_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"  ❌ Failed to create run: {response.status_code}")
                return {
                    "success": False,
                    "error": f"Failed to create run: {response.text[:200]}"
                }
                
            run_id = response.json()["run"]["info"]["run_id"]
            print(f"  ✅ Created run: {run_id}")
            
            # Log metrics
            for metric_name, metric_value in model_data["metrics"].items():
                metric_response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/runs/log-metric",
                    json={
                        "run_id": run_id,
                        "key": metric_name,
                        "value": metric_value,
                        "timestamp": int(time.time() * 1000)
                    },
                    headers=headers,
                    timeout=10
                )
                
                if metric_response.status_code == 200:
                    print(f"  ✅ Logged metric: {metric_name}={metric_value:.3f}")
                else:
                    print(f"  ❌ Failed to log metric {metric_name}: {metric_response.status_code}")
                    
            # Log parameters
            for param_name, param_value in model_data["metadata"].items():
                param_response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/runs/log-parameter",
                    json={
                        "run_id": run_id,
                        "key": param_name,
                        "value": str(param_value)
                    },
                    headers=headers,
                    timeout=10
                )
                
                if param_response.status_code == 200:
                    print(f"  ✅ Logged parameter: {param_name}={param_value}")
                    
            # Update run status
            update_response = requests.post(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/runs/update",
                json={
                    "run_id": run_id,
                    "status": "FINISHED",
                    "end_time": int(time.time() * 1000)
                },
                headers=headers,
                timeout=10
            )
            
            if update_response.status_code == 200:
                print(f"  ✅ Run completed successfully")
                
            return {
                "success": True,
                "run_id": run_id,
                "metrics_logged": len(model_data["metrics"]),
                "parameters_logged": len(model_data["metadata"])
            }
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def _test_model_logging_api(self, model_data: Dict) -> Dict:
        """Test model logging via direct API calls when MLflow is not installed"""
        # Similar to above but using only API calls
        return self.test_model_logging(model_data)
        
    def test_model_registration(self, run_id: Optional[str] = None) -> Dict:
        """Test registering a model in the registry"""
        print("\n📦 Testing Model Registration...")
        
        model_name = f"test_model_{int(time.time())}"
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            # Create registered model
            response = requests.post(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/registered-models/create",
                json={
                    "name": model_name,
                    "tags": {
                        "hokusai_token_id": "test-token",
                        "benchmark_metric": "accuracy",
                        "benchmark_value": "0.95"
                    }
                },
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"  ✅ Model registered: {model_name}")
                
                # Create model version if we have a run_id
                if run_id:
                    version_response = requests.post(
                        f"{self.mlflow_endpoint}/api/2.0/mlflow/model-versions/create",
                        json={
                            "name": model_name,
                            "source": f"runs:/{run_id}/model",
                            "run_id": run_id
                        },
                        headers=headers,
                        timeout=10
                    )
                    
                    if version_response.status_code == 200:
                        version = version_response.json().get("model_version", {}).get("version", "1")
                        print(f"  ✅ Model version created: v{version}")
                    else:
                        print(f"  ⚠️  Failed to create model version: {version_response.status_code}")
                        
                # Search for the model
                search_response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/registered-models/search",
                    json={"filter": f"name='{model_name}'"},
                    headers=headers,
                    timeout=10
                )
                
                if search_response.status_code == 200:
                    models = search_response.json().get("registered_models", [])
                    if models:
                        print(f"  ✅ Model found in registry")
                        
                return {
                    "success": True,
                    "model_name": model_name,
                    "model_found": len(models) > 0 if search_response.status_code == 200 else False
                }
            else:
                print(f"  ❌ Failed to register model: {response.status_code}")
                print(f"     Response: {response.text[:200]}")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
                
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def test_model_retrieval(self, model_name: str) -> Dict:
        """Test retrieving a registered model"""
        print("\n🔍 Testing Model Retrieval...")
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            # Get model details
            response = requests.get(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/registered-models/get",
                params={"name": model_name},
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                model_data = response.json().get("registered_model", {})
                print(f"  ✅ Model retrieved: {model_data.get('name')}")
                print(f"     Created: {model_data.get('creation_timestamp')}")
                print(f"     Last Updated: {model_data.get('last_updated_timestamp')}")
                
                # Get model versions
                versions_response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/model-versions/search",
                    json={"filter": f"name='{model_name}'"},
                    headers=headers,
                    timeout=10
                )
                
                if versions_response.status_code == 200:
                    versions = versions_response.json().get("model_versions", [])
                    print(f"  ✅ Found {len(versions)} model version(s)")
                    
                return {
                    "success": True,
                    "model_data": model_data,
                    "versions_count": len(versions) if versions_response.status_code == 200 else 0
                }
            else:
                print(f"  ❌ Failed to retrieve model: {response.status_code}")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
                
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def test_artifact_upload(self, run_id: str) -> Dict:
        """Test uploading artifacts"""
        print("\n📤 Testing Artifact Upload...")
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            # Create a test artifact
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                test_artifact = {
                    "model_metadata": {
                        "framework": "sklearn",
                        "algorithm": "RandomForest",
                        "test_timestamp": datetime.now().isoformat()
                    }
                }
                json.dump(test_artifact, f)
                artifact_path = f.name
                
            # Upload artifact
            with open(artifact_path, 'rb') as f:
                files = {'file': ('metadata.json', f, 'application/json')}
                
                response = requests.post(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow-artifacts/artifacts",
                    params={
                        "run_id": run_id,
                        "path": "metadata.json"
                    },
                    files=files,
                    headers=headers,
                    timeout=30
                )
                
            # Clean up
            os.unlink(artifact_path)
            
            if response.status_code == 200:
                print(f"  ✅ Artifact uploaded successfully")
                return {
                    "success": True,
                    "artifact_name": "metadata.json"
                }
            else:
                print(f"  ❌ Failed to upload artifact: {response.status_code}")
                print(f"     Response: {response.text[:200]}")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
                
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*60)
        print("📋 MODEL REGISTRATION TEST REPORT")
        print("="*60)
        
        print(f"\n📅 Timestamp: {self.results['timestamp']}")
        print(f"🔑 API Key: {self.api_key[:10]}...{self.api_key[-4:] if self.api_key else 'Not provided'}")
        
        print(f"\n📊 Summary:")
        print(f"  Total Stages: {self.results['summary']['total_stages']}")
        print(f"  ✅ Passed: {self.results['summary']['passed_stages']}")
        print(f"  ❌ Failed: {self.results['summary']['failed_stages']}")
        print(f"  ⚠️  Warnings: {self.results['summary']['warnings']}")
        
        if self.results['summary']['total_stages'] > 0:
            success_rate = (self.results['summary']['passed_stages'] / 
                          self.results['summary']['total_stages']) * 100
            print(f"  📈 Success Rate: {success_rate:.1f}%")
            
        # Stage-by-stage results
        print("\n📝 Stage Results:")
        for stage_name, stage_result in self.results['stages'].items():
            if stage_result.get("success"):
                print(f"  ✅ {stage_name}")
            elif stage_result.get("skipped"):
                print(f"  ⏭️  {stage_name} (skipped: {stage_result.get('reason', 'unknown')})")
            else:
                print(f"  ❌ {stage_name}: {stage_result.get('error', 'unknown error')}")
                
        # Save detailed report
        report_file = "model_registration_test_report.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed report saved to: {report_file}")
        
        # Recommendations
        print("\n🔧 Recommendations:")
        
        if not self.results['stages'].get('experiment_creation', {}).get('success'):
            print("  - Fix experiment creation endpoint authentication")
            
        if not self.results['stages'].get('model_registration', {}).get('success'):
            print("  - Verify model registry is properly configured")
            
        if not self.results['stages'].get('artifact_upload', {}).get('success'):
            print("  - Check artifact storage configuration (S3 bucket, permissions)")
            
        print("\n✅ Model registration testing completed!")
        
    def run_full_workflow(self):
        """Run the complete model registration workflow"""
        if not self.api_key:
            print("❌ No API key provided!")
            print("Please set HOKUSAI_API_KEY environment variable")
            return None
            
        print("🚀 Starting Model Registration Workflow Test...")
        print(f"🔑 Using API key: {self.api_key[:10]}...{self.api_key[-4:]}")
        print("="*60)
        
        # Stage 1: Create model
        model_result = self.create_sample_model()
        self.results['stages']['model_creation'] = model_result
        self.results['summary']['total_stages'] += 1
        if model_result.get('success'):
            self.results['summary']['passed_stages'] += 1
        else:
            self.results['summary']['failed_stages'] += 1
            
        # Stage 2: Create experiment
        experiment_result = self.test_experiment_creation()
        self.results['stages']['experiment_creation'] = experiment_result
        self.results['summary']['total_stages'] += 1
        if experiment_result.get('success'):
            self.results['summary']['passed_stages'] += 1
        elif experiment_result.get('skipped'):
            self.results['summary']['warnings'] += 1
        else:
            self.results['summary']['failed_stages'] += 1
            
        # Stage 3: Log model
        run_result = self.test_model_logging(
            model_result, 
            experiment_result.get('experiment_id')
        )
        self.results['stages']['model_logging'] = run_result
        self.results['summary']['total_stages'] += 1
        if run_result.get('success'):
            self.results['summary']['passed_stages'] += 1
        elif run_result.get('skipped'):
            self.results['summary']['warnings'] += 1
        else:
            self.results['summary']['failed_stages'] += 1
            
        # Stage 4: Register model
        registration_result = self.test_model_registration(
            run_result.get('run_id')
        )
        self.results['stages']['model_registration'] = registration_result
        self.results['summary']['total_stages'] += 1
        if registration_result.get('success'):
            self.results['summary']['passed_stages'] += 1
        else:
            self.results['summary']['failed_stages'] += 1
            
        # Stage 5: Retrieve model
        if registration_result.get('success'):
            retrieval_result = self.test_model_retrieval(
                registration_result.get('model_name')
            )
            self.results['stages']['model_retrieval'] = retrieval_result
            self.results['summary']['total_stages'] += 1
            if retrieval_result.get('success'):
                self.results['summary']['passed_stages'] += 1
            else:
                self.results['summary']['failed_stages'] += 1
                
        # Stage 6: Test artifact upload
        if run_result.get('run_id'):
            artifact_result = self.test_artifact_upload(run_result.get('run_id'))
            self.results['stages']['artifact_upload'] = artifact_result
            self.results['summary']['total_stages'] += 1
            if artifact_result.get('success'):
                self.results['summary']['passed_stages'] += 1
            else:
                self.results['summary']['failed_stages'] += 1
                
        # Generate report
        self.generate_report()
        
        return self.results


if __name__ == "__main__":
    # Check for API key
    api_key = os.environ.get("HOKUSAI_API_KEY")
    if not api_key and len(sys.argv) > 1:
        api_key = sys.argv[1]
        
    if not api_key:
        print("❌ Please provide an API key!")
        print("Usage: python test_model_registration_flow.py <api_key>")
        print("   or: export HOKUSAI_API_KEY=<api_key>")
        sys.exit(1)
        
    tester = ModelRegistrationTester(api_key)
    results = tester.run_full_workflow()
    
    # Exit with appropriate code
    if results and results['summary']['failed_stages'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)