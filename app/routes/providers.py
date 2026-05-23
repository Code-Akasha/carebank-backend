from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.provider import Provider
from app.schemas.models import ProviderResponse
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _persist_providers(db: Session, records: list[dict]) -> None:
    if not records:
        return
    for record in records:
        provider = db.query(Provider).filter(Provider.id == record.get("id")).first()
        if provider:
            provider.name = record.get("name", provider.name)
            provider.status = record.get("status", provider.status)
            provider.country = record.get("country", provider.country)
            provider.channels = record.get("channels", provider.channels)
            provider.latency_ms = record.get("latency_ms", provider.latency_ms)
            provider.logo_url = record.get("logo_url", provider.logo_url)
            provider.support_contact = record.get(
                "support_contact",
                provider.support_contact,
            )
        else:
            db.add(
                Provider(
                    id=record.get("id"),
                    name=record.get("name", "Unknown Provider"),
                    status=record.get("status"),
                    country=record.get("country"),
                    channels=record.get("channels"),
                    latency_ms=record.get("latency_ms"),
                    logo_url=record.get("logo_url"),
                    support_contact=record.get("support_contact"),
                ),
            )
    db.commit()


@router.get("/", response_model=list[ProviderResponse])
async def list_providers(db: Session = Depends(get_db)):
    client = get_banking_client()
    try:
        records = await client.get_providers()
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    _persist_providers(db, records)
    return records
