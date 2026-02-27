from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.product import Product
from app.schemas.models import ProductResponse

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()
