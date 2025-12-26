from flask import Flask, request
import requests, os, random, datetime
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
# USER SESSION STORAGE
# ==========================
user_states = {}

# ==========================
# SEND WHATSAPP MESSAGE
# ==========================
def send_whatsapp_message(to, message, buttons=None):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

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

    requests.post(url, headers=headers, json=payload)


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
    print("FULL PAYLOAD:", data)

    try:
        value = data["entry"][0]["changes"][0]["value"]

        messages = value.get("messages")
        if not messages:
            return "OK", 200

        message = messages[0]
        from_number = message["from"]

        # ======================
        # BUTTON RESPONSE
        # ======================
        if message.get("type") == "interactive":
            button_id = message["interactive"]["button_reply"]["id"]

            if button_id == "slots":
                send_whatsapp_message(
                    from_number,
                    "📅 *Available Slots*\n\n"
                    "🟢 Morning: 9 AM – 12 PM\n"
                    "🟢 Afternoon: 12 PM – 3 PM\n"
                    "🟢 Evening: 3 PM – 6 PM\n\n"
                    "Click *Book Laundry* to continue."
                )

            elif button_id == "book":
                user_states[from_number] = {"step": "name"}
                send_whatsapp_message(
                    from_number,
                    "👤 Please enter your *Full Name*:"
                )

            return "OK", 200

        # ======================
        # TEXT MESSAGE
        # ======================
        if message.get("type") == "text":
            text = message["text"]["body"].strip().lower()

            # GREETING
            if text in ["hi", "hello", "hai", "hey"]:
                buttons = [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "slots",
                            "title": "📅 Check Slots"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "book",
                            "title": "🧺 Book Laundry"
                        }
                    }
                ]

                send_whatsapp_message(
                    from_number,
                    "👋 *Welcome to Laundry Service!*\n\n"
                    "We provide fast & affordable laundry services.\n\n"
                    "Please choose an option 👇",
                    buttons
                )
                return "OK", 200

            # ======================
            # BOOKING FLOW
            # ======================
            if from_number in user_states:
                state = user_states[from_number]

                if state["step"] == "name":
                    state["name"] = text.title()
                    state["step"] = "mobile"
                    send_whatsapp_message(
                        from_number,
                        "📞 Please enter your *Mobile Number*:"
                    )
                    return "OK", 200

                if state["step"] == "mobile":
                    state["mobile"] = text
                    state["step"] = "address"
                    send_whatsapp_message(
                        from_number,
                        "📍 Please enter your *Pickup Address*:"
                    )
                    return "OK", 200

                if state["step"] == "address":
                    state["address"] = text

                    order_id = f"LDRY-{random.randint(1000, 9999)}"
                    time_now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

                    sheet.append_row([
                        order_id,
                        state["name"],
                        state["mobile"],
                        state["address"],
                        "Pending",
                        time_now
                    ])

                    send_whatsapp_message(
                        from_number,
                        f"✅ *Order Confirmed!*\n\n"
                        f"🆔 Order ID: *{order_id}*\n"
                        f"👤 Name: {state['name']}\n"
                        f"📞 Mobile: {state['mobile']}\n"
                        f"📍 Address: {state['address']}\n\n"
                        f"🧺 Our team will contact you shortly."
                    )

                    del user_states[from_number]
                    return "OK", 200

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200


# ==========================
# RENDER PORT
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
