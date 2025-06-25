# Release Process for hokusai-ml-platform

This document outlines the process for releasing new versions of the hokusai-ml-platform package.

## Pre-Release Checklist

Before creating a release, ensure:

- [ ] All tests pass locally and on CI
- [ ] Documentation is up to date
- [ ] CHANGELOG.md has been updated with release notes
- [ ] Version number in `pyproject.toml` has been updated
- [ ] Version number in `src/hokusai/__init__.py` has been updated
- [ ] Examples have been tested with the new version

## Release Steps

### 1. Update Version Numbers

Update the version in two places:

```bash
# In hokusai-ml-platform/pyproject.toml
version = "X.Y.Z"

# In hokusai-ml-platform/src/hokusai/__init__.py
__version__ = "X.Y.Z"
```

### 2. Update CHANGELOG.md

Move items from "Unreleased" to a new version section:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features...

### Changed
- Changes...

### Fixed
- Bug fixes...
```

### 3. Create a Pull Request

```bash
git checkout -b release/vX.Y.Z
git add -A
git commit -m "chore: prepare release vX.Y.Z"
git push origin release/vX.Y.Z
```

Create a PR and ensure all checks pass.

### 4. Merge and Tag

After PR approval and merge:

```bash
git checkout main
git pull origin main
git tag -a vX.Y.Z -m "Release version X.Y.Z"
git push origin vX.Y.Z
```

### 5. Create GitHub Release

1. Go to [Releases](https://github.com/Hokusai-protocol/hokusai-data-pipeline/releases)
2. Click "Draft a new release"
3. Select the tag `vX.Y.Z`
4. Title: `hokusai-ml-platform vX.Y.Z`
5. Copy release notes from CHANGELOG.md
6. Click "Publish release"

This will trigger the automated publishing workflow.

### 6. Verify Publication

For TestPyPI releases:
- Check https://test.pypi.org/project/hokusai-ml-platform/
- Test installation: `pip install -i https://test.pypi.org/simple/ hokusai-ml-platform`

For PyPI releases:
- Check https://pypi.org/project/hokusai-ml-platform/
- Test installation: `pip install hokusai-ml-platform`

## Post-Release

### 1. Update Documentation

- Update installation instructions if needed
- Update any version-specific documentation
- Announce release in appropriate channels

### 2. Start Next Development Cycle

```bash
git checkout -b chore/post-release-vX.Y.Z
```

Update versions to next development version (e.g., X.Y.Z+1.dev0):

```bash
# In pyproject.toml and __init__.py
version = "X.Y.Z+1.dev0"
```

Add new "Unreleased" section to CHANGELOG.md:

```markdown
## [Unreleased]

### Added
### Changed
### Fixed
```

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Incompatible API changes
- **MINOR** (0.Y.0): Backwards-compatible functionality additions
- **PATCH** (0.0.Z): Backwards-compatible bug fixes

## Emergency Patches

For critical fixes:

1. Create patch from the release tag:
   ```bash
   git checkout -b hotfix/vX.Y.Z+1 vX.Y.Z
   ```

2. Apply fixes and follow abbreviated release process

3. Cherry-pick fixes back to main

## Manual Publishing (Fallback)

If automated publishing fails:

```bash
cd hokusai-ml-platform
python -m build
python -m twine upload dist/*
```

Ensure you have PyPI credentials configured.