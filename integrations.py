import random

class ExternalIntegrations:
    @staticmethod
    def get_gis_coordinates(zed_id: str):
        # Simulate call to external GIS API
        return {
            "zedId": zed_id,
            "lat": -15.4167 + random.uniform(-0.1, 0.1),
            "lng": 28.2833 + random.uniform(-0.1, 0.1),
            "status": "synchronized"
        }

    @staticmethod
    def verify_nrc(nrc_number: str):
        # Simulate call to National Registration Database
        return {
            "nrc": nrc_number,
            "valid": True,
            "match": "Full",
            "source": "DNRPC"
        }

    @staticmethod
    def post_payment_gateway(payment_data: dict):
        # Simulate call to Mobile Money / Bank Gateway
        return {
            "status": "success",
            "transaction_id": f"EXT-{random.randint(10000, 99999)}",
            "provider_response": "Processed successfully"
        }

    @staticmethod
    def send_sms_africastalking(phone_number: str, message: str):
        # Simulate call to Africa's Talking Text Service
        print(f"[Africa's Talking] Sending SMS to {phone_number}: {message}")
        return {
            "SMSMessageData": {
                "Message": f"Sent to 1/1 Total Cost: K0.25",
                "Recipients": [{"number": phone_number, "status": "Success", "messageId": "AT-MSG-12345"}]
            }
        }
