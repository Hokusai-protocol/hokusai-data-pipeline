"""Task-specific signatures for DSPy."""

from typing import List, Dict, Any, Optional

from .base import BaseSignature, SignatureField


class EmailDraft(BaseSignature):
    """Generate professional email drafts based on context and purpose."""
    
    category = "task_specific"
    tags = ["email", "communication", "writing"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="recipient",
                description="Email recipient name or address",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="subject",
                description="Email subject line",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="purpose",
                description="Purpose of the email (inform, request, follow-up, etc.)",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="key_points",
                description="Key points to include in the email",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="tone",
                description="Desired tone (professional, friendly, formal, casual)",
                type_hint=str,
                required=False,
                default="professional"
            ),
            SignatureField(
                name="sender_name",
                description="Name of the sender",
                type_hint=str,
                required=False,
                default=""
            ),
            SignatureField(
                name="attachments_mentioned",
                description="Any attachments to reference",
                type_hint=list,
                required=False,
                default=[]
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="email_body",
                description="The complete email body text",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="suggested_subject",
                description="Alternative subject line if needed",
                type_hint=str,
                required=False
            ),
            SignatureField(
                name="call_to_action",
                description="Identified call-to-action in the email",
                type_hint=str,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "recipient": "john.doe@company.com",
                "subject": "Project Update - Q4 Milestones",
                "purpose": "inform",
                "key_points": ["Milestone 1 completed", "On track for Q4", "Need budget approval for Phase 2"],
                "tone": "professional",
                "sender_name": "Jane Smith",
                "email_body": "Dear John,\n\nI hope this email finds you well. I wanted to provide you with an update on our Q4 project milestones.\n\nI'm pleased to report that we have successfully completed Milestone 1 as of last Friday. The team has done excellent work, and we remain on track to meet all Q4 deliverables.\n\nLooking ahead, we'll need budget approval for Phase 2 by the end of next week to maintain our timeline. Could we schedule a brief meeting to discuss this?\n\nPlease let me know if you need any additional information.\n\nBest regards,\nJane Smith",
                "call_to_action": "Schedule meeting for budget approval"
            }
        ]


class CodeGeneration(BaseSignature):
    """Generate code based on requirements and specifications."""
    
    category = "task_specific"
    tags = ["code", "programming", "development"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="description",
                description="Description of what the code should do",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="language",
                description="Programming language to use",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="framework",
                description="Framework or library to use (if applicable)",
                type_hint=str,
                required=False,
                default=""
            ),
            SignatureField(
                name="requirements",
                description="Specific requirements or constraints",
                type_hint=list,
                required=False,
                default=[]
            ),
            SignatureField(
                name="style_guide",
                description="Coding style guide to follow",
                type_hint=str,
                required=False,
                default="standard"
            ),
            SignatureField(
                name="include_tests",
                description="Whether to include unit tests",
                type_hint=bool,
                required=False,
                default=False
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="code",
                description="The generated code",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="explanation",
                description="Explanation of the code structure and logic",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="dependencies",
                description="List of dependencies or imports required",
                type_hint=list,
                required=False
            ),
            SignatureField(
                name="usage_example",
                description="Example of how to use the code",
                type_hint=str,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "description": "Function to validate email addresses",
                "language": "python",
                "requirements": ["Handle common email formats", "Return boolean"],
                "include_tests": True,
                "code": "import re\n\ndef validate_email(email: str) -> bool:\n    \"\"\"Validate email address format.\n    \n    Args:\n        email: Email address to validate\n        \n    Returns:\n        bool: True if valid, False otherwise\n    \"\"\"\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))\n\n# Unit tests\ndef test_validate_email():\n    assert validate_email('user@example.com') == True\n    assert validate_email('invalid.email') == False\n    assert validate_email('user@sub.example.com') == True",
                "explanation": "Uses regex pattern matching to validate email format. Checks for basic structure: local@domain.tld",
                "dependencies": ["re"],
                "usage_example": "is_valid = validate_email('user@example.com')"
            }
        ]


class DataAnalysis(BaseSignature):
    """Generate data analysis insights and recommendations."""
    
    category = "task_specific"
    tags = ["data", "analysis", "insights"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="data_description",
                description="Description of the data being analyzed",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="analysis_goals",
                description="Specific goals or questions to answer",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="metrics",
                description="Key metrics or KPIs to focus on",
                type_hint=list,
                required=False,
                default=[]
            ),
            SignatureField(
                name="constraints",
                description="Any constraints or limitations",
                type_hint=dict,
                required=False,
                default={}
            ),
            SignatureField(
                name="audience",
                description="Target audience for the analysis",
                type_hint=str,
                required=False,
                default="business stakeholders"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="analysis",
                description="Detailed analysis findings",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="insights",
                description="Key insights discovered",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="recommendations",
                description="Actionable recommendations",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="visualizations",
                description="Suggested visualizations to create",
                type_hint=list,
                required=False
            ),
            SignatureField(
                name="further_analysis",
                description="Suggestions for additional analysis",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "data_description": "E-commerce sales data for Q3 2024",
                "analysis_goals": ["Identify top performing products", "Find seasonal trends", "Customer segment analysis"],
                "metrics": ["revenue", "conversion_rate", "average_order_value"],
                "audience": "executive team",
                "analysis": "Q3 2024 e-commerce performance shows strong growth with total revenue up 23% YoY...",
                "insights": [
                    "Mobile purchases increased 45% and now represent 60% of total sales",
                    "Premium product line shows highest profit margins at 42%",
                    "Customer retention improved to 68% from 55% in Q2"
                ],
                "recommendations": [
                    "Invest in mobile app improvements to capture growing mobile trend",
                    "Expand premium product line given high margins",
                    "Implement loyalty program to further improve retention"
                ],
                "visualizations": ["Revenue trend line chart", "Product category pie chart", "Customer segment heatmap"]
            }
        ]


class ReportGeneration(BaseSignature):
    """Generate structured reports from data and requirements."""
    
    category = "task_specific"
    tags = ["report", "documentation", "writing"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="data",
                description="Data or information to include in the report",
                type_hint=dict,
                required=True
            ),
            SignatureField(
                name="report_type",
                description="Type of report (executive, technical, progress, financial)",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="sections",
                description="Required sections for the report",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="audience",
                description="Target audience for the report",
                type_hint=str,
                required=False,
                default="general"
            ),
            SignatureField(
                name="format",
                description="Output format preference (narrative, bullet_points, mixed)",
                type_hint=str,
                required=False,
                default="mixed"
            ),
            SignatureField(
                name="length_limit",
                description="Maximum length in words",
                type_hint=int,
                required=False,
                default=None
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="report",
                description="The complete generated report",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="executive_summary",
                description="Executive summary of the report",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="table_of_contents",
                description="Table of contents with sections",
                type_hint=list,
                required=False
            ),
            SignatureField(
                name="key_findings",
                description="List of key findings or highlights",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "data": {"project": "Website Redesign", "completion": 75, "milestones": ["Design complete", "Development 50%"], "risks": ["Timeline tight"], "budget_used": 0.6},
                "report_type": "progress",
                "sections": ["Overview", "Progress Update", "Milestones", "Risks", "Next Steps"],
                "audience": "project stakeholders",
                "format": "mixed",
                "report": "# Website Redesign Progress Report\n\n## Overview\nThe website redesign project is currently 75% complete and progressing according to plan...\n\n## Progress Update\n- Design phase: 100% complete\n- Development phase: 50% complete\n- Testing phase: Not started\n\n## Milestones Achieved\n✓ Design approval received\n✓ Frontend framework selected\n✓ Content migration plan finalized\n\n## Risks and Mitigation\n⚠️ Timeline constraints due to upcoming holiday season\n  - Mitigation: Added additional developer resource\n\n## Next Steps\n1. Complete development phase by month end\n2. Begin UAT testing in week 1 of next month\n3. Prepare launch communication plan",
                "executive_summary": "Website redesign is 75% complete with design finalized and development underway. Project remains on budget (60% utilized) but faces timeline pressure. Additional resources allocated to maintain schedule.",
                "table_of_contents": ["Overview", "Progress Update", "Milestones", "Risks", "Next Steps"],
                "key_findings": ["On budget", "Design complete", "Timeline risk identified", "Mitigation in place"]
            }
        ]