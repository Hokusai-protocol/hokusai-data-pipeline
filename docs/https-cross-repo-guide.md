# HTTPS Implementation Guide for Other Hokusai Repositories

## Overview

This guide is for teams managing other Hokusai services (auth.hokus.ai, www.hokus.ai) that are not part of this repository. It provides a standardized approach to implementing HTTPS across all Hokusai services.

## Shared Certificate Strategy

### Option 1: Use Shared Wildcard Certificate (Recommended)

If the main Hokusai platform has already created a wildcard certificate for `*.hokus.ai`:

1. **Get the Certificate ARN** from the platform team:
   ```
   arn:aws:acm:us-east-1:123456789012:certificate/...
   ```

2. **Use the same certificate** in your load balancer configuration:
   - The certificate can be used across multiple ALBs
   - No additional validation needed
   - Reduces certificate management overhead

### Option 2: Request Service-Specific Certificate

If you need a separate certificate:

1. **Request certificate** for your specific domain:
   ```bash
   aws acm request-certificate \
     --domain-name "auth.hokus.ai" \
     --validation-method DNS \
     --region us-east-1
   ```

2. **Coordinate DNS validation** with the platform team to add CNAME records

## Implementation Steps

### For Services Using AWS ALB/ELB

1. **Update Security Groups**:
   ```hcl
   # Allow HTTPS traffic
   ingress {
     from_port   = 443
     to_port     = 443
     protocol    = "tcp"
     cidr_blocks = ["0.0.0.0/0"]
   }
   ```

2. **Add HTTPS Listener**:
   ```hcl
   resource "aws_lb_listener" "https" {
     load_balancer_arn = aws_lb.main.arn
     port              = "443"
     protocol          = "HTTPS"
     ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
     certificate_arn   = var.certificate_arn
     
     default_action {
       type             = "forward"
       target_group_arn = aws_lb_target_group.main.arn
     }
   }
   ```

3. **Configure HTTP to HTTPS Redirect**:
   ```hcl
   resource "aws_lb_listener" "http" {
     load_balancer_arn = aws_lb.main.arn
     port              = "80"
     protocol          = "HTTP"
     
     default_action {
       type = "redirect"
       
       redirect {
         port        = "443"
         protocol    = "HTTPS"
         status_code = "HTTP_301"
       }
     }
   }
   ```

### For Services Using CloudFront

1. **Configure CloudFront Distribution**:
   ```hcl
   resource "aws_cloudfront_distribution" "main" {
     # ... other configuration ...
     
     viewer_certificate {
       acm_certificate_arn = var.certificate_arn
       ssl_support_method  = "sni-only"
     }
     
     default_cache_behavior {
       viewer_protocol_policy = "redirect-to-https"
       # ... other settings ...
     }
   }
   ```

### For Kubernetes/EKS Services

1. **Using AWS Load Balancer Controller**:
   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: auth-service
     annotations:
       service.beta.kubernetes.io/aws-load-balancer-backend-protocol: "http"
       service.beta.kubernetes.io/aws-load-balancer-ssl-cert: "arn:aws:acm:..."
       service.beta.kubernetes.io/aws-load-balancer-ssl-ports: "https"
   spec:
     type: LoadBalancer
     ports:
     - name: https
       port: 443
       targetPort: 8080
   ```

2. **Using Ingress**:
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: auth-ingress
     annotations:
       kubernetes.io/ingress.class: alb
       alb.ingress.kubernetes.io/certificate-arn: "arn:aws:acm:..."
       alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
       alb.ingress.kubernetes.io/ssl-redirect: '443'
   spec:
     rules:
     - host: auth.hokus.ai
       http:
         paths:
         - path: /
           pathType: Prefix
           backend:
             service:
               name: auth-service
               port:
                 number: 8080
   ```

## Environment Variable Updates

Update all services to use HTTPS URLs:

```yaml
# Before
API_URL: "http://api.hokus.ai"
AUTH_URL: "http://auth.hokus.ai"
FRONTEND_URL: "http://www.hokus.ai"

# After
API_URL: "https://api.hokus.ai"
AUTH_URL: "https://auth.hokus.ai"
FRONTEND_URL: "https://www.hokus.ai"
```

## Testing Checklist

- [ ] HTTPS endpoint responds correctly
- [ ] HTTP redirects to HTTPS
- [ ] No mixed content warnings in browser
- [ ] API calls use HTTPS
- [ ] WebSocket connections (if any) use WSS
- [ ] OAuth callbacks use HTTPS URLs
- [ ] CORS headers updated for HTTPS origins

## Common Issues and Solutions

### Issue: Certificate Domain Mismatch
**Solution**: Ensure the certificate includes your specific subdomain or use wildcard

### Issue: Mixed Content Warnings
**Solution**: Update all resource URLs in:
- Frontend assets
- API responses
- Configuration files
- Database stored URLs

### Issue: CORS Errors After HTTPS
**Solution**: Update CORS allowed origins:
```javascript
const corsOptions = {
  origin: [
    'https://www.hokus.ai',
    'https://app.hokus.ai',
    'https://api.hokus.ai'
  ]
};
```

### Issue: Health Checks Failing
**Solution**: Ensure health check uses correct protocol:
```hcl
health_check {
  protocol = "HTTPS"  # or keep as HTTP if backend doesn't support HTTPS
  path     = "/health"
}
```

## Coordination Checklist

When implementing HTTPS, coordinate with the platform team on:

- [ ] Certificate provisioning (shared vs separate)
- [ ] DNS validation record management
- [ ] Deployment timeline to minimize downtime
- [ ] Update API endpoint URLs in dependent services
- [ ] Update documentation and client configurations
- [ ] Monitor for any integration issues

## Security Best Practices

1. **Use Strong SSL Policy**: Minimum TLS 1.2
2. **Enable HSTS**: Add Strict-Transport-Security header
3. **Regular Security Scans**: Use SSL Labs to validate configuration
4. **Monitor Certificate Expiry**: Set up alerts 30 days before expiration
5. **Secure Cookies**: Update cookie settings to use Secure flag

## Contact Information

For questions or coordination:
- Platform Team: [contact info]
- DNS Management: [contact info]
- Certificate Issues: [contact info]