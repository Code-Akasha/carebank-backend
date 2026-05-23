from sqlalchemy import JSON, Column, Float, String, Text

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    type = Column(String, index=True, nullable=False)  # e.g., savings_plan, loan
    provider_id = Column(String, index=True, nullable=True)
    description = Column(Text, nullable=True)
    min_balance_required = Column(Float, nullable=True)
    interest_rate = Column(Float, nullable=True)

    # JSON field for storing deterministic eligibility rules
    eligibility_rules = Column(JSON, nullable=True)
