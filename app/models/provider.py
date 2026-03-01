from sqlalchemy import Column, String, Integer, JSON

from app.core.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="online")
    country = Column(String, nullable=True)
    channels = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    logo_url = Column(String, nullable=True)
    support_contact = Column(String, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
