# Phase 5: Chat Integration - Quick Start Guide

**Objective**: Wire PaymentAgent and RecurringPaymentAgent into existing chat infrastructure  
**Time Estimate**: 4-6 hours  
**Effort**: Medium  

---

## Understanding Current State

### What Exists Already (We Built)
- ✅ `PaymentAgent` in `app/agents/payment_agent.py` - handles one-time payment conversations
- ✅ `RecurringPaymentAgent` in `app/agents/recurring_payment_agent.py` - handles recurring setup
- ✅ `PaymentContext` model - preserves state between messages
- ✅ `RecurringSetupContext` model - preserves state between messages
- ✅ Full error handling and validation in both agents

### What's Missing (To Be Built)
- ⏳ `/api/chat/payments/execute` endpoint - wires into PaymentAgent
- ⏳ `/api/chat/payments/recurring` endpoint - wires into RecurringPaymentAgent
- ⏳ Context persistence (in-memory cache or Redis)
- ⏳ Frontend components to call these endpoints

---

## Architecture for Chat Integration

```
┌─────────────────────┐
│   React Frontend    │
└──────────┬──────────┘
           │ POST /api/chat/payments/execute
           │ {message, context}
           ▼
┌─────────────────────────────────────┐
│   Chat Route Handler                 │
│   (app/routes/chat_payments.py)     │
└────────────┬────────────────────────┘
             │ Extract: user_id (JWT), message, context
             ▼
┌─────────────────────────────────────┐
│   Agent Dispatcher                   │
│   (determines which agent)           │
└────────────┬────────────────────────┘
             │
    ┌─────────┴──────────┐
    │                    │
    ▼                    ▼
┌──────────────┐  ┌──────────────────┐
│Payment Agent │  │RecurringAgent    │
└──────┬───────┘  └────────┬─────────┘
       │                   │
       └─────────┬─────────┘
                 │ Returns AgentResponse
                 ▼
┌─────────────────────────────────────┐
│   Response Formatter                 │
│   (JSON response to client)          │
└─────────────────────────────────────┘
```

---

## Step 1: Create Chat Routes File

**File**: `app/routes/chat_payments.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthenticationCredentials
from typing import Optional
from pydantic import BaseModel

from app.agents.payment_agent import PaymentAgent, PaymentContext
from app.agents.recurring_payment_agent import RecurringPaymentAgent, RecurringSetupContext
from app.core.config import settings
from app.core.security import get_current_user_id

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Request/Response models
class ChatPaymentRequest(BaseModel):
    message: str
    context: Optional[PaymentContext] = None

class ChatRecurringRequest(BaseModel):
    message: str
    context: Optional[RecurringSetupContext] = None

class ChatResponse(BaseModel):
    message: str
    context: dict  # Updated context
    options: list
    error: Optional[str] = None

# Initialize agents
payment_agent = PaymentAgent()
recurring_agent = RecurringPaymentAgent()

@router.post("/payments/execute")
async def chat_payment(request: ChatPaymentRequest, user_id: str = Depends(get_current_user_id)) -> ChatResponse:
    """One-time payment via conversation"""
    try:
        # Initialize context if not provided
        context = request.context or PaymentContext(user_id=user_id)
        
        # Process message through agent
        response = payment_agent.process_message(user_id, request.message, context)
        
        return ChatResponse(
            message=response.message,
            context=response.context.model_dump(),
            options=response.options
        )
    except Exception as e:
        return ChatResponse(
            message="An error occurred. Please try again.",
            context={},
            options=[],
            error=str(e)
        )

@router.post("/payments/recurring")
async def chat_recurring(request: ChatRecurringRequest, user_id: str = Depends(get_current_user_id)) -> ChatResponse:
    """Recurring payment setup via conversation"""
    try:
        # Initialize context if not provided
        context = request.context or RecurringSetupContext(user_id=user_id)
        
        # Process message through agent
        response = recurring_agent.process_message(user_id, request.message, context)
        
        return ChatResponse(
            message=response.message,
            context=response.context.model_dump(),
            options=response.options
        )
    except Exception as e:
        return ChatResponse(
            message="An error occurred. Please try again.",
            context={},
            options=[],
            error=str(e)
        )
```

---

## Step 2: Register New Routes in app.main

**File**: `app/main.py`

Add to the create_app() function or app initialization:

```python
# In create_app() or app initialization section
from app.routes import chat_payments

# Add this line with other router includes:
app.include_router(chat_payments.router)
```

---

## Step 3: Test the Endpoints

### Test One-Time Payment Flow

**First request** (start conversation):
```bash
curl -X POST http://localhost:8000/api/chat/payments/execute \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to pay someone"}'

# Expected response:
{
  "message": "Great! Who would you like to pay? Here are your saved beneficiaries:\n1. Mom - 1000000001\n2. Rent Admin - 1000000002\n\nOr type the name of a new beneficiary.",
  "context": {
    "user_id": "user123",
    "state": "SELECTING_BENEFICIARY",
    "beneficiary_id": null,
    ...
  },
  "options": ["Mom", "Rent Admin", "New contact"]
}
```

**Second request** (select beneficiary):
```bash
curl -X POST http://localhost:8000/api/chat/payments/execute \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Mom",
    "context": {
      "user_id": "user123",
      "state": "SELECTING_BENEFICIARY",
      ...previous context...
    }
  }'

# Expected response:
{
  "message": "Mom is verified ✓\n\nHow much would you like to pay?",
  "context": {
    "state": "ENTERING_AMOUNT",
    "beneficiary_id": 1,
    ...
  },
  "options": ["500", "1000", "5000", "Custom amount"]
}
```

---

## Step 4: Test Recurring Payment Flow

**Similar to above but**:
- Endpoint: `/api/chat/payments/recurring`
- State: `state: "SELECTING_FREQUENCY"`
- Options: Daily, Weekly, Monthly, Quarterly
- Extra steps: Day/date selection, approval question

---

## Step 5: Frontend Integration

### React Hook for Payment Chat

```typescript
// src/hooks/usePaymentChat.ts
import { useState } from 'react';

export const usePaymentChat = () => {
  const [messages, setMessages] = useState([]);
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (endpoint: '/execute' | '/recurring', message: string) => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/chat/payments/${endpoint}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, context })
        }
      );
      
      const data = await response.json();
      setContext(data.context);
      setMessages([...messages, 
        { role: 'user', message },
        { role: 'assistant', message: data.message, options: data.options }
      ]);
      
      return data;
    } finally {
      setLoading(false);
    }
  };

  return { messages, sendMessage, loading };
};
```

### React Component

```typescript
// src/components/PaymentChat.tsx
import { usePaymentChat } from '../hooks/usePaymentChat';

export const PaymentChat = () => {
  const { messages, sendMessage, loading } = usePaymentChat();
  const [input, setInput] = useState('');

  const handleSend = () => {
    sendMessage('execute', input);
    setInput('');
  };

  return (
    <div className="payment-chat">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.message}
          </div>
        ))}
      </div>
      <input 
        value={input} 
        onChange={(e) => setInput(e.target.value)}
        placeholder="Type your message..."
      />
      <button onClick={handleSend} disabled={loading}>Send</button>
    </div>
  );
};
```

---

## Checklist for Phase 5

- [ ] Create `app/routes/chat_payments.py` with both endpoints
- [ ] Register routes in `app/main.py`
- [ ] Test `/api/chat/payments/execute` endpoint manually with curl
- [ ] Test `/api/chat/payments/recurring` endpoint manually with curl
- [ ] Verify state machine transitions work correctly
- [ ] Verify context is preserved between requests
- [ ] Create React component for payment chat UI
- [ ] Wire component into Chat page
- [ ] Test end-to-end: Message → Backend → Agent → Response
- [ ] Test error scenarios (invalid amount, no beneficiaries, etc.)
- [ ] Add logging to endpoint handlers
- [ ] Write integration tests for both endpoints

---

## Common Issues & Solutions

### Issue: "Context is None on second request"
**Solution**: Client must send the updated context back in each request

### Issue: "Agent not finding beneficiaries"
**Solution**: Verify JWT token contains correct user_id, check DB has beneficiaries for that user

### Issue: "Payment executes automatically but shouldn't"
**Solution**: Check `requires_mpin` flag, verify MPIN validation is working

### Issue: "Recurring setup doesn't persist to DB"
**Solution**: Verify `create_recurring_payment_rule()` is being called, check DB for inserted rows

---

## Performance Considerations

- Agent processing: <100ms (acceptable for real-time chat)
- DB queries: Keep to minimum (beneficiaries list, settings)
- Consider caching beneficiary list on client
- Add rate limiting on endpoints (e.g., 10 requests/min)

---

## Security Considerations

- ✅ Always extract user_id from JWT (use Depends(get_current_user_id))
- ✅ Enforce user isolation at agent level (agents already do this)
- ✅ Validate all context data (agents already do)
- ✅ Log all payment attempts (add logging to endpoints)
- ✅ Rate limit for MPIN entry attempts

---

## Next Steps After Chat Integration

1. **Frontend Payment UI**: Create full payment form + history view
2. **Recurring Management**: Show upcoming payments, pause/resume UI
3. **Testing**: 30+ integration tests for agent flows
4. **Monitoring**: Add metrics for payment volumes, agent latency
5. **Performance**: Load test with 1000+ concurrent chat sessions

---

## Resources

- **Agent docs**: See `docs/PHASE4-SUMMARY.md`
- **API reference**: See `docs/PAYMENT-SYSTEM-COMPLETE.md`
- **Example agent usage**: See docstrings in `app/agents/payment_agent.py`
- **Testing patterns**: See `docs/testing-guide.md` (to be created)

---

**Ready to start Phase 5? Follow the steps above in sequence!**
