/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.
 */

module.exports = {
  docs: [
    {
      type: 'category',
      label: 'Overview',
      collapsed: false,
      items: [
        'overview/introduction',
        'overview/architecture',
      ],
    },
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/first-contribution',
        'getting-started/configuration',
      ],
    },
    {
      type: 'category',
      label: 'ML Platform',
      items: [
        'ml-platform/overview',
        'ml-platform/core-concepts',
        'ml-platform/api-reference',
        'ml-platform/examples',
      ],
    },
    {
      type: 'category',
      label: 'Data Pipeline',
      items: [
        'data-pipeline/architecture',
        'data-pipeline/configuration',
        'data-pipeline/data-formats',
        'data-pipeline/attestation',
      ],
    },
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/basic-workflow',
        'tutorials/huggingface-integration',
        'tutorials/multi-contributor',
        'tutorials/ab-testing',
        'tutorials/production-deployment',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guide',
      items: [
        'developer-guide/api-reference',
        'developer-guide/troubleshooting',
        'developer-guide/best-practices',
        'developer-guide/security',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/cli-commands',
        'reference/environment-vars',
        'reference/output-schemas',
        'reference/glossary',
      ],
    },
    {
      type: 'category',
      label: 'Archive',
      collapsed: true,
      items: [
        'architecture/overview',
        'data-contribution/overview',
        'operations/deployment',
        'troubleshooting/common-issues',
      ],
    },
  ],
};