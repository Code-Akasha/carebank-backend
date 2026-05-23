import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/products", tags=["products"])


def _normalize_product(record: dict) -> dict:
    normalized = dict(record)
    if "type" not in normalized or not normalized.get("type"):
        normalized["type"] = normalized.get("category")
    return normalized


def _persist_products(db: Session, products: list[dict]) -> None:
    """Upsert products using raw SQL to avoid ORM schema conflicts."""
    if not products:
        return
    for record in products:
        normalized = _normalize_product(record)
        eligibility = normalized.get("eligibility_rules")
        eligibility_json = json.dumps(eligibility) if eligibility else None
        db.execute(
            text(
                """
                INSERT INTO products
                    (id, name, type, provider_id, description,
                     min_balance_required, interest_rate, eligibility_rules)
                VALUES
                    (:id, :name, :type, :provider_id, :description,
                     :min_balance_required, :interest_rate, :eligibility_rules)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    provider_id = excluded.provider_id,
                    description = excluded.description,
                    min_balance_required = excluded.min_balance_required,
                    interest_rate = excluded.interest_rate,
                    eligibility_rules = excluded.eligibility_rules
                """,
            ),
            {
                "id": normalized.get("id"),
                "name": normalized.get("name"),
                "type": normalized.get("type"),
                "provider_id": normalized.get("provider_id"),
                "description": normalized.get("description"),
                "min_balance_required": normalized.get("min_balance_required"),
                "interest_rate": normalized.get("interest_rate"),
                "eligibility_rules": eligibility_json,
            },
        )
    db.commit()


@router.get("/bank-policies")
async def get_bank_policies() -> dict:
    """Return MockBank regulatory policy catalog (India-first rails + action caps)."""
    client = get_banking_client()
    try:
        return await client.get_banking_policies()
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}",
        ) from exc


@router.get("/bank-plans")
async def get_bank_plans() -> dict:
    """Return MockBank account plan catalog as the source of truth."""
    client = get_banking_client()
    try:
        return await client.get_bank_plans()
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}",
        ) from exc


@router.get("/")
async def list_products(db: Session = Depends(get_db)) -> list:
    """Return products from the mock bank, persisting locally for caching."""
    client = get_banking_client()
    try:
        products = await client.get_products()
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}",
        ) from exc

    normalized_products = [_normalize_product(record) for record in products]
    _persist_products(db, normalized_products)
    return normalized_products
