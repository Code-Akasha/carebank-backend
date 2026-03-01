from sqlalchemy import Column, String, Float, JSON

from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    account_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    provider_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    mask = Column(String, nullable=True)
    currency = Column(String, default="INR")
    institution = Column(String, nullable=True)
    current_balance = Column(Float, default=0.0)
    available_balance = Column(Float, default=0.0)
    status = Column(String, default="active")
    last_statement_date = Column(String, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
