from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Enum, JSON
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    zedId = Column(String, unique=True, index=True)
    name = Column(String)
    nrc = Column(String, unique=True)
    phone = Column(String)
    district = Column(String)
    province = Column(String)
    farmSize = Column(Float)
    verifiedSize = Column(Float)
    status = Column(String)  # drone_verified, pending_survey, flagged, active
    crops = Column(JSON)  # List of crops
    lat = Column(Float)
    lng = Column(Float)
    registeredDate = Column(String)
    biometricVerified = Column(Boolean, default=False)
    photo = Column(String, nullable=True)

class FISPVoucher(Base):
    __tablename__ = "vouchers"

    id = Column(Integer, primary_key=True, index=True)
    voucherId = Column(String, unique=True, index=True)
    farmerId = Column(String)
    farmerName = Column(String)
    district = Column(String)
    items = Column(JSON)  # List of objects: {name, qty, unit}
    status = Column(String)  # issued, redeemed, expired, revoked
    issuedDate = Column(String)
    redeemedDate = Column(String, nullable=True)
    agroDealer = Column(String, nullable=True)
    season = Column(String)

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    farmerId = Column(String)
    farmerName = Column(String)
    amount = Column(Float)
    produce = Column(String)
    quantity = Column(Float)
    unitPrice = Column(Float)
    method = Column(String)  # mobile_money, bank, wallet
    provider = Column(String, nullable=True)
    status = Column(String)  # pending, processing, completed, failed
    date = Column(String)
    transactionRef = Column(String, unique=True)

class LogisticsTrip(Base):
    __tablename__ = "logistics_trips"

    id = Column(Integer, primary_key=True, index=True)
    truckId = Column(String, nullable=True)
    driver = Column(String, nullable=True)
    fieldAgentId = Column(String, nullable=True)
    driverId = Column(String, nullable=True)
    farmerId = Column(String, nullable=True)
    farmerName = Column(String)
    origin = Column(String)
    destination = Column(String)
    produce = Column(String)
    weight = Column(Float)
    status = Column(String)  # ready, assigned, loading, in_transit, arrived, delivered
    scheduledDate = Column(String)
    progress = Column(Integer)
    eta = Column(String, nullable=True)

class StorageDepot(Base):
    __tablename__ = "storage_depots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    location = Column(String)
    capacity = Column(Integer)
    used = Column(Integer)
    province = Column(String)

class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)
    farmerId = Column(String)
    farmerName = Column(String)
    zedId = Column(String)
    type = Column(String)
    severity = Column(String)  # low, medium, high, critical
    description = Column(String)
    date = Column(String)
    status = Column(String)  # open, investigating, resolved
