import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # Fallback to defaults or log warning
    print("WARNING: Supabase credentials not found in .env")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

async def register_farmer_in_supabase(farmer_data: dict):
    """
    Pushes farmer registration data to the 'farmers' table in Supabase.
    """
    if not supabase:
        print("ERROR: Supabase client not initialized")
        return {"success": False, "error": "Supabase connection failed"}
        
    try:
        # Map fields to match Supabase table schema 'farmers'
        # The schema might use camelCase like the frontend: zedId, name, nrc, phone, etc.
        data = {
            "zedId": farmer_data.get("zedId"),
            "name": farmer_data.get("name"),
            "nrc": farmer_data.get("nrc"),
            "phone": farmer_data.get("phone"),
            "district": farmer_data.get("district", "TBD"),
            "province": farmer_data.get("region"),
            "farmSize": farmer_data.get("farmSize", 0.0),
            "status": farmer_data.get("status", "pending_lite"),
            "registeredDate": farmer_data.get("registeredDate", "2026-03-26")
        }
        
        response = supabase.table("farmers").insert(data).execute()
        return {"success": True, "data": response.data}
        
    except Exception as e:
        print(f"Supabase Registration Error: {str(e)}")
        return {"success": False, "error": str(e)}
