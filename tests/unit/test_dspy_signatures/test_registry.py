"""Unit tests for DSPy signature registry."""

import pytest

from src.dspy_signatures.registry import SignatureRegistry
from src.dspy_signatures.base import BaseSignature, SignatureField
from src.dspy_signatures.metadata import SignatureMetadata


class TestSignatureRegistry:
    """Test cases for SignatureRegistry."""
    
    def test_registry_initialization(self):
        """Test registry initializes correctly."""
        registry = SignatureRegistry()
        assert registry.signatures == {}
        assert registry.aliases == {}
        assert registry.metadata == {}
    
    def test_register_signature(self):
        """Test registering a new signature."""
        registry = SignatureRegistry()
        
        # Create a test signature class
        class TestSignature(BaseSignature):
            """A test signature."""
            
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Test input", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Test output", str, True)]
        
        signature = TestSignature()
        
        metadata = SignatureMetadata(
            name="TestSignature",
            description="A test signature",
            category="test",
            tags=["test", "example"],
            version="1.0.0"
        )
        
        # Register the signature
        registry.register(signature, metadata)
        
        assert "TestSignature" in registry.signatures
        assert registry.signatures["TestSignature"] == signature
        assert registry.metadata["TestSignature"] == metadata
    
    def test_register_duplicate_signature(self):
        """Test registering duplicate signature raises error."""
        registry = SignatureRegistry()
        
        class TestSignature(BaseSignature):
            """A test signature."""
            
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Test input", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Test output", str, True)]
        
        signature = TestSignature()
        
        metadata = SignatureMetadata(
            name="TestSignature",
            description="A test signature",
            category="test",
            tags=["test"],
            version="1.0.0"
        )
        
        registry.register(signature, metadata)
        
        # Attempt to register again should raise error
        with pytest.raises(ValueError, match="Signature 'TestSignature' already registered"):
            registry.register(signature, metadata)
    
    def test_get_signature(self):
        """Test retrieving a registered signature."""
        registry = SignatureRegistry()
        
        class TestSignature(BaseSignature):
            """A test signature."""
            
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Test input", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Test output", str, True)]
        
        signature = TestSignature()
        
        metadata = SignatureMetadata(
            name="TestSignature",
            description="A test signature",
            category="test",
            tags=["test"],
            version="1.0.0"
        )
        
        registry.register(signature, metadata)
        
        # Get the signature
        retrieved = registry.get("TestSignature")
        assert retrieved == signature
    
    def test_get_nonexistent_signature(self):
        """Test getting non-existent signature raises error."""
        registry = SignatureRegistry()
        
        with pytest.raises(KeyError, match="Signature 'NonExistent' not found"):
            registry.get("NonExistent")
    
    def test_create_alias(self):
        """Test creating an alias for a signature."""
        registry = SignatureRegistry()
        
        class TestSignature(BaseSignature):
            """A test signature."""
            
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Test input", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Test output", str, True)]
        
        signature = TestSignature()
        
        metadata = SignatureMetadata(
            name="TestSignature",
            description="A test signature",
            category="test",
            tags=["test"],
            version="1.0.0"
        )
        
        registry.register(signature, metadata)
        
        # Create alias
        registry.create_alias("QuickTest", "TestSignature")
        
        assert registry.aliases["QuickTest"] == "TestSignature"
        assert registry.get("QuickTest") == signature
    
    def test_create_alias_for_nonexistent_signature(self):
        """Test creating alias for non-existent signature raises error."""
        registry = SignatureRegistry()
        
        with pytest.raises(KeyError, match="Cannot create alias"):
            registry.create_alias("QuickTest", "NonExistent")
    
    def test_list_signatures(self):
        """Test listing all registered signatures."""
        registry = SignatureRegistry()
        
        # Register multiple signatures
        for i in range(3):
            # Create a unique class for each iteration
            attrs = {
                '__module__': '__main__',
                'get_input_fields': classmethod(lambda cls: [SignatureField("input", "Test input", str, True)]),
                'get_output_fields': classmethod(lambda cls: [SignatureField("output", "Test output", str, True)])
            }
            TestSig = type(f'TestSignature{i}', (BaseSignature,), attrs)
            
            sig = TestSig()
            
            metadata = SignatureMetadata(
                name=f"TestSignature{i}",
                description=f"Test signature {i}",
                category="test",
                tags=["test"],
                version="1.0.0"
            )
            
            registry.register(sig, metadata)
        
        signatures = registry.list_signatures()
        assert len(signatures) == 3
        assert all(f"TestSignature{i}" in signatures for i in range(3))
    
    def test_search_by_category(self):
        """Test searching signatures by category."""
        registry = SignatureRegistry()
        
        # Register signatures with different categories
        categories = ["text", "text", "analysis", "conversation"]
        
        for i, category in enumerate(categories):
            # Create a unique class for each iteration
            attrs = {
                '__module__': '__main__',
                'get_input_fields': classmethod(lambda cls: [SignatureField("input", "Test input", str, True)]),
                'get_output_fields': classmethod(lambda cls: [SignatureField("output", "Test output", str, True)])
            }
            TestSig = type(f'Signature{i}', (BaseSignature,), attrs)
            
            sig = TestSig()
            
            metadata = SignatureMetadata(
                name=f"Signature{i}",
                description=f"Signature {i}",
                category=category,
                tags=[category],
                version="1.0.0"
            )
            
            registry.register(sig, metadata)
        
        # Search by category
        text_sigs = registry.search(category="text")
        assert len(text_sigs) == 2
        
        analysis_sigs = registry.search(category="analysis")
        assert len(analysis_sigs) == 1
    
    def test_search_by_tags(self):
        """Test searching signatures by tags."""
        registry = SignatureRegistry()
        
        # Register signatures with different tags
        tag_sets = [
            ["email", "generation"],
            ["email", "analysis"],
            ["code", "generation"],
            ["data", "analysis"]
        ]
        
        for i, tags in enumerate(tag_sets):
            # Create a unique class for each iteration
            attrs = {
                '__module__': '__main__',
                'get_input_fields': classmethod(lambda cls: [SignatureField("input", "Test input", str, True)]),
                'get_output_fields': classmethod(lambda cls: [SignatureField("output", "Test output", str, True)])
            }
            TestSig = type(f'Signature{i}', (BaseSignature,), attrs)
            
            sig = TestSig()
            
            metadata = SignatureMetadata(
                name=f"Signature{i}",
                description=f"Signature {i}",
                category="test",
                tags=tags,
                version="1.0.0"
            )
            
            registry.register(sig, metadata)
        
        # Search by tags
        email_sigs = registry.search(tags=["email"])
        assert len(email_sigs) == 2
        
        generation_sigs = registry.search(tags=["generation"])
        assert len(generation_sigs) == 2
        
        # Search with multiple tags (AND operation)
        email_gen_sigs = registry.search(tags=["email", "generation"])
        assert len(email_gen_sigs) == 1
    
    def test_get_metadata(self):
        """Test retrieving signature metadata."""
        registry = SignatureRegistry()
        
        class TestSignature(BaseSignature):
            """A test signature."""
            
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Test input", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Test output", str, True)]
        
        signature = TestSignature()
        
        metadata = SignatureMetadata(
            name="TestSignature",
            description="A test signature",
            category="test",
            tags=["test"],
            version="1.0.0",
            examples=["Example 1", "Example 2"]
        )
        
        registry.register(signature, metadata)
        
        retrieved_metadata = registry.get_metadata("TestSignature")
        assert retrieved_metadata == metadata
        assert retrieved_metadata.examples == ["Example 1", "Example 2"]
    
    def test_check_compatibility(self):
        """Test checking signature compatibility."""
        registry = SignatureRegistry()
        
        # Create signatures with input/output fields
        class Signature1(BaseSignature):
            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("text", "Text", str, True),
                    SignatureField("context", "Context", str, False)
                ]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("response", "Response", str, True)]
        
        class Signature2(BaseSignature):
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("response", "Response", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("analysis", "Analysis", str, True)]
        
        class Signature3(BaseSignature):
            @classmethod
            def get_input_fields(cls):
                return [SignatureField("data", "Data", str, True)]
            
            @classmethod
            def get_output_fields(cls):
                return [SignatureField("result", "Result", str, True)]
        
        for sig_class in [Signature1, Signature2, Signature3]:
            sig = sig_class()
            metadata = SignatureMetadata(
                name=sig_class.__name__,
                description=f"{sig_class.__name__} description",
                category="test",
                tags=["test"],
                version="1.0.0"
            )
            registry.register(sig, metadata)
        
        # Check compatibility
        assert registry.check_compatibility("Signature1", "Signature2") == True
        assert registry.check_compatibility("Signature1", "Signature3") == False
        assert registry.check_compatibility("Signature2", "Signature3") == False
    
    def test_export_catalog(self):
        """Test exporting signature catalog."""
        registry = SignatureRegistry()
        
        # Register a few signatures
        for i in range(2):
            # Create a unique class for each iteration
            attrs = {
                '__module__': '__main__',
                'get_input_fields': classmethod(lambda cls: [SignatureField("input", "Test input", str, True)]),
                'get_output_fields': classmethod(lambda cls: [SignatureField("output", "Test output", str, True)])
            }
            TestSig = type(f'TestSignature{i}', (BaseSignature,), attrs)
            
            sig = TestSig()
            
            metadata = SignatureMetadata(
                name=f"TestSignature{i}",
                description=f"Test signature {i}",
                category="test",
                tags=["test", f"tag{i}"],
                version="1.0.0"
            )
            
            registry.register(sig, metadata)
        
        catalog = registry.export_catalog()
        
        assert len(catalog) == 2
        assert all("name" in entry for entry in catalog)
        assert all("metadata" in entry for entry in catalog)
        assert catalog[0]["name"] == "TestSignature0"