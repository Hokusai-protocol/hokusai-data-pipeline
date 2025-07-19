# Product Requirements Document: Resolve Routing Conflicts

## Objectives

The primary objective is to resolve routing conflicts in the Hokusai API infrastructure that prevent proper MLflow endpoint access through the API proxy. The current routing configuration causes all `/api*` paths to be incorrectly routed to the API service instead of being properly distributed to their intended services, particularly blocking access to MLflow via `/api/mlflow/*` paths.

## Personas

### Primary Users
- **Third-party developers**: External developers integrating with Hokusai who need reliable API access to register models
- **Data scientists**: Users of the Hokusai ML platform who need MLflow connectivity for model tracking and registration
- **Platform administrators**: DevOps team managing the Hokusai infrastructure

### Secondary Users
- **Internal developers**: Hokusai team members who need clear routing documentation
- **API consumers**: Any service or application consuming Hokusai APIs

## Success Criteria

1. **Routing Resolution**: All API paths correctly route to their intended services without conflicts
2. **MLflow Access**: Third-party developers can successfully access MLflow endpoints via the API proxy
3. **Documentation**: Complete routing documentation that clearly shows which paths go to which services
4. **Backward Compatibility**: Existing API consumers continue to work without breaking changes
5. **Test Coverage**: Automated tests verify routing behavior and prevent regression
6. **Successful Registration**: `test_real_registration.py` runs successfully with a live API key

## Tasks

### 1. Analyze Current Routing Configuration
- Review ALB routing rules and priorities
- Document all current routing paths and their destinations
- Identify all conflicting routes beyond the known `/api*` issue

### 2. Design Routing Solution
- Evaluate the three proposed options from FINAL_TEST_REPORT.md:
  - Option 1: Make ALB routing rules more specific
  - Option 2: Remove 'api' from MLflow proxy paths
  - Option 3: Use direct MLflow paths
- Select the best approach considering backward compatibility and clarity
- Create routing design document

### 3. Implement Routing Changes
- Update ALB routing rules or proxy path configurations based on chosen solution
- Ensure no breaking changes to existing API endpoints
- Update any hardcoded paths in the codebase

### 4. Update API Documentation
- Document all API routing paths in a central location
- Update API reference documentation
- Create migration guide if paths change

### 5. Create Routing Tests
- Write automated tests to verify routing behavior
- Test all API endpoints to ensure correct routing
- Add tests that would catch routing conflicts

### 6. Test Model Registration Flow
- Run `test_real_registration.py` with a live API key
- Verify MLflow connectivity through the API proxy
- Ensure third-party model registration works end-to-end

### 7. Deploy and Monitor
- Deploy routing changes to development environment
- Monitor for any routing errors or issues
- Deploy to production after verification