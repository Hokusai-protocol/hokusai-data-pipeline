# Documentation Consolidation Plan

## Current State

We have two separate documentation directories that serve different purposes but contain overlapping content:

### 1. `/docs` Directory (Internal/Developer Documentation)
- **Purpose**: Internal developer documentation, technical guides
- **Format**: Standard Markdown
- **Audience**: Contributors, developers working on the codebase
- **Content**: Technical details, advanced topics, internal APIs

### 2. `/documentation` Directory (Public Documentation)
- **Purpose**: Public-facing documentation for docs.hokus.ai
- **Format**: Docusaurus-compatible with frontmatter
- **Audience**: End users, external developers using Hokusai
- **Content**: Getting started guides, tutorials, API reference

## Issues with Current Structure

1. **Confusion**: Two directories with similar names and overlapping content
2. **Duplication**: Some content exists in both places (e.g., getting started guides)
3. **Maintenance**: Updates need to be made in multiple places
4. **Discoverability**: Not clear which documentation to use when

## Recommended Solution

### Option 1: Rename and Clarify (Recommended)

Rename directories to make their purpose clear:

```
hokusai-data-pipeline/
├── docs-internal/          # Internal developer documentation
│   ├── README.md          # "Internal Developer Documentation"
│   ├── architecture/
│   ├── contributing/
│   └── advanced/
│
└── docs-public/           # Public documentation (Docusaurus)
    ├── README.md          # "Public Documentation for docs.hokus.ai"
    ├── sidebars.js
    ├── getting-started/
    ├── tutorials/
    └── api-reference/
```

### Option 2: Single Source of Truth

Merge everything into one directory with clear subdirectories:

```
hokusai-data-pipeline/
└── docs/
    ├── README.md          # Explains the structure
    ├── internal/          # Developer documentation
    │   ├── architecture/
    │   └── contributing/
    │
    └── public/            # Docusaurus site
        ├── sidebars.js
        ├── getting-started/
        └── api-reference/
```

### Option 3: Keep Public Docs External

Move Docusaurus documentation to a separate repository:

```
hokusai-data-pipeline/
└── docs/                  # All internal documentation

hokusai-docs/             # Separate repo
└── docusaurus/           # Public documentation site
```

## Migration Steps for Option 1 (Recommended)

1. **Rename directories**:
   ```bash
   mv docs docs-internal
   mv documentation docs-public
   ```

2. **Update READMEs** to clearly explain each directory's purpose

3. **Remove duplicated content** between directories

4. **Update references** in code and other documentation

5. **Create clear guidelines** for what goes where

## Content Allocation Guidelines

### Internal Documentation (`docs-internal/`)
- Architecture decisions
- Development setup
- Contributing guidelines
- Internal APIs
- Advanced implementation details
- Debugging guides

### Public Documentation (`docs-public/`)
- Getting started guides
- API reference
- Tutorials
- Examples
- Installation instructions
- User-facing features

## Benefits of Consolidation

1. **Clear Purpose**: No confusion about which docs to use
2. **Better Maintenance**: Clear ownership of content
3. **Improved Navigation**: Users know where to find information
4. **Easier Updates**: Single location for each piece of content

## Next Steps

1. Choose consolidation approach
2. Create migration scripts
3. Update all references
4. Add CI checks to maintain structure
5. Document the new structure clearly