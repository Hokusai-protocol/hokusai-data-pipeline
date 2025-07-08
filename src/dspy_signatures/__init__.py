"""DSPy Signature Library for Hokusai Platform.

This module provides a comprehensive library of reusable DSPy signatures
for common prompt patterns across the platform.
"""

from .registry import SignatureRegistry, get_global_registry
from .base import BaseSignature, SignatureField
from .loader import SignatureLoader

# Import all signature categories
from .text_generation import (
    DraftText,
    ReviseText,
    ExpandText,
    RefineText
)

from .analysis import (
    CritiqueText,
    SummarizeText,
    ExtractInfo,
    ClassifyText
)

from .conversation import (
    RespondToUser,
    ClarifyIntent,
    GenerateFollowUp,
    ResolveQuery
)

from .task_specific import (
    EmailDraft,
    CodeGeneration,
    DataAnalysis,
    ReportGeneration
)

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
    "ReportGeneration"
]
