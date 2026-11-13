---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
background: false
allowed-tools: Bash(gh *)
paths: "src/**/*.ts"
---

## Pull request context

- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`

## Your task

Summarize this pull request. Report the intent, the risk, and the files that
carry the change.
