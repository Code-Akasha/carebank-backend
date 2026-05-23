from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    merchant = Column(String, index=True)
    category = Column(String, index=True)
    description = Column(Text, nullable=True)

    # Example for pgvector (could be transaction embedding for similarity search)
    # embedding = Column(Vector(1536))
