"""DSPy Signature Library for Hokusai Platform.

This module provides a comprehensive library of reusable DSPy signatures
for common prompt patterns across the platform.
"""

from .analysis import ClassifyText, CritiqueText, ExtractInfo, SummarizeText
from .base import BaseSignature, SignatureField
from .conversation import ClarifyIntent, GenerateFollowUp, ResolveQuery, RespondToUser
from .loader import SignatureLoader
from .registry import SignatureRegistry, get_global_registry
from .task_specific import CodeGeneration, DataAnalysis, EmailDraft, ReportGeneration

# Import all signature categories
from .text_generation import DraftText, ExpandText, RefineText, ReviseText

# Initialize global registry and register all signatures
_registry = get_global_registry()

# Register text generation signatures
for sig in [DraftText, ReviseText, ExpandText, RefineText]:
    _registry.register(sig(), sig.get_metadata())

# Register analysis signatures
for sig in [CritiqueText, SummarizeText, ExtractInfo, ClassifyText]:
    _registry.register(sig(), sig.get_metadata())

# Register conversation signatures
for sig in [RespondToUser, ClarifyIntent, GenerateFollowUp, ResolveQuery]:
    _registry.register(sig(), sig.get_metadata())

# Register task-specific signatures
for sig in [EmailDraft, CodeGeneration, DataAnalysis, ReportGeneration]:
    _registry.register(sig(), sig.get_metadata())

# Create common aliases
_registry.create_alias("Email", "EmailDraft")
_registry.create_alias("Code", "CodeGeneration")
_registry.create_alias("Summarize", "SummarizeText")
_registry.create_alias("Draft", "DraftText")
_registry.create_alias("Revise", "ReviseText")
_registry.create_alias("Respond", "RespondToUser")

__all__ = [
    # Core classes
    "SignatureRegistry",
    "get_global_registry",
    "BaseSignature",
    "SignatureField",
    "SignatureLoader",
    # Text generation
    "DraftText",
    "ReviseText",
    "ExpandText",
    "RefineText",
    # Analysis
    "CritiqueText",
    "SummarizeText",
    "ExtractInfo",
    "ClassifyText",
    # Conversation
    "RespondToUser",
    "ClarifyIntent",
    "GenerateFollowUp",
    "ResolveQuery",
    # Task-specific
    "EmailDraft",
    "CodeGeneration",
    "DataAnalysis",
    "ReportGeneration",
]
