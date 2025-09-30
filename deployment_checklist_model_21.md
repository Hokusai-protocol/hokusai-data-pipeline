# Model 21 Production Deployment Checklist

## Current Endpoint (When Deployed)
```
POST https://api.hokus.ai/api/v1/models/21/predict
```

## 🚨 CRITICAL: What's Missing for Production

### 1. **API Route Registration** ❌
The `model_serving.py` endpoint is NOT registered in `src/api/main.py`

**Required Change:**
```python
# In src/api/main.py
from src.api.endpoints import model_serving

# Add this line after other route inclusions
app.include_router(model_serving.router)
```

### 2. **Dependencies Installation** ❌
Need to add to `requirements.txt`:
```
huggingface-hub>=0.19.0
scikit-learn>=1.3.0
```

### 3. **Environment Variables** ❌
Must be set in production environment (AWS ECS):
```
HUGGINGFACE_API_KEY=hf_ddLWhXdxxxx  # Your HF token
HOKUSAI_API_KEY=hk_prod_xxx         # For internal auth
```

### 4. **Model Training & Upload** ⚠️
Current model is a dummy model. Need to:
- Train real Sales Lead Scoring model with actual data
- Upload to HuggingFace repository
- Update model config in `model_serving.py`

### 5. **Infrastructure Configuration** ❌
Need to update in `../hokusai-infrastructure`:
- Add environment variables to ECS task definition
- Ensure ALB routing includes `/api/v1/models/*` path
- Add secrets to AWS Secrets Manager

### 6. **Database Integration** ❌
Model metadata should be in database:
```sql
INSERT INTO models (id, name, repository_id, storage_type, status)
VALUES (21, 'Sales Lead Scoring Model',
        'timogilvie/hokusai-model-21-sales-lead-scorer',
        'huggingface_private', 'active');
```

## ✅ What IS Ready

1. **Model Storage**: Private HuggingFace repository created
2. **Security**: Private repo with authentication working
3. **Serving Code**: `model_serving.py` endpoint implemented
4. **Upload Scripts**: Model upload automation ready

## 🔧 Minimal Changes to Make It Work

### Quick Fix (For Testing)
```python
# 1. Update src/api/main.py
from src.api.endpoints import model_serving
app.include_router(model_serving.router)

# 2. Add to requirements.txt
huggingface-hub>=0.19.0
scikit-learn>=1.3.0

# 3. Set environment variable in deployment
HUGGINGFACE_API_KEY=your_token_here
```

### Then Deploy:
```bash
# Build and push Docker image
docker build -t hokusai/api:latest -f Dockerfile.api .
docker push $ECR_REGISTRY/hokusai/api:latest

# Update ECS service
aws ecs update-service --cluster hokusai-development \
  --service hokusai-api-development --force-new-deployment
```

## 📊 Testing the Deployed Endpoint

Once deployed, test with:

```bash
curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
  -H "Authorization: Bearer YOUR_HOKUSAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "company_size": 1000,
      "industry": "Technology",
      "engagement_score": 75,
      "website_visits": 10,
      "email_opens": 5,
      "content_downloads": 3,
      "demo_requested": true,
      "budget_confirmed": false,
      "decision_timeline": "Q2 2025",
      "title": "VP of Sales"
    }
  }'
```

Expected Response:
```json
{
  "model_id": "21",
  "predictions": {
    "lead_score": 72,
    "conversion_probability": 0.72,
    "recommendation": "Hot",
    "factors": ["Demo requested", "High engagement"]
  },
  "metadata": {
    "api_version": "1.0",
    "inference_method": "local"
  },
  "timestamp": "2025-09-29T18:30:00Z"
}
```

## ⚠️ Current Branch Status

**This branch contains:**
- ✅ Model upload scripts
- ✅ Serving endpoint code
- ✅ Security analysis
- ✅ Test scripts

**This branch does NOT contain:**
- ❌ Route registration in main.py
- ❌ Dependency updates
- ❌ Infrastructure changes
- ❌ Real trained model

## 🎯 Answer to Your Question

**No, merging this branch alone will NOT make the endpoint work in production.**

You need to:
1. Register the route in `main.py`
2. Add dependencies to `requirements.txt`
3. Set `HUGGINGFACE_API_KEY` in production environment
4. Deploy the changes

**Estimated work: 30 minutes** to make it functional with the dummy model.
**Additional work needed:** Train and upload real Sales Lead Scoring model.