# Branch Protection Rules - CareBank

This document describes how to configure GitHub branch protection rules to enforce CI checks before merging pull requests.

## Overview

Both the backend and frontend repositories have CI workflows configured that must pass before a PR can be merged. This is enforced using GitHub's branch protection rules.

## Required GitHub Settings

### For carebank-backend Repository

1. Go to Repository Settings > Branches
2. Click "Add rule" for `main` branch
3. Configure the following settings:

**Required Checks:**
- Require branches to be up to date before merging: **unchecked** (let CI handle this)
- Require status checks to pass before merging: **checked**
  - Select required status checks:
    - `Backend Tests` (runs on Python 3.11)
    - `Backend Tests` (runs on Python 3.12)
    - `Type Check`
- Require conversation resolution before merging: **checked**
- Require code owner reviews: **checked**
- Required number of reviews before merging: **1**
- Include administrators: **unchecked** (admins can bypass)

4. Repeat for `develop` branch

### For carebank-frontend Repository

1. Go to Repository Settings > Branches
2. Click "Add rule" for `main` branch
3. Configure the following settings:

**Required Checks:**
- Require status checks to pass before merging: **checked**
  - Select required status checks:
    - `lint-and-build` (runs on Node 20)
    - `lint-and-build` (runs on Node 22)
- Require conversation resolution before merging: **checked**
- Require code owner reviews: **checked**
- Required number of reviews before merging: **1**
- Include administrators: **unchecked**

4. Repeat for `develop` branch

## How It Works

### Backend CI (test.yml)
- Runs on pull requests to `main` and `develop` branches
- Tests run on Python 3.11 and 3.12
- Includes:
  - PostgreSQL and Redis services for integration tests
  - Unit tests with pytest
  - Code linting with ruff
  - Coverage reporting

### Frontend CI (ci.yml)
- Runs on pull requests to `main` and `develop` branches
- Runs on Node 20 and 22
- Includes:
  - ESLint for code quality
  - TypeScript type checking
  - Production build verification

## Verification

To verify the rules are working:

1. Create a test PR that intentionally breaks a test
2. The PR should show failing checks
3. The "Merge pull request" button should be disabled
4. Only after all checks pass can the PR be merged

## Quick Reference

| Repository | Branch | Required Checks |
|------------|--------|-----------------|
| carebank-backend | main, develop | Backend Tests (3.11), Backend Tests (3.12), Type Check |
| carebank-frontend | main, develop | lint-and-build (Node 20), lint-and-build (Node 22) |
