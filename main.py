from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import socketio

import models, schemas, database
from database import engine, get_db
import integrations
import chat as chat_module
from routers.ussd import router as ussd_router
from routers.ussd_api import router as ussd_api_router



# Create tables (includes chat_messages table via chat import)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Zedagro Backend Service")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Support Chat Module ──────────────────────────────────────────────────────
app.include_router(chat_module.router)

# ── USSD Module ─────────────────────────────────────────────────────────────
app.include_router(ussd_router)
app.include_router(ussd_api_router)



# Wrap the entire FastAPI app with Socket.io's ASGI layer.
# The sio server intercepts WebSocket upgrade requests for /socket.io/
# and passes all regular HTTP requests through to FastAPI.
socket_app = socketio.ASGIApp(chat_module.sio, other_asgi_app=app)


@app.get("/")
def read_root():
    return {"message": "Welcome to the Zedagro Backend Service"}

# --- FARMERS ROUTES ---
@app.get("/farmers", response_model=List[schemas.Farmer])
def get_farmers(db: Session = Depends(get_db)):
    return db.query(models.Farmer).all()

@app.post("/farmers", response_model=schemas.Farmer)
def create_farmer(farmer: schemas.FarmerCreate, db: Session = Depends(get_db)):
    # External verification
    nrc_status = integrations.ExternalIntegrations.verify_nrc(farmer.nrc)
    if not nrc_status["valid"]:
        raise HTTPException(status_code=400, detail="NRC verification failed")
    
    db_farmer = models.Farmer(**farmer.dict())
    db.add(db_farmer)
    db.commit()
    db.refresh(db_farmer)
    return db_farmer

# --- VOUCHERS ROUTES ---
@app.get("/vouchers", response_model=List[schemas.FISPVoucher])
def get_vouchers(db: Session = Depends(get_db)):
    return db.query(models.FISPVoucher).all()

# --- PAYMENTS ROUTES ---
@app.get("/payments", response_model=List[schemas.Payment])
def get_payments(db: Session = Depends(get_db)):
    return db.query(models.Payment).all()

@app.post("/payments", response_model=schemas.Payment)
def create_payment(payment: schemas.PaymentCreate, db: Session = Depends(get_db)):
    db_payment = models.Payment(**payment.dict())
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment

@app.post("/payments/bulk", response_model=List[schemas.Payment])
def create_payments_bulk(payments: List[schemas.PaymentCreate], db: Session = Depends(get_db)):
    db_payments = [models.Payment(**p.dict()) for p in payments]
    db.add_all(db_payments)
    db.commit()
    for p in db_payments:
        db.refresh(p)
    return db_payments

# --- LOGISTICS ROUTES ---
@app.get("/logistics", response_model=List[schemas.LogisticsTrip])
def get_logistics(db: Session = Depends(get_db)):
    return db.query(models.LogisticsTrip).all()

@app.post("/logistics", response_model=schemas.LogisticsTrip)
def create_logistics_request(trip: schemas.LogisticsTripCreate, db: Session = Depends(get_db)):
    db_trip = models.LogisticsTrip(**trip.dict())
    db.add(db_trip)
    db.commit()
    db.refresh(db_trip)
    return db_trip

@app.patch("/logistics/{trip_id}/assign", response_model=schemas.LogisticsTrip)
def assign_logistics(trip_id: int, assignment: schemas.LogisticsAssign, db: Session = Depends(get_db)):
    db_trip = db.query(models.LogisticsTrip).filter(models.LogisticsTrip.id == trip_id).first()
    if not db_trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    for key, value in assignment.dict().items():
        setattr(db_trip, key, value)
    
    db.commit()
    db.refresh(db_trip)
    return db_trip

@app.patch("/logistics/{trip_id}/status", response_model=schemas.LogisticsTrip)
def update_logistics_status(trip_id: int, update: schemas.LogisticsStatusUpdate, db: Session = Depends(get_db)):
    db_trip = db.query(models.LogisticsTrip).filter(models.LogisticsTrip.id == trip_id).first()
    if not db_trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    for key, value in update.dict(exclude_unset=True).items():
        setattr(db_trip, key, value)
    
    db.commit()
    db.refresh(db_trip)
    return db_trip

# --- STORAGE DEPOT ROUTES ---
@app.get("/storage", response_model=List[schemas.StorageDepot])
def get_storage(db: Session = Depends(get_db)):
    return db.query(models.StorageDepot).all()

# --- FRAUD ALERT ROUTES ---
@app.get("/fraud-alerts", response_model=List[schemas.FraudAlert])
def get_fraud_alerts(db: Session = Depends(get_db)):
    return db.query(models.FraudAlert).all()

# --- SEED DATA FUNCTION ---
@app.post("/seed-data")
def seed_data(db: Session = Depends(get_db)):
    # Clear existing data
    db.query(models.Farmer).delete()
    db.query(models.FISPVoucher).delete()
    db.query(models.Payment).delete()
    db.query(models.LogisticsTrip).delete()
    db.query(models.StorageDepot).delete()
    db.query(models.FraudAlert).delete()
    db.commit()

    # Seed Farmers
    farmers_data = [
        {
            "zedId": "ZED-882931", "name": "Mubanga Kalunga", "nrc": "443212/11/1",
            "phone": "+260 977 123 456", "district": "Lusaka West", "province": "Lusaka",
            "farmSize": 5.0, "verifiedSize": 4.2, "status": "drone_verified",
            "crops": ["Maize", "Soya"], "lat": -15.4167, "lng": 28.2833,
            "registeredDate": "2025-03-12", "biometricVerified": True
        },
        {
            "zedId": "ZED-554021", "name": "Kelvin Phiri", "nrc": "112039/10/1",
            "phone": "+260 955 345 678", "district": "Ndola", "province": "Copperbelt",
            "farmSize": 3.5, "verifiedSize": 3.5, "status": "pending_survey",
            "crops": ["Maize"], "lat": -12.9708, "lng": 28.6366,
            "registeredDate": "2025-04-22", "biometricVerified": True
        },
        # Add more farmers as needed...
    ]
    for farmer in farmers_data:
        db.add(models.Farmer(**farmer))
    
    # Add other seed data (Vouchers, Payments, etc.) following the mock data in data.ts
    
    # Vouchers
    vouchers_data = [
        {
            "voucherId": "FISP-9921", "farmerId": "1", "farmerName": "Banda Kelvin",
            "district": "Lusaka District", "items": [{"name": "Urea Fertilizer", "qty": 2, "unit": "50kg bags"}],
            "status": "redeemed", "issuedDate": "2025-11-12", "redeemedDate": "2026-03-08",
            "season": "2026", "agroDealer": "Lusaka West Agrostore"
        }
    ]
    for voucher in vouchers_data:
        db.add(models.FISPVoucher(**voucher))

    # Payments
    payments_data = [
        {
            "farmerId": "1", "farmerName": "Mubanga Kalunga", "amount": 18750.0,
            "produce": "Maize", "quantity": 2500.0, "unitPrice": 7.5,
            "method": "mobile_money", "provider": "MTN MoMo", "status": "completed",
            "date": "2026-03-06", "transactionRef": "MTN-20263060001"
        }
    ]
    for payment in payments_data:
        db.add(models.Payment(**payment))
    
    # Logistics
    logistics_data = [
        {
            "truckId": None, "driver": None, "fieldAgentId": "agent_01", "farmerId": "farmer_88",
            "farmerName": "Mwape Farms Ltd", "origin": "Farm (Mansa)", "destination": "FRA Storage (Ndola)",
            "produce": "Soya", "weight": 12.0, "status": "ready", "scheduledDate": "2026-03-08",
            "progress": 0, "eta": None
        },
        {
            "truckId": "TRK-902", "driver": "Chanda Musonda", "fieldAgentId": "agent_02", "farmerId": "farmer_31",
            "farmerName": "Mubanga Kalunga", "origin": "Farm (Lusaka)", "destination": "FRA Storage (Lusaka)",
            "produce": "Maize", "weight": 4.2, "status": "assigned", "scheduledDate": "2026-03-09",
            "progress": 10, "eta": "Arrival 14:00"
        },
        {
            "truckId": "TRK-451", "driver": "John Phiri", "fieldAgentId": "agent_03", "farmerId": "farmer_22",
            "farmerName": "Grace Mwanza", "origin": "Farm (Kabwe)", "destination": "FRA Storage (Lusaka)",
            "produce": "Maize", "weight": 15.0, "status": "in_transit", "scheduledDate": "2026-03-10",
            "progress": 45, "eta": "2h 30m"
        },
        {
            "truckId": "TRK-229", "driver": "Peter Banda", "fieldAgentId": "agent_01", "farmerId": "farmer_15",
            "farmerName": "Patrick Banda", "origin": "Farm (Chipata)", "destination": "FRA Storage (Chipata)",
            "produce": "Maize", "weight": 11.8, "status": "delivered", "scheduledDate": "2026-03-05",
            "progress": 100, "eta": "Arrived"
        }
    ]
    for trip in logistics_data:
        db.add(models.LogisticsTrip(**trip))

    # Storage
    storage_data = [
        {"name": "Lusaka Central", "location": "Lusaka", "capacity": 50000, "used": 42500, "province": "Lusaka"},
        {"name": "Ndola Regional", "location": "Ndola", "capacity": 35000, "used": 21000, "province": "Copperbelt"},
    ]
    for depot in storage_data:
        db.add(models.StorageDepot(**depot))

    # Fraud Alerts
    fraud_data = [
        {
            "farmerId": "5", "farmerName": "Grace Mwanza", "zedId": "ZED-773122",
            "type": "Farm Size Discrepancy", "severity": "critical", "date": "2026-03-07",
            "description": "Claimed farm size exceeds verified by 16%.", "status": "investigating"
        }
    ]
    for alert in fraud_data:
        db.add(models.FraudAlert(**alert))

    db.commit()
    return {"message": "Database seeded successfully!"}
