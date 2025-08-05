# Instructions for removing old routing rules after applying routing-fix.tf

# After the new routing rules are successfully deployed, remove these old rules:

# 1. In main.tf, remove or comment out:
#    - aws_lb_listener_rule.api (around line 335)
#    This is the problematic /api* catch-all rule

# 2. In https-updates.tf, remove or comment out:
#    - aws_lb_listener_rule.https_api (around line 28)
#    This is the HTTPS version of the same problematic rule

# The new rules in routing-fix.tf will replace these with more specific patterns.

# Migration steps:
# 1. Apply routing-fix.tf first (creates new rules)
# 2. Verify routing works correctly
# 3. Remove the old rules mentioned above
# 4. Apply again to remove old rules

# This approach ensures zero downtime during the migration.