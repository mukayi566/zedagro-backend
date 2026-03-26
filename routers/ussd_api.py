from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from database import get_db
import models, schemas
import random
from services.supabase_service import register_farmer_in_supabase

router = APIRouter(prefix="/v1", tags=["USSD REST API"])

@router.get("/payments/ussd/{zed_id}")
async def get_payment_ussd(zed_id: str, phone: str, db: Session = Depends(get_db)):
    farmer = db.query(models.Farmer).filter(models.Farmer.zedId == zed_id).first()
    if not farmer:
        return None
    
    # In real app, check if phone matches
    # if farmer.phone != phone: return None
    
    last_payment = db.query(models.Payment).filter(models.Payment.farmerId == zed_id).order_by(models.Payment.id.desc()).first()
    if not last_payment:
        # For demo, if no real payment, return a mock one for valid ID
        return {
            "name": farmer.name,
            "zedagro_id": zed_id,
            "amount": 4500.0,
            "date": "2025-05-15",
            "method": "Mobile Money",
            "status": "Completed",
            "season_total": 12500.0
        }

    total = db.query(func.sum(models.Payment.amount)).filter(models.Payment.farmerId == zed_id).scalar() or 0.0

    return {
        "name": farmer.name,
        "zedagro_id": zed_id,
        "amount": last_payment.amount,
        "date": last_payment.date,
        "method": last_payment.method,
        "status": last_payment.status,
        "season_total": total
    }

@router.get("/fisp/ussd/{zed_id}")
async def get_fisp_ussd(zed_id: str, phone: str = None, db: Session = Depends(get_db)):
    farmer = db.query(models.Farmer).filter(models.Farmer.zedId == zed_id).first()
    if not farmer:
        return None
        
    voucher = db.query(models.FISPVoucher).filter(models.FISPVoucher.farmerId == zed_id).first()
    if not voucher:
        return None

    return {
        "name": farmer.name,
        "status": voucher.status,
        "redeemed_at": voucher.redeemedDate or "N/A",
        "agrodealer": voucher.agroDealer or "N/A",
        "items": ", ".join([f"{i.name}" for i in [schemas.VoucherItem(**item) for item in voucher.items]]),
        "qr_ref": voucher.voucherId,
        "expires": "2026-10-31"
    }

@router.get("/logistics/ussd/{zed_id}")
async def get_logistics_ussd(zed_id: str, phone: str = None, db: Session = Depends(get_db)):
    farmer = db.query(models.Farmer).filter(models.Farmer.zedId == zed_id).first()
    if not farmer:
        return None

    trip = db.query(models.LogisticsTrip).filter(models.LogisticsTrip.farmerId == zed_id).order_by(models.LogisticsTrip.id.desc()).first()
    if not trip:
        return None

    return {
        "farmer": farmer.name,
        "produce": trip.produce,
        "kg": int(trip.weight * 1000) if trip.weight < 1000 else int(trip.weight), # assuming weight is tons if small, or kg
        "status": trip.status,
        "plate": trip.truckId or "PENDING",
        "driver": trip.driver or "Not Assigned",
        "from": trip.origin,
        "to": trip.destination,
        "progress": trip.progress,
        "eta": trip.eta or "TBD"
    }

@router.get("/farmers/ussd/{zed_id}")
async def get_farmer_ussd(zed_id: str, phone: str = None, db: Session = Depends(get_db)):
    farmer = db.query(models.Farmer).filter(models.Farmer.zedId == zed_id).first()
    if not farmer:
        return None

    return {
        "name": farmer.name,
        "zedagro_id": farmer.zedId,
        "district": farmer.district,
        "region": farmer.province,
        "farm_size_verified": farmer.verifiedSize,
        "farm_size_claimed": farmer.farmSize,
        "crops": farmer.crops,
        "status": farmer.status,
        "farmer_type": "smallholder" if farmer.farmSize < 10 else "commercial"
    }

@router.get("/agents/ussd/{zed_id}")
async def get_agent_ussd(zed_id: str, phone: str = None, db: Session = Depends(get_db)):
    # Currently no Agent model, return a default mock
    return {
        "name": "Chanda Mumba",
        "phone": "+260 971 000 111",
        "region": "Lusaka West",
        "status": "Active"
    }

@router.post("/farmers/ussd/register")
async def register_farmer_ussd(data: Dict[str, Any], db: Session = Depends(get_db)):
    new_zed_id = f"ZED-{random.randint(100000, 999999)}"
    
    # Check if NRC already exists
    existing = db.query(models.Farmer).filter(models.Farmer.nrc == data['nrc']).first()
    if existing:
        return {"success": False, "error": "NRC already registered"}

    new_farmer = models.Farmer(
        zedId=new_zed_id,
        name=data['name'],
        nrc=data['nrc'],
        phone=data['phone'],
        province=data['region'],
        district="TBD",
        farmSize=0.0,
        verifiedSize=0.0,
        status="pending_lite",
        crops=[],
        lat=0.0,
        lng=0.0,
        registeredDate="2026-03-26"
    )
    
    db.add(new_farmer)
    db.commit()
    db.refresh(new_farmer)
    
    # Push to Supabase for real-time synchronization with the frontend
    try:
        import asyncio
        asyncio.create_task(register_farmer_in_supabase({
            "zedId": new_zed_id,
            "name": data['name'],
            "nrc": data['nrc'],
            "phone": data['phone'],
            "region": data['region'],
            "status": "pending_lite",
            "registeredDate": "2026-03-26"
        }))
    except Exception as e:
        print(f"Supabase sync error: {str(e)}")
    
    return {
        "success": True,
        "zedagro_id": new_zed_id
    }
