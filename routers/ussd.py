from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse
from services.ussd_service import (
    get_last_payment,
    get_fisp_status,
    get_active_trip,
    get_farmer_details,
    get_assigned_agent,
    register_farmer_ussd,
)

router = APIRouter(prefix="/ussd", tags=["USSD"])

REGIONS = {
    "1": "Lusaka",      "2": "Copperbelt",   "3": "Eastern",
    "4": "Northern",    "5": "Southern",      "6": "Western",
    "7": "North-Western","8": "Luapula",      "9": "Muchinga",
    "10": "Central",
}

FARMER_TYPES = {
    "1": "smallholder",
    "2": "commercial",
}


@router.post("", response_class=PlainTextResponse)
async def ussd_handler(
    sessionId:   str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text:        str = Form(""),
):
    # Split input into steps e.g. "1*2*ZED001" → ["1","2","ZED001"]
    steps = text.split("*") if text else []

    # ── MAIN MENU ─────────────────────────────────────────────
    if text == "":
        return (
            "CON Welcome to ZEDAGRO 🌾\n"
            "1. Check My Payment\n"
            "2. My FISP Voucher Status\n"
            "3. Track My Produce\n"
            "4. My Farm Details\n"
            "5. Register as Farmer\n"
            "6. Contact Field Agent"
        )

    # ── 1. PAYMENT ────────────────────────────────────────────
    if steps[0] == "1":
        if len(steps) == 1:
            return (
                "CON Payment Information\n"
                "Enter your ZEDAGRO Farmer ID:\n"
                "(e.g. ZED001234)"
            )

        farmer_id = steps[1]
        payment = await get_last_payment(farmer_id, phoneNumber)

        if not payment:
            return (
                f"END No account found for {farmer_id}.\n"
                "Check your ID and try again.\n"
                "Call 0800-FRA-HELP for assistance."
            )

        return (
            "END Payment Details\n"
            f"Farmer: {payment['name']}\n"
            f"ID: {payment['zedagro_id']}\n\n"
            f"Last Payment: K{payment['amount']}\n"
            f"Date: {payment['date']}\n"
            f"Method: {payment['method']}\n"
            f"Status: {payment['status']}\n\n"
            f"Season total: K{payment['season_total']}"
        )

    # ── 2. FISP VOUCHER ───────────────────────────────────────
    if steps[0] == "2":
        if len(steps) == 1:
            return (
                "CON FISP Voucher Status\n"
                "Enter your ZEDAGRO Farmer ID:"
            )

        farmer_id = steps[1]
        voucher = await get_fisp_status(farmer_id, phoneNumber)

        if not voucher:
            return (
                f"END No FISP record found for {farmer_id}.\n"
                "Visit your nearest FRA office\n"
                "or call 0800-FRA-HELP."
            )

        status = voucher.get("status")

        if status == "redeemed":
            return (
                "END FISP Voucher Status\n"
                f"Farmer: {voucher['name']}\n"
                "Status: REDEEMED ✓\n\n"
                f"Redeemed: {voucher['redeemed_at']}\n"
                f"At: {voucher['agrodealer']}\n"
                f"Items: {voucher['items']}\n\n"
                "No further action needed."
            )

        if status == "issued":
            return (
                "END FISP Voucher Status\n"
                f"Farmer: {voucher['name']}\n"
                "Status: READY TO USE\n\n"
                f"Voucher: {voucher['qr_ref']}\n"
                f"Items: {voucher['items']}\n"
                "Show this to any registered\n"
                "agrodealer to redeem.\n"
                f"Valid until: {voucher['expires']}"
            )

        return (
            "END FISP Voucher Status\n"
            f"Farmer: {voucher['name']}\n"
            f"Status: {status.upper()}\n\n"
            "Complete your farm verification\n"
            "first. Contact your field agent."
        )

    # ── 3. PRODUCE TRACKING ───────────────────────────────────
    if steps[0] == "3":
        if len(steps) == 1:
            return (
                "CON Track My Produce\n"
                "Enter your ZEDAGRO Farmer ID:"
            )

        farmer_id = steps[1]
        trip = await get_active_trip(farmer_id, phoneNumber)

        if not trip:
            return (
                "END No active delivery found.\n"
                "Your produce has not been\n"
                "collected yet OR delivery\n"
                "is already complete."
            )

        return (
            "END Produce Tracking\n"
            f"Farmer: {trip['farmer']}\n"
            f"Produce: {trip['produce']} {trip['kg']}kg\n\n"
            f"Status: {trip['status']}\n"
            f"Truck: {trip['plate']}\n"
            f"Driver: {trip['driver']}\n\n"
            f"From: {trip['from']}\n"
            f"To:   {trip['to']}\n"
            f"Progress: {trip['progress']}%\n"
            f"ETA: {trip['eta']}\n\n"
            "Payment sent when delivered."
        )

    # ── 4. FARM DETAILS ───────────────────────────────────────
    if steps[0] == "4":
        if len(steps) == 1:
            return (
                "CON My Farm Details\n"
                "Enter your ZEDAGRO Farmer ID:"
            )

        farmer_id = steps[1]
        farmer = await get_farmer_details(farmer_id, phoneNumber)

        if not farmer:
            return (
                "END No account found.\n"
                "Register first by selecting\n"
                "option 5 from the main menu."
            )

        size = (
            f"{farmer['farm_size_verified']}ha (verified)"
            if farmer.get("farm_size_verified")
            else f"{farmer['farm_size_claimed']}ha (not verified)"
        )

        return (
            "END Farm Details\n"
            f"Name: {farmer['name']}\n"
            f"ID: {farmer['zedagro_id']}\n"
            f"District: {farmer['district']}\n"
            f"Region: {farmer['region']}\n\n"
            f"Farm Size: {size}\n"
            f"Crops: {', '.join(farmer['crops'])}\n"
            f"Status: {farmer['status'].upper()}\n"
            f"Type: {farmer['farmer_type']}"
        )

    # ── 5. REGISTER ───────────────────────────────────────────
    if steps[0] == "5":
        if len(steps) == 1:
            return (
                "CON Register as Farmer\n"
                "Do you have a smartphone?\n\n"
                "1. Yes - I will use the app\n"
                "2. No  - Register via USSD now"
            )

        # Has smartphone — direct to app
        if steps[1] == "1":
            return (
                "END Download ZEDAGRO App\n"
                "Search 'ZEDAGRO' on Google\n"
                "Play Store or App Store.\n\n"
                "Or visit: zedagro.gov.zm\n\n"
                f"Your number {phoneNumber}\n"
                "will be your login."
            )

        # USSD registration flow
        if steps[1] == "2":
            if len(steps) == 2:
                return (
                    "CON USSD Registration\n"
                    "Step 1 of 4\n\n"
                    "Enter your full name:\n"
                    "(as it appears on your NRC)"
                )

            if len(steps) == 3:
                return (
                    "CON USSD Registration\n"
                    "Step 2 of 4\n\n"
                    "Enter your NRC number:\n"
                    "(e.g. 123456/78/1)"
                )

            if len(steps) == 4:
                return (
                    "CON USSD Registration\n"
                    "Step 3 of 4\n\n"
                    "Select your region:\n"
                    "1. Lusaka\n"
                    "2. Copperbelt\n"
                    "3. Eastern\n"
                    "4. Northern\n"
                    "5. Southern\n"
                    "6. Western\n"
                    "7. Others"
                )

            if len(steps) == 5:
                return (
                    "CON USSD Registration\n"
                    "Step 4 of 4\n\n"
                    "Select your farmer type:\n"
                    "1. Smallholder Farmer\n"
                    "   (family farm / food)\n"
                    "2. Commercial Farmer\n"
                    "   (farming for sale)"
                )

            if len(steps) == 6:
                name        = steps[2]
                nrc         = steps[3]
                region_code = steps[4]
                type_code   = steps[5]

                result = await register_farmer_ussd({
                    "name":        name,
                    "nrc":         nrc,
                    "phone":       phoneNumber,
                    "region":      REGIONS.get(region_code, "Unknown"),
                    "farmer_type": FARMER_TYPES.get(type_code, "smallholder"),
                    "status":      "pending_lite",
                    "source":      "ussd",
                })

                if result.get("success"):
                    return (
                        "END Registration Received!\n"
                        f"Name: {name}\n"
                        f"ID: {result['zedagro_id']}\n"
                        f"Phone: {phoneNumber}\n"
                        "Status: PENDING\n\n"
                        "A field agent will contact\n"
                        "you to complete verification.\n\n"
                        "Save your ZEDAGRO ID:\n"
                        f"{result['zedagro_id']}\n\n"
                        "Thank you for joining ZEDAGRO."
                    )

                return (
                    "END Registration Failed.\n"
                    f"NRC {nrc} may already be\n"
                    "registered or system error.\n\n"
                    "Try again or call:\n"
                    "0800-FRA-HELP"
                )

    # ── 6. CONTACT AGENT ─────────────────────────────────────
    if steps[0] == "6":
        if len(steps) == 1:
            return (
                "CON Contact Field Agent\n"
                "Enter your ZEDAGRO Farmer ID:"
            )

        farmer_id = steps[1]
        agent = await get_assigned_agent(farmer_id, phoneNumber)

        if not agent:
            return (
                "END No agent assigned yet.\n"
                "Call FRA Helpline:\n"
                "0800-FRA-HELP (Toll Free)\n\n"
                "Or visit your nearest\n"
                "FRA District Office."
            )

        return (
            "END Your Field Agent\n"
            f"Name: {agent['name']}\n"
            f"Phone: {agent['phone']}\n"
            f"Region: {agent['region']}\n"
            f"Status: {agent['status']}\n\n"
            "Call or SMS your agent\n"
            "directly using the number above.\n\n"
            "FRA Helpline (Toll Free):\n"
            "0800-FRA-HELP"
        )

    # ── INVALID ───────────────────────────────────────────────
    return (
        "END Invalid option selected.\n"
        "Please dial *384# again\n"
        "and choose from the menu."
    )
