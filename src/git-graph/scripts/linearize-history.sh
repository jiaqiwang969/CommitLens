#!/bin/bash

# Create a new branch for linear history
git checkout -b linear-main

# Get all commits in topological order, excluding merges
commits=$(git rev-list --no-merges --reverse HEAD)

# Create a new orphan branch
git checkout --orphan temp-linear

# Remove all files
git rm -rf . 2>/dev/null || true

# Cherry-pick each commit
first=true
for commit in $commits; do
    echo "Processing commit: $commit"

    if [ "$first" = true ]; then
        # For the first commit, we need to handle it differently
        git checkout $commit -- .
        git add -A
        git commit -C $commit --allow-empty
        first=false
    else
        # Cherry-pick subsequent commits
        git cherry-pick $commit || {
            # If cherry-pick fails, try to continue
            git add -A
            git cherry-pick --continue || true
        }
    fi
done

echo "Linear history created on branch temp-linear"
echo "To verify: git log --oneline --graph"