from fastapi import FastAPI

from app.routes.transactions import router as transactions_router
from app.routes.balances import router as balances_router
from app.routes.products import router as products_router
from app.routes.health_score import router as health_score_router
from app.routes.chat import router as chat_router
from app.routes.simulate import router as simulate_router

app = FastAPI(
    title="CareBank Backend",
    description="Personalized Banking & Financial Wellness API",
    version="0.1.0",
)

app.include_router(transactions_router)
app.include_router(balances_router)
app.include_router(products_router)
app.include_router(health_score_router)
app.include_router(chat_router)
app.include_router(simulate_router)


@app.get("/")
def health():
    return {"status": "CareBank Backend Running"}
