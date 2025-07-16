# Workflow Prompt Improvements to Avoid Merge Conflicts

## Problem
The current workflow creates `prd.md` and `tasks.md` files in the root directory for each feature, causing merge conflicts when multiple features are developed in parallel.

## Suggested Improvements

### Option 1: Use Feature-Specific File Names
Instead of using generic `prd.md` and `tasks.md`, use feature-specific names:

```bash
# Step 3: Generate PRD
- Save the AI-generated PRD to `docs/prd/<feature-name>-prd.md`

# Step 4: Generate Tasks  
- Save these to `docs/tasks/<feature-name>-tasks.md`
```

### Option 2: Use a Single Directory per Feature
Create a feature directory to contain all related documents:

```bash
# After creating the branch
mkdir -p features/<feature-name>

# Step 3: Generate PRD
- Save the AI-generated PRD to `features/<feature-name>/prd.md`

# Step 4: Generate Tasks
- Save these to `features/<feature-name>/tasks.md`
```

### Option 3: Append to Existing Files with Sections
Instead of overwriting, append to existing files with clear section markers:

```markdown
# In prd.md
## [Feature: Fix MLflow Authentication] - 2025-07-16
...content...

## [Feature: Another Feature] - 2025-07-15
...content...
```

### Option 4: Use Git Worktrees (Advanced)
For complex projects, use git worktrees to isolate feature development:

```bash
# Create a worktree for the feature
git worktree add -b feature/<name> ../hokusai-<feature-name> origin/main
cd ../hokusai-<feature-name>
# Now prd.md and tasks.md won't conflict with other branches
```

## Recommended Solution

I recommend **Option 2** (Feature Directory) because it:
- Keeps all feature-related documents together
- Avoids conflicts between parallel features
- Makes it easy to review what was done for each feature
- Can be easily cleaned up after feature completion

## Updated Workflow Steps

Replace current Step 3 and 4 with:

```markdown
### Step 2.5: Create Feature Directory
- Create a directory for this feature:
  ```bash
  mkdir -p features/<sanitized-title>
  ```

### Step 3: Generate PRD
- Use the prompt in `prd-prompt-template.md`
- Replace `{{PROJECT_SUMMARY}}` with the selected Linear task's title + description
- Save the AI-generated PRD to `features/<sanitized-title>/prd.md`

### Step 4: Generate Tasks
- Use the prompt in `tasks-prompt-template.md` to convert the PRD into tasks
- Save these to `features/<sanitized-title>/tasks.md`
```

## Alternative: Use TODO.md
Another approach is to use a single `TODO.md` file that tracks all active tasks across features:

```markdown
# TODO.md

## Active Features

### Fix MLflow Authentication
- Branch: feature/fix-mlflow-authentication-error
- Linear: https://linear.app/...
- [ ] Add authentication support
- [ ] Update documentation
- [x] Write tests

### Another Feature
- Branch: feature/another-feature
- Linear: https://linear.app/...
- [ ] Task 1
- [ ] Task 2
```

This avoids conflicts while maintaining visibility of all work in progress.