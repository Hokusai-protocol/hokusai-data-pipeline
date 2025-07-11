# Hokusai Documentation Map

This document clarifies the purpose and content of our two documentation directories.

## Directory Structure

```
hokusai-data-pipeline/
├── docs/                    # Internal developer documentation
│   ├── README.md           # Internal docs index
│   ├── getting_started.md  # Developer quick start
│   ├── advanced/           # Advanced implementation details
│   └── *.md               # Technical documentation
│
└── documentation/          # Public documentation (Docusaurus)
    ├── README.md          # Public docs index
    ├── sidebars.js        # Docusaurus navigation
    ├── getting-started/   # User guides
    ├── tutorials/         # Step-by-step tutorials
    └── api-reference/     # API documentation
```

## Content Guidelines

### `/docs` - Internal Developer Documentation

**Purpose**: Technical documentation for contributors and developers working on Hokusai itself

**Content includes**:
- Architecture decisions and design documents
- Implementation details
- Advanced configuration options
- Development environment setup
- Internal APIs and services
- Pipeline implementation details
- Testing strategies
- Debugging guides

**Audience**: 
- Hokusai contributors
- Developers extending the platform
- DevOps engineers deploying Hokusai

### `/documentation` - Public User Documentation

**Purpose**: User-facing documentation for docs.hokus.ai

**Content includes**:
- Getting started guides
- Installation instructions
- API reference
- Tutorials and examples
- Best practices
- Feature explanations
- Integration guides

**Audience**:
- Data scientists using Hokusai
- Developers integrating with Hokusai
- Third-party application developers

## Key Differences

| Aspect | `/docs` (Internal) | `/documentation` (Public) |
|--------|-------------------|-------------------------|
| Format | Standard Markdown | Docusaurus with frontmatter |
| Audience | Contributors | End users |
| Content | Implementation details | Usage guides |
| Deployment | GitHub only | docs.hokus.ai |
| Updates | With code changes | With releases |

## When to Update Which

### Update `/docs` when:
- Adding new architectural components
- Documenting implementation details
- Creating development guides
- Adding debugging information
- Documenting internal APIs

### Update `/documentation` when:
- Adding user-facing features
- Creating tutorials
- Updating API documentation
- Writing integration guides
- Improving getting started content

## Avoiding Duplication

To prevent content duplication:

1. **Installation instructions** → `/documentation` only
2. **API reference** → `/documentation` only
3. **Architecture details** → `/docs` only
4. **Development setup** → `/docs` only
5. **User tutorials** → `/documentation` only

## Cross-References

When appropriate, link between documentation sets:

- From `/docs`: "For user documentation, see docs.hokus.ai"
- From `/documentation`: "For implementation details, see internal developer docs"

## Future Improvements

1. Consider renaming directories for clarity:
   - `/docs` → `/docs-internal`
   - `/documentation` → `/docs-public`

2. Add CI checks to ensure:
   - No duplicate content
   - Consistent formatting
   - Valid cross-references

3. Create automated sync for shared content (e.g., version numbers)