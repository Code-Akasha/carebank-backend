from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.product import Product
from app.schemas.models import ProductResponse
from app.services.mockbank_client import get_mockbank_client, MockBankClientError

router = APIRouter(prefix="/api/products", tags=["products"])


def _persist_products(db: Session, products: list[dict]) -> None:
    if not products:
        return
    for record in products:
        product = db.query(Product).filter(Product.id == record.get("id")).first()
        if product:
            product.name = record.get("name", product.name)
            product.type = record.get("type", product.type)
            product.provider_id = record.get("provider_id", product.provider_id)
            product.description = record.get("description", product.description)
            product.min_balance_required = record.get(
                "min_balance_required", product.min_balance_required
            )
            product.interest_rate = record.get("interest_rate", product.interest_rate)
            product.eligibility_rules = record.get(
                "eligibility_rules", product.eligibility_rules
            )
        else:
            db.add(
                Product(
                    id=record.get("id"),
                    name=record.get("name"),
                    type=record.get("type"),
                    provider_id=record.get("provider_id"),
                    description=record.get("description"),
                    min_balance_required=record.get("min_balance_required"),
                    interest_rate=record.get("interest_rate"),
                    eligibility_rules=record.get("eligibility_rules"),
                )
            )
    db.commit()


@router.get("/", response_model=list[ProductResponse])
async def list_products(db: Session = Depends(get_db)):
    client = get_mockbank_client()
    try:
        products = await client.get_products()
    except MockBankClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"MockBank unavailable: {exc}"
        ) from exc

    _persist_products(db, products)
    return products
