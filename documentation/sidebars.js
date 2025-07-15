/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  // Main documentation sidebar
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quickstart',
        'authentication',
        'getting-started/configuration',
        'getting-started/first-model',
        'getting-started/mlflow-access',
      ],
    },
    {
      type: 'category',
      label: 'Core Features',
      items: [
        'core-features/model-registry',
        'core-features/deltaone-detection',
        'core-features/dspy-integration',
        'core-features/ab-testing',
        'core-features/metric-logging',
        'core-features/model-versioning',
      ],
    },
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/building-first-model',
        'tutorials/contributing-data',
        'tutorials/ab-testing',
        'tutorials/using-dspy',
        'tutorials/tracking-performance',
        'tutorials/claiming-rewards',
      ],
    },
    {
      type: 'category',
      label: 'Data Contribution',
      items: [
        'contributing/overview',
        'contributing/data-formats',
        'contributing/eth-wallet-setup',
        'contributing/submission-workflow',
        'contributing/huggingface-datasets',
        'contributing/data-quality',
        'contributing/licensing',
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      items: [
        'api-reference/index',
        'api-reference/authentication',
        'api-reference/models-api',
        'api-reference/contribution-api',
        'api-reference/performance-api',
        'api-reference/rewards-api',
        'api-reference/dspy-api',
        'api-reference/webhooks',
        'api-reference/error-codes',
        {
          type: 'category',
          label: 'SDKs',
          items: [
            'api-reference/sdks/python',
            'api-reference/sdks/javascript',
            'api-reference/sdks/go',
            'api-reference/sdks/java',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: [
        'guides/architecture',
        'guides/best-practices',
        'guides/security',
        'guides/performance-optimization',
        'guides/deployment',
        'guides/monitoring',
        'guides/troubleshooting',
        'guides/migration',
      ],
    },
    {
      type: 'category',
      label: 'Advanced Topics',
      items: [
        'advanced/custom-signatures',
        'advanced/teleprompt-finetuning',
        'advanced/zk-proofs',
        'advanced/on-chain-verification',
        'advanced/custom-metrics',
        'advanced/pipeline-orchestration',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/glossary',
        'reference/faq',
        'reference/changelog',
        'reference/roadmap',
        'reference/license',
      ],
    },
  ],

  // API-specific sidebar
  api: [
    'api-reference/index',
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'api-reference/authentication',
        'api-reference/quickstart',
        'api-reference/rate-limits',
      ],
    },
    {
      type: 'category',
      label: 'Endpoints',
      items: [
        'api-reference/models-api',
        'api-reference/contribution-api',
        'api-reference/performance-api',
        'api-reference/rewards-api',
        'api-reference/dspy-api',
      ],
    },
    {
      type: 'category',
      label: 'SDKs',
      items: [
        'api-reference/sdks/python',
        'api-reference/sdks/javascript',
        'api-reference/sdks/go',
        'api-reference/sdks/java',
      ],
    },
    {
      type: 'category',
      label: 'Advanced',
      items: [
        'api-reference/webhooks',
        'api-reference/batch-operations',
        'api-reference/async-requests',
        'api-reference/error-codes',
      ],
    },
  ],
};

module.exports = sidebars;