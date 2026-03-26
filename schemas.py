from pydantic import BaseModel
from typing import List, Optional

class VoucherItem(BaseModel):
    name: str
    qty: float
    unit: str

class FarmerBase(BaseModel):
    zedId: str
    name: str
    nrc: str
    phone: str
    district: str
    province: str
    farmSize: float
    verifiedSize: float
    status: str
    crops: List[str]
    lat: float
    lng: float
    registeredDate: str
    biometricVerified: bool
    photo: Optional[str] = None

class FarmerCreate(FarmerBase):
    pass

class Farmer(FarmerBase):
    id: int

    class Config:
        from_attributes = True

class FISPVoucherBase(BaseModel):
    voucherId: str
    farmerId: str
    farmerName: str
    district: str
    items: List[VoucherItem]
    status: str
    issuedDate: str
    redeemedDate: Optional[str] = None
    agroDealer: Optional[str] = None
    season: str

class FISPVoucherCreate(FISPVoucherBase):
    pass

class FISPVoucher(FISPVoucherBase):
    id: int

    class Config:
        from_attributes = True

class PaymentBase(BaseModel):
    farmerId: str
    farmerName: str
    amount: float
    produce: str
    quantity: float
    unitPrice: float
    method: str
    provider: Optional[str] = None
    status: str
    date: str
    transactionRef: str

class PaymentCreate(PaymentBase):
    pass

class Payment(PaymentBase):
    id: int

    class Config:
        from_attributes = True

class LogisticsTripBase(BaseModel):
    truckId: Optional[str] = None
    driver: Optional[str] = None
    fieldAgentId: Optional[str] = None
    driverId: Optional[str] = None
    farmerId: Optional[str] = None
    farmerName: str
    origin: str
    destination: str
    produce: str
    weight: float
    status: str  # ready, assigned, loading, in_transit, arrived, delivered
    scheduledDate: str
    progress: int
    eta: Optional[str] = None

class LogisticsTripCreate(LogisticsTripBase):
    pass

class LogisticsTrip(LogisticsTripBase):
    id: int

    class Config:
        from_attributes = True

class StorageDepotBase(BaseModel):
    name: str
    location: str
    capacity: int
    used: int
    province: str

class StorageDepotCreate(StorageDepotBase):
    pass

class StorageDepot(StorageDepotBase):
    id: int

    class Config:
        from_attributes = True

class FraudAlertBase(BaseModel):
    farmerId: str
    farmerName: str
    zedId: str
    type: str
    severity: str
    description: str
    date: str
    status: str

class FraudAlertCreate(FraudAlertBase):
    pass

class FraudAlert(FraudAlertBase):
    id: int

    class Config:
        from_attributes = True

class LogisticsStatusUpdate(BaseModel):
    status: str
    progress: Optional[int] = None
    eta: Optional[str] = None

class LogisticsAssign(BaseModel):
    truckId: str
    driverId: str
    driver: str
    status: str = "assigned"
