#!/bin/bash

echo "🚀 Syncing .env with GitHub Action Secrets..."

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null
then
    echo "❌ GitHub CLI (gh) could not be found."
    echo "Please install it by running: brew install gh"
    exit
fi

# Ensure user is logged in
echo "Checking GitHub authentication..."
if ! gh auth status &> /dev/null
then
    echo "You need to log in to GitHub first. Running 'gh auth login'..."
    gh auth login
fi

# Set the secrets
echo "Uploading 170+ environment variables from .env to GitHub..."
gh secret set -f .env

echo "✅ Success! All variables are now in GitHub Repository Secrets."
