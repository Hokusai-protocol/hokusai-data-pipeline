#!/usr/bin/env python3
"""Analyze the endpoint audit results."""

import json
import sys
from collections import defaultdict

def analyze_audit_report(report_file: str):
    """Analyze the audit report and provide insights."""
    with open(report_file, 'r') as f:
        report = json.load(f)
    
    print("="*80)
    print("HOKUSAI API ENDPOINT AUDIT ANALYSIS")
    print("="*80)
    
    summary = report['summary']
    print(f"Audit Date: {report['audit_timestamp']}")
    print(f"Base URL: {report['base_url']}")
    print(f"Total Endpoints: {summary['total_endpoints']}")
    print(f"Success Rate: {summary['success_rate']}")
    print(f"Average Response Time: {summary['average_response_time_ms']} ms")
    print()
    
    # Status code analysis
    print("STATUS CODE DISTRIBUTION:")
    print("-" * 30)
    status_dist = report['status_code_distribution']
    for code, count in sorted(status_dist.items()):
        percentage = (count / summary['total_endpoints']) * 100
        status_name = {
            '200': 'OK',
            '401': 'Unauthorized', 
            '403': 'Forbidden',
            '404': 'Not Found',
            '422': 'Unprocessable Entity',
            '500': 'Internal Server Error',
            '502': 'Bad Gateway',
            '503': 'Service Unavailable'
        }.get(str(code), 'Other')
        print(f"{code} {status_name:<20}: {count:>3} ({percentage:5.1f}%)")
    print()
    
    # Working endpoints
    working_endpoints = [ep for ep in report['detailed_results'] if ep['success']]
    print(f"WORKING ENDPOINTS ({len(working_endpoints)}):")
    print("-" * 40)
    for ep in sorted(working_endpoints, key=lambda x: x['path']):
        print(f"✅ {ep['method']:<6} {ep['path']:<50} [{ep['status_code']}]")
    print()
    
    # Auth-related failures (401/403)
    auth_failures = [ep for ep in report['detailed_results'] 
                    if not ep['success'] and ep['status_code'] in [401, 403]]
    if auth_failures:
        print(f"AUTHENTICATION REQUIRED ENDPOINTS ({len(auth_failures)}):")
        print("-" * 50)
        for ep in sorted(auth_failures, key=lambda x: x['path']):
            print(f"🔒 {ep['method']:<6} {ep['path']:<50} [{ep['status_code']}]")
        print()
    
    # Missing endpoints (404)
    missing_endpoints = [ep for ep in report['detailed_results'] 
                        if not ep['success'] and ep['status_code'] == 404]
    if missing_endpoints:
        print(f"MISSING/NOT IMPLEMENTED ENDPOINTS ({len(missing_endpoints)}):")
        print("-" * 55)
        by_file = defaultdict(list)
        for ep in missing_endpoints:
            by_file[ep['file']].append(ep)
        
        for file_name, endpoints in sorted(by_file.items()):
            print(f"\n📁 {file_name}:")
            for ep in sorted(endpoints, key=lambda x: x['path']):
                print(f"   ❌ {ep['method']:<6} {ep['path']}")
    
    # File-based analysis
    print(f"\nBY FILE ANALYSIS:")
    print("-" * 20)
    file_results = report['results_by_file']
    for file_name, stats in sorted(file_results.items()):
        success_rate = (stats['success'] / stats['total']) * 100
        status = "🟢" if success_rate > 80 else "🟡" if success_rate > 50 else "🔴"
        print(f"{status} {file_name:<25}: {stats['success']:>2}/{stats['total']:>2} ({success_rate:5.1f}%)")
    
    print(f"\nRECOMMENDations:")
    print("-" * 20)
    
    auth_count = len(auth_failures)
    missing_count = len(missing_endpoints)
    working_count = len(working_endpoints)
    
    if working_count > 0:
        print(f"✅ {working_count} endpoints are working correctly")
    
    if auth_count > 0:
        print(f"🔑 {auth_count} endpoints require authentication - provide API key for full testing")
    
    if missing_count > 0:
        print(f"⚠️  {missing_count} endpoints return 404 - may be:")
        print("   - Not implemented yet")
        print("   - Requiring specific URL parameters")
        print("   - Behind different routing")
    
    # High-level health assessment
    if working_count > summary['total_endpoints'] * 0.7:
        print("\n🎉 API appears to be healthy with most core endpoints working")
    elif working_count > summary['total_endpoints'] * 0.4:
        print("\n⚠️  API has moderate issues - some endpoints may need attention")
    else:
        print("\n🚨 API appears to have significant issues - many endpoints not responding")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_audit.py <audit_report.json>")
        sys.exit(1)
    
    try:
        analyze_audit_report(sys.argv[1])
    except FileNotFoundError:
        print(f"Error: Report file '{sys.argv[1]}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: '{sys.argv[1]}' is not valid JSON")
        sys.exit(1)
    except Exception as e:
        print(f"Error analyzing report: {e}")
        sys.exit(1)