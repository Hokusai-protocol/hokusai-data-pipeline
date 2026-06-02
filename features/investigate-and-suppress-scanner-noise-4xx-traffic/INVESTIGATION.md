# HOK-1977 Investigation

## Observed Scanner Traffic

- API service recorded 560 4xx responses.
- MLflow service recorded 2753 4xx responses.
- The dominant source called out in the issue was `10.0.102.142`.
- Seed paths from production samples included `/mgmt/tm/util/bash`, `/ui/login`, `/login.action`, and `/api/jsonws`.

Direct CloudWatch or ALB log sampling was not performed from this dev machine. Per local repo guidance, external endpoints are not reachable from the development environment, so this investigation is based on the issue samples plus common scanner templates.

Sampled: partial (seed list + known scanner templates)

## Path Samples

- `/mgmt/tm/util/bash`
- `/ui/login`
- `/login.action`
- `/api/jsonws`
- `/api/jsonws/invoke`
- `/wp-admin/`
- `/phpmyadmin/`
- `/cgi-bin/`
- `/.env`
- `/.git/`
- `/manager/html`
- `/server-status`
- `/actuator/`
- `/jenkins/`
- `/boaform/admin/formLogin`

## Final Deny List

Exact paths shipped in `src/api/middleware/scanner_filter.py`:

- `/.env`
- `/api/jsonws`
- `/boaform/admin/formlogin`
- `/login.action`
- `/manager/html`
- `/server-status`
- `/ui/login`

Prefix matches shipped in `src/api/middleware/scanner_filter.py`:

- `/.git/`
- `/.aws/`
- `/actuator/`
- `/api/jsonws/`
- `/autodiscover/`
- `/cgi-bin/`
- `/console/`
- `/geoserver/`
- `/hudson/`
- `/jenkins/`
- `/mgmt/`
- `/nifi/`
- `/owa/`
- `/phpmyadmin/`
- `/solr/`
- `/wp-admin/`

## Allowlist

These prefixes take precedence over the deny list and continue into the application:

- `/health`
- `/ready`
- `/live`
- `/metrics`
- `/docs`
- `/redoc`
- `/openapi.json`
- `/api/v1/`
- `/api/2.0/mlflow/`
- `/api/2.0/preview/mlflow/`
- `/api/mlflow/`
- `/mlflow/`
- `/api/models`
- `/models`
- `/api/health`

## Infra Follow-up

This PR only suppresses API noise inside the FastAPI process. MLflow does not run through this middleware path, so its scanner suppression needs to happen at the load balancer or WAF layer.

Recommended follow-up in `hokusai-infrastructure`:

```hcl
resource "aws_lb_listener_rule" "scanner_noise_fixed_response" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 25

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = ""
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = [
        "/mgmt/*",
        "/ui/login",
        "/login.action",
        "/api/jsonws",
        "/api/jsonws/*",
        "/wp-admin/*",
        "/phpmyadmin/*",
        "/cgi-bin/*",
        "/.env",
      ]
    }
  }
}
```

Apply an equivalent rule to both:

- the API ALB listener in `environments/development/` and `environments/production/`
- the MLflow ALB listener in `environments/development/` and `environments/production/`

Optional WAF follow-up:

- add a byte-match or regex rule for the same scanner path set
- optionally combine it with source-IP rate limiting if scanner volume increases

Recommended tracking:

- file a separate Linear follow-up issue against `hokusai-infrastructure`
- use that issue to land ALB listener rules and any WAF ACL updates for both API and MLflow
