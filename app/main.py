from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.routes.transactions import router as transactions_router
from app.routes.balances import router as balances_router
from app.routes.products import router as products_router
from app.routes.accounts import router as accounts_router
from app.routes.providers import router as providers_router
from app.routes.health_score import router as health_score_router
from app.routes.chat import router as chat_router
from app.routes.simulate import router as simulate_router
from app.routes.events import router as events_router
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CareBank Backend",
    description="Personalized Banking & Financial Wellness API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(transactions_router)
app.include_router(balances_router)
app.include_router(products_router)
app.include_router(accounts_router)
app.include_router(providers_router)
app.include_router(health_score_router)
app.include_router(chat_router)
app.include_router(simulate_router)
app.include_router(events_router)


@app.get("/")
def health():
    return {"status": "CareBank Backend Running", "version": "0.2.0"}
