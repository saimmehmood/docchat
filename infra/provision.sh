#!/usr/bin/env bash
# Provisions everything DocChat needs in Azure:
#   - Azure AI Foundry (AI Services) resource with a chat and an embedding deployment
#   - Azure AI Search on the free tier (the index itself is created by the app on startup)
#   - Azure Container Registry + Linux App Service to run the container
# and, if the GitHub CLI is logged in, stores the deployment secrets on the repo.
#
# Usage: az login && ./infra/provision.sh
# Override any of the variables below via environment, e.g. LOCATION=swedencentral ./infra/provision.sh
set -euo pipefail

PREFIX="${PREFIX:-docchat$RANDOM}"
LOCATION="${LOCATION:-eastus2}"
RG="${RG:-rg-docchat}"
AI_NAME="${AI_NAME:-${PREFIX}-ai}"
SEARCH_NAME="${SEARCH_NAME:-${PREFIX}-search}"
ACR_NAME="${ACR_NAME:-${PREFIX//-/}acr}"
PLAN_NAME="${PLAN_NAME:-${PREFIX}-plan}"
APP_NAME="${APP_NAME:-${PREFIX}-app}"
GITHUB_REPO="${GITHUB_REPO:-saimmehmood/docchat}"

CHAT_MODEL="${CHAT_MODEL:-gpt-4.1-mini}"
CHAT_MODEL_VERSION="${CHAT_MODEL_VERSION:-2025-04-14}"
EMBED_MODEL="${EMBED_MODEL:-text-embedding-3-small}"
EMBED_MODEL_VERSION="${EMBED_MODEL_VERSION:-1}"

echo "==> Resource group $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Azure AI Foundry resource $AI_NAME"
az cognitiveservices account create -g "$RG" -n "$AI_NAME" -l "$LOCATION" \
  --kind AIServices --sku S0 --custom-domain "$AI_NAME" --yes -o none

echo "==> Deploying $CHAT_MODEL"
az cognitiveservices account deployment create -g "$RG" -n "$AI_NAME" \
  --deployment-name "$CHAT_MODEL" --model-format OpenAI \
  --model-name "$CHAT_MODEL" --model-version "$CHAT_MODEL_VERSION" \
  --sku-name GlobalStandard --sku-capacity 50 -o none

echo "==> Deploying $EMBED_MODEL"
az cognitiveservices account deployment create -g "$RG" -n "$AI_NAME" \
  --deployment-name "$EMBED_MODEL" --model-format OpenAI \
  --model-name "$EMBED_MODEL" --model-version "$EMBED_MODEL_VERSION" \
  --sku-name Standard --sku-capacity 50 -o none

AI_ENDPOINT="https://${AI_NAME}.openai.azure.com/"
AI_KEY=$(az cognitiveservices account keys list -g "$RG" -n "$AI_NAME" --query key1 -o tsv)

echo "==> Azure AI Search (free tier) $SEARCH_NAME"
az search service create -g "$RG" -n "$SEARCH_NAME" -l "$LOCATION" --sku free -o none
SEARCH_ENDPOINT="https://${SEARCH_NAME}.search.windows.net"
SEARCH_KEY=$(az search admin-key show -g "$RG" --service-name "$SEARCH_NAME" --query primaryKey -o tsv)

echo "==> Container registry $ACR_NAME"
az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled true -o none
ACR_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

echo "==> App Service $APP_NAME"
az appservice plan create -g "$RG" -n "$PLAN_NAME" -l "$LOCATION" --is-linux --sku B1 -o none
# Start from a placeholder image; the GitHub workflow pushes and deploys the real one.
az webapp create -g "$RG" -p "$PLAN_NAME" -n "$APP_NAME" \
  --container-image-name mcr.microsoft.com/appsvc/staticsite:latest -o none
az webapp config container set -g "$RG" -n "$APP_NAME" \
  --container-registry-url "https://$ACR_SERVER" \
  --container-registry-user "$ACR_USER" \
  --container-registry-password "$ACR_PASS" -o none
az webapp config appsettings set -g "$RG" -n "$APP_NAME" -o none --settings \
  WEBSITES_PORT=8000 \
  AZURE_OPENAI_ENDPOINT="$AI_ENDPOINT" \
  AZURE_OPENAI_API_KEY="$AI_KEY" \
  AZURE_OPENAI_CHAT_DEPLOYMENT="$CHAT_MODEL" \
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT="$EMBED_MODEL" \
  AZURE_SEARCH_ENDPOINT="$SEARCH_ENDPOINT" \
  AZURE_SEARCH_API_KEY="$SEARCH_KEY"

# Publish-profile deploys need basic auth on the SCM site (off by default on new apps).
az resource update -g "$RG" --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies \
  --parent "sites/$APP_NAME" -n scm --set properties.allow=true -o none
PUBLISH_PROFILE=$(az webapp deployment list-publishing-profiles -g "$RG" -n "$APP_NAME" --xml)

# Local .env for running the API on your machine.
cat > "$(dirname "$0")/../backend/.env" <<EOF
AZURE_OPENAI_ENDPOINT=$AI_ENDPOINT
AZURE_OPENAI_API_KEY=$AI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=$CHAT_MODEL
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$EMBED_MODEL
AZURE_SEARCH_ENDPOINT=$SEARCH_ENDPOINT
AZURE_SEARCH_API_KEY=$SEARCH_KEY
EOF
echo "==> Wrote backend/.env"

if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  echo "==> Setting GitHub Actions secrets on $GITHUB_REPO"
  gh secret set AZURE_WEBAPP_NAME -R "$GITHUB_REPO" -b "$APP_NAME"
  gh secret set AZURE_WEBAPP_PUBLISH_PROFILE -R "$GITHUB_REPO" -b "$PUBLISH_PROFILE"
  gh secret set ACR_LOGIN_SERVER -R "$GITHUB_REPO" -b "$ACR_SERVER"
  gh secret set ACR_USERNAME -R "$GITHUB_REPO" -b "$ACR_USER"
  gh secret set ACR_PASSWORD -R "$GITHUB_REPO" -b "$ACR_PASS"
else
  echo "!! gh CLI not logged in. Set these repo secrets manually:"
  echo "   AZURE_WEBAPP_NAME=$APP_NAME  ACR_LOGIN_SERVER=$ACR_SERVER  ACR_USERNAME=$ACR_USER"
  echo "   ACR_PASSWORD and AZURE_WEBAPP_PUBLISH_PROFILE (az webapp deployment list-publishing-profiles --xml)"
fi

echo
echo "Done. App URL: https://${APP_NAME}.azurewebsites.net"
echo "Push to main (or re-run the workflow) to build and deploy."
