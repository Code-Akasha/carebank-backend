# CareBank Azure Deployment - Complete Setup

## ✅ Current Status

### Backend & Database
- **Backend**: Running on Azure Container Apps
- **Database**: Azure Database for PostgreSQL Flexible Server
- **Status**: ✅ Auth endpoints working (201 Created)
- **Admin Account**: admin@carebank.demo / AdminCare2026! (role: admin)

### Proxy Service
- **agentic-bank**: Running on Azure Container Apps
- **Status**: ✅ Running

### Frontend
- **Dev Server**: http://localhost:5173
- **Ready to test**: ✅

### LLM Integration
- **Ollama**: Can be run locally on port 11434
- **Tunnel**: Need to create ngrok tunnel
- **Configuration**: Via admin UI endpoints

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Azure Container Apps                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │   backend    │  │ agentic-bank│  │   redis      │   │
│  │ (FastAPI)    │  │   (proxy)   │  │              │   │
│  └──────┬───────┘  └─────────────┘  └──────────────┘   │
│         │                                                │
└─────────┼────────────────────────────────────────────────┘
          │
          ↓
   ┌─────────────────────────┐
   │ Azure Database for      │
   │ PostgreSQL              │
   │ carebank-db.postgres... │
   └─────────────────────────┘
```

---

## Admin Credentials

**Email**: admin@carebank.demo
**Password**: AdminCare2026!
**Role**: admin

**Demo Users** (created via registration):
- rajesh@demo.com / Demo@2026!
- priya@demo.com / Demo@2026!
- amit@demo.com / Demo@2026!

---

## Setup Steps

### 1. Frontend Login (Local)

```bash
cd /home/jefino9488/WebstormProjects/carebank-frontend
VITE_API_BASE_URL=https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io \
npm run dev
```

Then navigate to: http://localhost:5173
- Login with: admin@carebank.demo / AdminCare2026!

### 2. Start Ollama (Local - Optional)

```bash
# Install ollama from https://ollama.ai
# Then pull a model and run
ollama pull qwen:7b
ollama serve  # Runs on localhost:11434
```

### 3. Create ngrok Tunnel to Ollama

```bash
# In new terminal
ngrok http 11434

# Copy the URL shown (e.g., https://abc123.ngrok.io)
# This is your OLLAMA_TUNNEL_URL
```

### 4. Configure LLM via Admin API

Get admin token:
```bash
ADMIN_TOKEN=$(curl -s -X POST \
  "https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@carebank.demo","password":"AdminCare2026!"}' \
  | jq -r '.access_token')
```

Configure LLM tunnel (replace TUNNEL_URL with ngrok URL):
```bash
curl -X PUT \
  "https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io/api/admin/llm/tunnel/production" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tunnel_url": "https://your-ngrok-url.ngrok.io",
    "ollama_model_default": "qwen:7b",
    "request_timeout_sec": 30
  }'
```

Test Ollama connection:
```bash
curl -X POST \
  "https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io/api/admin/llm/tunnel/production/test" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 5. Test Payment Flow

Via frontend UI:
1. Login as demo user (rajesh@demo.com / Demo@2026!)
2. Navigate to Payments section
3. Initiate payment flow
4. Backend calls agentic-bank proxy for account operations

---

## API Endpoints (Admin)

All endpoints require admin JWT token in `Authorization: Bearer <token>` header.

**GET** `/api/admin/llm/prompts`
- List all active LLM prompts for agents

**GET** `/api/admin/llm/tunnel/{environment}`
- Get tunnel configuration for environment (production/dev)

**PUT** `/api/admin/llm/tunnel/{environment}`
- Update tunnel URL and settings
- Payload: `{tunnel_url, tunnel_auth_token, ollama_model_default, request_timeout_sec}`

**POST** `/api/admin/llm/tunnel/{environment}/test`
- Test connectivity to configured Ollama

**GET** `/api/admin/llm/models`
- List available models from Ollama

**PUT** `/api/admin/llm/prompts/{agent_name}/publish`
- Publish new prompt version for agent

---

## Testing Checklist

- [ ] Frontend loads at http://localhost:5173
- [ ] Admin login works
- [ ] Can access admin LLM configuration page
- [ ] Demo users created successfully
- [ ] Payment endpoints accessible
- [ ] Ollama tunnel configured
- [ ] Proxy integration works
- [ ] End-to-end payment flow completes

---

## Troubleshooting

### Backend 500 Error on Auth
**Check**: Azure Database connection
```bash
az containerapp logs show --name backend --resource-group carebank-rg --tail 50
```

### Ollama Not Responding
**Check**: Ollama running on localhost:11434
```bash
curl http://localhost:11434/api/tags
```

### Ngrok Tunnel Not Working
**Check**: ngrok process running and tunnel active
```bash
ps aux | grep ngrok
curl http://localhost:4040/api/tunnels  # ngrok UI API
```

---

## URLs & Credentials

**Backend**: https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io
**Frontend**: http://localhost:5173 (development)
**Swagger**: https://backend.politefield-3469f7f1.centralindia.azurecontainerapps.io/docs

**Proxy**: agentic-bank.internal.politefield-3469f7f1.centralindia.azurecontainerapps.io
**Database**: carebank-db.postgres.database.azure.com:5432

---

## Next Steps

1. Test frontend login flow
2. Create demo user accounts
3. Set up Ollama tunnel
4. Configure LLM in admin UI
5. Test payment flow end-to-end
6. Monitor logs for any issues
