from sqlalchemy import Column, Integer, String, Float, Text, JSON
from app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    type = Column(String, index=True, nullable=False) # e.g., savings_plan, loan
    description = Column(Text, nullable=True)
    min_balance_required = Column(Float, nullable=True)
    interest_rate = Column(Float, nullable=True)
    
    # JSON field for storing deterministic eligibility rules
    eligibility_rules = Column(JSON, nullable=True)
