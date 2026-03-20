from app.agents.coordinator import _classify_intent_keywords, _INTENT_KEYWORDS

msg = "what is my balance how can i improve my savings"

keyword_result = _classify_intent_keywords(msg)
print(f"Message: {msg}")
print(f"Intent: {keyword_result.intent}")
print(f"Secondary Intent: {keyword_result.secondary_intent}")
print(f"Confidence: {keyword_result.confidence}")
