#!/bin/bash
# ============================================================================
# Deploy bcomm-whatsapp-bridge on Coolify
# ============================================================================
# Usage:
#   COOLIFY_TOKEN=<your-token> ./deploy-coolify.sh
#
# Prerequisites:
#   1. DNS record: wa-bot.agent-bcomm.space → agent-bcomm.space IP
#   2. Coolify API token (generate in Coolify → Settings → API Tokens)
#   3. GitHub repo accessible: https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge
# ============================================================================

set -euo pipefail

COOLIFY_URL="${COOLIFY_URL:-https://coolify.agent-bcomm.space}"
COOLIFY_TOKEN="${COOLIFY_TOKEN:?Set COOLIFY_TOKEN env var}"
GITHUB_REPO="LeonardoBittencourt97/bcomm-whatsapp-bridge"
GITHUB_BRANCH="main"
DOMAIN="wa-bot.agent-bcomm.space"
APP_NAME="bcomm-whatsapp-bridge"

echo "🔧 Deploying $APP_NAME to Coolify..."
echo "   Coolify: $COOLIFY_URL"
echo "   Domain:  $DOMAIN"
echo "   Repo:    $GITHUB_REPO"
echo ""

# ── 1. Get or create team ──────────────────────────────────────────
echo "📋 Step 1: Getting team info..."
TEAMS=$(curl -s -X GET "$COOLIFY_URL/api/v1/teams" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json")
TEAM_ID=$(echo "$TEAMS" | python3 -c "import sys,json; teams=json.load(sys.stdin); print(teams[0]['uuid'] if teams else '')" 2>/dev/null)

if [ -z "$TEAM_ID" ]; then
  echo "❌ Could not find team. Check your COOLIFY_TOKEN."
  exit 1
fi
echo "   Team ID: $TEAM_ID"

# ── 2. Get or create project ───────────────────────────────────────
echo ""
echo "📁 Step 2: Getting/creating project..."
PROJECTS=$(curl -s -X GET "$COOLIFY_URL/api/v1/projects" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json")
PROJECT_ID=$(echo "$PROJECTS" | python3 -c "
import sys, json
projects = json.load(sys.stdin)
for p in projects:
    if p.get('name','').lower() == 'bcomm':
        print(p['uuid'])
        break
" 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
  echo "   Creating 'bcomm' project..."
  PROJECT_RESP=$(curl -s -X POST "$COOLIFY_URL/api/v1/projects" \
    -H "Authorization: Bearer $COOLIFY_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "bcomm",
      "description": "BCOMM communication platform services"
    }')
  PROJECT_ID=$(echo "$PROJECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('uuid',''))" 2>/dev/null)
  echo "   Created project: $PROJECT_ID"
else
  echo "   Found existing project: $PROJECT_ID"
fi

# ── 3. Create application ──────────────────────────────────────────
echo ""
echo "🚀 Step 3: Creating application..."
APP_RESP=$(curl -s -X POST "$COOLIFY_URL/api/v1/applications" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"project_uuid\": \"$PROJECT_ID\",
    \"type\": \"compose\",
    \"name\": \"$APP_NAME\",
    \"git_repository\": \"https://github.com/$GITHUB_REPO\",
    \"git_branch\": \"$GITHUB_BRANCH\",
    \"destination\": \"\"
  }")
APP_UUID=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('uuid',''))" 2>/dev/null)

if [ -z "$APP_UUID" ]; then
  echo "❌ Failed to create application."
  echo "   Response: $APP_RESP"
  echo ""
  echo "   Falling back to manual instructions..."
  echo "   → Go to $COOLIFY_URL"
  echo "   → New Application → Docker Compose"
  echo "   → Git Repository: https://github.com/$GITHUB_REPO"
  echo "   → Branch: $GITHUB_BRANCH"
  exit 1
fi
echo "   App UUID: $APP_UUID"

# ── 4. Configure environment variables ─────────────────────────────
echo ""
echo "🔐 Step 4: Setting environment variables..."

ENV_VARS='{
  "EVOLUTION_API_URL": "https://evolution-api.agent-bcomm.space",
  "EVOLUTION_API_KEY": "1F0C0840D74A-4EFF-B413-AF2DE616B30E",
  "EVOLUTION_INSTANCE": "BCOMM",
  "HERMES_PROFILE": "bcomm-atendente",
  "OPENCODE_API_KEY": "",
  "OPENCODE_API_URL": "https://opencode.ai/zen/go/v1",
  "OPENCODE_MODEL": "mimo-v2.5",
  "PORT": "8000",
  "DEBUG": "false",
  "LOG_LEVEL": "INFO",
  "RATE_LIMIT_PER_MINUTE": "20"
}'

ENV_RESP=$(curl -s -X POST "$COOLIFY_URL/api/v1/applications/$APP_UUID/envs" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"envs\": $ENV_VARS}")
echo "   Env vars set: $(echo "$ENV_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if 'uuid' in d else d)" 2>/dev/null)"

# ── 5. Configure domain ────────────────────────────────────────────
echo ""
echo "🌐 Step 5: Configuring domain..."
DOMAIN_RESP=$(curl -s -X POST "$COOLIFY_URL/api/v1/applications/$APP_UUID/destination" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"fqdn\": \"https://$DOMAIN\",
    \"ports\": [{\"host\": \"8000\", \"container\": \"8000\"}],
    \"name\": \"$APP_NAME\"
  }")
echo "   Domain config: $(echo "$DOMAIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if 'uuid' in d else d)" 2>/dev/null)"

# ── 6. Start deployment ────────────────────────────────────────────
echo ""
echo "🚀 Step 6: Starting deployment..."
DEPLOY_RESP=$(curl -s -X POST "$COOLIFY_URL/api/v1/applications/$APP_UUID/deploy" \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -H "Content-Type: application/json")
echo "   Deploy response: $(echo "$DEPLOY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message', d))" 2>/dev/null)"

echo ""
echo "✅ Deployment initiated!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🌐 URL: https://$DOMAIN"
echo "  📊 Coolify: $COOLIFY_URL/applications/$APP_UUID"
echo "  📁 Project: $PROJECT_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏳ Wait 2-3 minutes for build + SSL certificate provisioning."
echo "   Check logs: $COOLIFY_URL/applications/$APP_UUID/logs"
