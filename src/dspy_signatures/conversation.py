"""Conversation signatures for DSPy."""

from typing import List, Dict, Any

from .base import BaseSignature, SignatureField


class RespondToUser(BaseSignature):
    """Generate appropriate responses to user messages in conversations."""
    
    category = "conversation"
    tags = ["conversation", "response", "dialogue"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="user_message",
                description="The user's message to respond to",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="conversation_history",
                description="Previous messages in the conversation",
                type_hint=list,
                required=False,
                default=[]
            ),
            SignatureField(
                name="persona",
                description="The assistant's persona or role",
                type_hint=str,
                required=False,
                default="helpful assistant"
            ),
            SignatureField(
                name="context",
                description="Additional context about the conversation",
                type_hint=dict,
                required=False,
                default={}
            ),
            SignatureField(
                name="tone",
                description="Desired tone of response (friendly, professional, casual)",
                type_hint=str,
                required=False,
                default="friendly"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="response",
                description="The generated response to the user",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="intent_detected",
                description="The detected intent of the user message",
                type_hint=str,
                required=False
            ),
            SignatureField(
                name="follow_up_needed",
                description="Whether a follow-up question is recommended",
                type_hint=bool,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "user_message": "Can you help me understand how machine learning works?",
                "persona": "AI tutor",
                "tone": "friendly",
                "response": "I'd be happy to explain machine learning! Think of it as teaching computers to learn from examples, just like how you learned to recognize cats and dogs as a child...",
                "intent_detected": "request_explanation",
                "follow_up_needed": True
            }
        ]


class ClarifyIntent(BaseSignature):
    """Generate clarifying questions to better understand user intent."""
    
    category = "conversation"
    tags = ["conversation", "clarification", "intent"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="user_message",
                description="The ambiguous or unclear user message",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="possible_intents",
                description="List of possible interpretations",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="context",
                description="Conversation context",
                type_hint=dict,
                required=False,
                default={}
            ),
            SignatureField(
                name="max_options",
                description="Maximum number of options to present",
                type_hint=int,
                required=False,
                default=3
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="clarification_question",
                description="The clarifying question to ask",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="intent_hypothesis",
                description="Best guess at user intent",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="options_provided",
                description="Specific options included in the question",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "user_message": "I need help with Python",
                "possible_intents": ["learn_basics", "debug_code", "best_practices", "installation"],
                "clarification_question": "I'd be happy to help with Python! Are you looking to: 1) Learn Python basics, 2) Debug existing code, or 3) Get help with installation?",
                "intent_hypothesis": "learn_basics",
                "options_provided": ["Learn Python basics", "Debug existing code", "Get help with installation"]
            }
        ]


class GenerateFollowUp(BaseSignature):
    """Generate relevant follow-up questions to deepen conversation."""
    
    category = "conversation"
    tags = ["conversation", "follow-up", "engagement"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="conversation",
                description="Recent conversation exchange",
                type_hint=dict,
                required=True
            ),
            SignatureField(
                name="topic",
                description="Main topic of discussion",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="goal",
                description="Goal of the follow-up (deepen, explore, confirm)",
                type_hint=str,
                required=False,
                default="deepen"
            ),
            SignatureField(
                name="num_questions",
                description="Number of follow-up questions to generate",
                type_hint=int,
                required=False,
                default=3
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="follow_up_questions",
                description="List of follow-up questions",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="rationale",
                description="Reasoning for the selected questions",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="question_types",
                description="Types of questions generated (open, closed, probing)",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "conversation": {"user": "I'm learning web development", "assistant": "That's great! Web development is a valuable skill."},
                "topic": "web development learning",
                "goal": "deepen",
                "follow_up_questions": [
                    "What aspect of web development interests you most - frontend, backend, or full-stack?",
                    "Do you have any specific projects in mind you'd like to build?",
                    "What's your current programming experience level?"
                ],
                "rationale": "Questions designed to understand learning goals and tailor advice",
                "question_types": ["open", "open", "closed"]
            }
        ]


class ResolveQuery(BaseSignature):
    """Resolve user queries with comprehensive answers."""
    
    category = "conversation"
    tags = ["conversation", "query", "resolution"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="query",
                description="The user's query to resolve",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="knowledge_base",
                description="Available knowledge or context to draw from",
                type_hint=dict,
                required=False,
                default={}
            ),
            SignatureField(
                name="constraints",
                description="Any constraints on the answer (length, complexity, scope)",
                type_hint=dict,
                required=False,
                default={}
            ),
            SignatureField(
                name="answer_format",
                description="Preferred answer format (detailed, concise, step_by_step)",
                type_hint=str,
                required=False,
                default="detailed"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="answer",
                description="The comprehensive answer to the query",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="sources",
                description="Sources or references used",
                type_hint=list,
                required=False
            ),
            SignatureField(
                name="confidence",
                description="Confidence level in the answer",
                type_hint=float,
                required=True
            ),
            SignatureField(
                name="caveats",
                description="Any limitations or caveats to the answer",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "query": "What are the main differences between Python and JavaScript?",
                "answer_format": "detailed",
                "answer": "Python and JavaScript are both popular programming languages with key differences:\n\n1. **Type System**: Python is dynamically typed with strong typing, while JavaScript is dynamically typed with weak typing...\n\n2. **Execution Environment**: Python runs on servers/desktops, JavaScript originally for browsers but now also server-side with Node.js...\n\n3. **Syntax**: Python emphasizes readability with indentation, JavaScript uses C-style syntax with braces...",
                "sources": ["Programming language documentation", "Industry surveys"],
                "confidence": 0.95,
                "caveats": ["Differences may vary with specific implementations", "Both languages continue to evolve"]
            }
        ]