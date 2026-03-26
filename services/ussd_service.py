import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ZEDAGRO_API_URL", "http://localhost:8000/v1")
TIMEOUT  = 5.0


async def get_last_payment(farmer_id: str, phone: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/payments/ussd/{farmer_id}",
                params={"phone": phone},
                timeout=TIMEOUT,
            )
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def get_fisp_status(farmer_id: str, phone: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/fisp/ussd/{farmer_id}",
                params={"phone": phone},
                timeout=TIMEOUT,
            )
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def get_active_trip(farmer_id: str, phone: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/logistics/ussd/{farmer_id}",
                params={"phone": phone},
                timeout=TIMEOUT,
            )
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def get_farmer_details(farmer_id: str, phone: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/farmers/ussd/{farmer_id}",
                params={"phone": phone},
                timeout=TIMEOUT,
            )
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def get_assigned_agent(farmer_id: str, phone: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/agents/ussd/{farmer_id}",
                params={"phone": phone},
                timeout=TIMEOUT,
            )
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def register_farmer_ussd(data: dict):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/farmers/ussd/register",
                json=data,
                timeout=8.0,
            )
            return r.json() if r.status_code in (200, 201) else {"success": False}
    except Exception:
        return {"success": False}
