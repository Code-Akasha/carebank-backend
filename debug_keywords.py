from app.agents.coordinator import _ordered_keyword_intents, _INTENT_KEYWORDS

msg1 = 'what is my balance how can i improve my savings'
msg2 = "what's my current balance and how can I save more"

print('Message 1:', msg1)
print('Keywords found:', _ordered_keyword_intents(msg1.lower()))

print('\nMessage 2:', msg2)
print('Keywords found:', _ordered_keyword_intents(msg2.lower()))

print('\nAvailable keywords:')
for intent, keywords in _INTENT_KEYWORDS.items():
    print(f'  {intent}: {keywords}')
