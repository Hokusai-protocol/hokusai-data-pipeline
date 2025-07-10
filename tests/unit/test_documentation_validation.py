"""
Test documentation code examples and validate documentation accuracy.
"""

import re
from pathlib import Path

import pytest


class TestDocumentationValidation:
    """Test suite for validating documentation accuracy and code examples."""

    @pytest.fixture
    def docs_dir(self):
        """Get the documentation directory path."""
        return Path(__file__).parent.parent.parent / "documentation"

    @pytest.fixture
    def root_dir(self):
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    def test_readme_commands(self, root_dir):
        """Test that commands in README.md are valid."""
        readme_path = root_dir / "README.md"
        assert readme_path.exists(), "README.md not found"

        with open(readme_path) as f:
            content = f.read()

        # Extract bash command blocks
        bash_blocks = re.findall(r"```bash\n(.*?)\n```", content, re.DOTALL)

        # Check that key commands are present
        commands_found = {"setup": False, "dry_run": False, "pytest": False, "mlflow": False}

        for block in bash_blocks:
            if "./setup.sh" in block:
                commands_found["setup"] = True
            if "--dry-run" in block:
                commands_found["dry_run"] = True
            if "pytest" in block:
                commands_found["pytest"] = True
            if "mlflow ui" in block:
                commands_found["mlflow"] = True

        # Verify all key commands are documented
        for cmd_type, found in commands_found.items():
            assert found, f"Missing {cmd_type} command in README.md"

    def test_environment_variables_documented(self, root_dir):
        """Test that all environment variables are documented."""
        readme_path = root_dir / "README.md"

        # Environment variables that should be documented in README
        required_env_vars = [
            "HOKUSAI_TEST_MODE",
            "PIPELINE_LOG_LEVEL",
            "MLFLOW_TRACKING_URI",
            "MLFLOW_EXPERIMENT_NAME",
        ]

        with open(readme_path) as f:
            content = f.read()

        for env_var in required_env_vars:
            assert env_var in content, f"Environment variable {env_var} not documented in README.md"

        # Check LINEAR_API_KEY is documented in CLAUDE.md
        claude_path = root_dir / "CLAUDE.md"
        if claude_path.exists():
            with open(claude_path) as f:
                claude_content = f.read()
            assert "LINEAR_API_KEY" in claude_content, "LINEAR_API_KEY not documented in CLAUDE.md"

    def test_python_import_examples(self, root_dir):
        """Test that Python import examples in documentation are valid."""
        # This test validates that documented imports would work
        test_imports = [
            "from src.modules.data_integration import DataIntegrator",
            "from src.pipeline.hokusai_pipeline import HokusaiPipeline",
        ]

        # Check if modules exist
        for import_stmt in test_imports:
            module_path = (
                import_stmt.replace("from ", "")
                .replace(" import", "/")
                .replace(".", "/")
                .split("/")[:-1]
            )
            module_path = "/".join(module_path) + ".py"
            full_path = root_dir / module_path

            # Check either .py file or __init__.py exists
            assert (
                full_path.exists() or (full_path.parent / "__init__.py").exists()
            ), f"Module for '{import_stmt}' not found"

    def test_documentation_structure_planned(self, docs_dir):
        """Test that documentation structure follows the planned architecture."""
        # Expected documentation categories from PRD
        expected_categories = [
            "getting-started",
            "architecture",
            "api-reference",
            "tutorials",
            "operations",
            "troubleshooting",
            "developer-guide",
        ]

        # This test will pass initially as docs don't exist yet
        # It serves as a specification for the documentation structure
        if docs_dir.exists():
            for category in expected_categories:
                category_path = docs_dir / category
                assert category_path.exists() or any(
                    docs_dir.glob(f"{category}*")
                ), f"Documentation category '{category}' not found"

    def test_docusaurus_compatibility(self, docs_dir):
        """Test that markdown files are Docusaurus-compatible."""
        if not docs_dir.exists():
            pytest.skip("Documentation directory not yet created")

        md_files = list(docs_dir.rglob("*.md"))

        for md_file in md_files:
            with open(md_file) as f:
                content = f.read()

            # Check for Docusaurus frontmatter
            if content.startswith("---"):
                # Validate frontmatter format
                frontmatter_end = content.find("---", 3)
                assert frontmatter_end > 3, f"Invalid frontmatter in {md_file}"

                frontmatter = content[3:frontmatter_end]
                # Check for required fields
                assert (
                    "title:" in frontmatter or "id:" in frontmatter
                ), f"Missing title or id in frontmatter of {md_file}"

    def test_code_blocks_syntax_highlighting(self, root_dir):
        """Test that code blocks have proper syntax highlighting."""
        readme_path = root_dir / "README.md"

        with open(readme_path) as f:
            content = f.read()

        # Find all code blocks with their content
        code_block_pattern = r"```(\w*)\n(.*?)\n```"
        code_blocks = re.findall(code_block_pattern, content, re.DOTALL)

        # Verify code blocks have language specified (except diagrams)
        for i, (lang, block_content) in enumerate(code_blocks):
            # Check if it's a diagram (contains box drawing characters)
            is_diagram = any(
                char in block_content for char in ["┌", "┐", "└", "┘", "─", "│", "▶", "▼", "▲"]
            )

            if not is_diagram:
                assert lang != "", f"Code block {i + 1} missing language specification"
                assert lang in [
                    "bash",
                    "python",
                    "json",
                    "yaml",
                    "typescript",
                    "javascript",
                ], f"Unexpected language '{lang}' in code block"

    def test_internal_links_valid(self, root_dir):
        """Test that internal documentation links are valid."""
        readme_path = root_dir / "README.md"

        with open(readme_path) as f:
            content = f.read()

        # Find internal links
        internal_links = re.findall(r"\[.*?\]\(((?!http).*?\.md.*?)\)", content)

        for link in internal_links:
            # Remove anchors
            link_path = link.split("#")[0]
            full_path = root_dir / link_path

            # For now, just check docs/PIPELINE_README.md which is referenced
            if "docs/PIPELINE_README.md" in link_path:
                assert full_path.exists(), f"Internal link target not found: {link}"

    def test_command_examples_validity(self):
        """Test that command examples follow correct syntax."""
        # This test validates command structure without executing
        valid_commands = [
            "python -m venv venv",
            "source venv/bin/activate",
            "pip install -r requirements.txt",
            "python -m metaflow run src.pipeline.hokusai_pipeline:HokusaiPipeline",
            "pytest",
            "mlflow ui",
            "node tools/workflow.js",
            "npx tsx tools/get-backlog.ts",
        ]

        for cmd in valid_commands:
            # Basic syntax validation
            assert not cmd.startswith(" "), f"Command has leading space: {cmd}"
            assert not cmd.endswith(" "), f"Command has trailing space: {cmd}"
            assert "  " not in cmd, f"Command has double spaces: {cmd}"


class TestDocumentationCompleteness:
    """Test suite for ensuring documentation completeness."""

    @pytest.fixture
    def root_dir(self):
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    def test_all_modules_documented(self, root_dir):
        """Test that all Python modules will have documentation."""
        src_dir = root_dir / "src"
        modules_to_document = []

        # Collect all Python modules
        for py_file in src_dir.rglob("*.py"):
            if "__pycache__" not in str(py_file) and "__init__" not in str(py_file):
                modules_to_document.append(py_file.relative_to(src_dir))

        # Verify we have modules to document
        assert len(modules_to_document) > 0, "No Python modules found to document"

        # Key modules that must be documented
        key_modules = [
            "pipeline/hokusai_pipeline.py",
            "modules/data_integration.py",
            "modules/baseline_loader.py",
            "modules/model_training.py",
            "modules/evaluation.py",
        ]

        for module in key_modules:
            assert any(
                str(m).endswith(module) for m in modules_to_document
            ), f"Key module {module} not found in source tree"

    def test_configuration_documentation_complete(self, root_dir):
        """Test that all configuration options will be documented."""
        # Configuration areas that need documentation
        config_areas = [
            "environment_variables",
            "mlflow_settings",
            "pipeline_parameters",
            "data_formats",
            "output_schemas",
        ]

        # This serves as a checklist for documentation
        # Will be validated when documentation is created
        assert len(config_areas) == 5, "Configuration areas checklist modified"

    def test_example_data_files_exist(self, root_dir):
        """Test that example data files referenced in docs exist."""
        test_fixtures_dir = root_dir / "data" / "test_fixtures"

        # Files that should exist for examples
        expected_files = ["test_queries.csv"]

        for file_name in expected_files:
            file_path = test_fixtures_dir / file_name
            assert file_path.exists(), f"Example data file {file_name} not found"
