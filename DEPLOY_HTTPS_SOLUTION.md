# Deploy HTTPS for registry.hokus.ai

## Current Situation

- `registry.hokus.ai` resolves to IP addresses but port 443 is closed
- The infrastructure already supports HTTPS but needs an SSL certificate
- All documentation and SDK defaults expect HTTPS

## Solution: Enable HTTPS

### Step 1: Create SSL Certificate

Using AWS Certificate Manager (ACM):

```bash
# Request a certificate for the domain
aws acm request-certificate \
  --domain-name registry.hokus.ai \
  --validation-method DNS \
  --region us-east-1

# Note the Certificate ARN returned
```

### Step 2: Validate the Certificate

1. Add the DNS validation records to your domain registrar
2. Wait for validation (usually takes a few minutes)
3. Verify certificate status:

```bash
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT-ID \
  --region us-east-1
```

### Step 3: Deploy Infrastructure with Certificate

```bash
cd infrastructure/terraform

# Apply with the certificate ARN
terraform apply \
  -var="certificate_arn=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT-ID" \
  -var="environment=production"
```

### Step 4: Update DNS Records

Point `registry.hokus.ai` to the ALB:

```bash
# Get the ALB DNS name
terraform output alb_dns_name

# Create Route53 alias record or update your DNS provider
# registry.hokus.ai → your-alb-name.us-east-1.elb.amazonaws.com
```

## Alternative: Quick Fix with Let's Encrypt

If you need a quick solution without AWS ACM:

### Option 1: Use Caddy as Reverse Proxy

```dockerfile
# Dockerfile.caddy
FROM caddy:2-alpine

COPY Caddyfile /etc/caddy/Caddyfile
```

```caddyfile
# Caddyfile
registry.hokus.ai {
    reverse_proxy mlflow:5000
    
    handle /api/* {
        reverse_proxy api:8001
    }
}
```

### Option 2: Use Nginx with Certbot

```nginx
server {
    listen 80;
    server_name registry.hokus.ai;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name registry.hokus.ai;
    
    ssl_certificate /etc/letsencrypt/live/registry.hokus.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/registry.hokus.ai/privkey.pem;
    
    location / {
        proxy_pass http://mlflow:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/ {
        proxy_pass http://api:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Temporary Workaround for Third Parties

Until HTTPS is deployed, third parties should:

```python
# Configure to use HTTP explicitly
import os
os.environ["MLFLOW_TRACKING_URI"] = "http://registry.hokus.ai"
os.environ["HOKUSAI_API_ENDPOINT"] = "http://registry.hokus.ai/api"

from hokusai import ModelRegistry
registry = ModelRegistry(tracking_uri="http://registry.hokus.ai")
```

## Benefits of Deploying HTTPS

1. **Security**: Protects API keys and model data in transit
2. **Trust**: Users expect HTTPS in 2025
3. **Compatibility**: Many tools enforce HTTPS
4. **SEO**: Search engines penalize HTTP-only sites
5. **Future-proof**: Avoids breaking changes later

## Implementation Priority

1. **High Priority**: Get SSL certificate and deploy HTTPS
2. **Medium Priority**: Update all hardcoded HTTP references to HTTPS
3. **Low Priority**: Add HTTP-to-HTTPS redirect

## Estimated Time

- Certificate creation: 30 minutes
- DNS validation: 10-60 minutes
- Infrastructure deployment: 15 minutes
- Testing: 30 minutes

**Total: ~2 hours**

## Next Steps

1. Decide on certificate provider (AWS ACM recommended)
2. Create and validate certificate
3. Deploy infrastructure with certificate ARN
4. Update DNS records
5. Test HTTPS endpoints
6. Update documentation to reflect HTTPS URLs