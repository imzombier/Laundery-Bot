from flask import Flask, request
import requests
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ==========================
# ENV VARIABLES (Render)
# ==========================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# ==========================
# GOOGLE SHEETS SETUP
# ==========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "service_account.json",
    scope
)

client = gspread.authorize(creds)
sheet = client.open("Laundry Orders").sheet1

# ==========================
# SEND WHATSAPP MESSAGE
# ==========================
def send_whatsapp_message(to, message, buttons=None):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    if buttons:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": message},
                "action": {"buttons": buttons}
            }
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# ==========================
# META WEBHOOK VERIFY
# ==========================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Verification failed", 403

# ==========================
# RECEIVE WHATSAPP MESSAGE
# ==========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    try:
        value = data["entry"][0]["changes"][0]["value"]

        if "messages" not in value:
            return "No message", 200

        message = value["messages"][0]
        from_number = message["from"]

        # BUTTON RESPONSE
        if "button" in message:
            button_id = message["button"]["payload"]

            if button_id == "pickup":
                send_whatsapp_message(from_number, "📦 Please share your *Name & Pickup Address*")
            elif button_id == "dry_cleaning":
                send_whatsapp_message(from_number, "🧼 Dry Cleaning selected. Send *Name & Address*")
            elif button_id == "home_delivery":
                send_whatsapp_message(from_number, "🚚 Home Delivery selected. Send *Name & Address*")

        # TEXT MESSAGE
        elif "text" in message:
            user_text = message["text"]["body"]

            sheet.append_row([
                user_text,
                from_number,
                "Pending Service",
                "Pending Address",
                "Pending"
            ])

            send_whatsapp_message(
                from_number,
                "✅ Thank you! Your laundry order is recorded.\nOur team will contact you soon."
            )

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200

# ==========================
# RENDER PORT
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
