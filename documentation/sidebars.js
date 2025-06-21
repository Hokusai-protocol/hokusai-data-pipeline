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
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/configuration',
      ],
    },
    {
      type: 'category',
      label: 'Architecture',
      items: [
        'architecture/overview',
        'architecture/components',
        'architecture/data-flow',
        'architecture/security',
      ],
    },
    {
      type: 'category',
      label: 'Data Contribution',
      items: [
        'data-contribution/overview',
        'data-contribution/data-formats',
        'data-contribution/validation-rules',
        'data-contribution/eth-wallet-setup',
        'data-contribution/submission-process',
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      items: [
        'api-reference/index',
        'api-reference/pipeline',
        'api-reference/data-integration',
        'api-reference/model-training',
        'api-reference/evaluation',
        'api-reference/output-generation',
      ],
    },
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/dry-run-mode',
        'tutorials/contributing-data',
        'tutorials/huggingface-integration',
        'tutorials/attestation-proofs',
      ],
    },
    {
      type: 'category',
      label: 'Operations',
      items: [
        'operations/deployment',
        'operations/monitoring',
        'operations/performance-tuning',
        'operations/security-best-practices',
      ],
    },
    {
      type: 'category',
      label: 'Troubleshooting',
      items: [
        'troubleshooting/common-issues',
        'troubleshooting/error-messages',
        'troubleshooting/debugging',
        'troubleshooting/faq',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guide',
      items: [
        'developer-guide/contributing',
        'developer-guide/code-style',
        'developer-guide/testing',
        'developer-guide/extensions',
      ],
    },
  ],
};