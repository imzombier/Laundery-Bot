from flask import Flask, request
import requests, os, random
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ==========================
# ENV VARIABLES
# ==========================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

ADMIN_NUMBER = "919705996618"  # Change this

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
# USER SESSION
# ==========================
user_states = {}

# ==========================
# HELPER FUNCTIONS
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


def get_next_3_days():
    days = []
    today = datetime.now()
    for i in range(1, 4):
        day = today + timedelta(days=i)
        days.append(day.strftime("%Y-%m-%d"))
    return days


def generate_order_id():
    today = datetime.now().strftime("%Y%m%d")
    records = sheet.get_all_values()
    count = len([r for r in records if r and r[0].startswith(today)]) + 1
    return f"{today}{str(count).zfill(3)}"


# ==========================
# VERIFY WEBHOOK
# ==========================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Verification failed", 403


# ==========================
# WEBHOOK RECEIVER
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

        # ---------------------
        # BUTTON HANDLING
        # ---------------------
        if message.get("type") == "interactive":
            button_id = message["interactive"]["button_reply"]["id"]

            if button_id == "slots":
                dates = get_next_3_days()

                buttons = [
                    {"type": "reply", "reply": {"id": f"date_{dates[0]}", "title": dates[0]}},
                    {"type": "reply", "reply": {"id": f"date_{dates[1]}", "title": dates[1]}},
                    {"type": "reply", "reply": {"id": f"date_{dates[2]}", "title": dates[2]}}
                ]

                send_whatsapp_message(
                    from_number,
                    "📅 *Choose Pickup Date*",
                    buttons
                )

            elif button_id.startswith("date_"):
                selected_date = button_id.replace("date_", "")

                user_states[from_number] = {
                    "step": "name",
                    "date": selected_date
                }

                send_whatsapp_message(
                    from_number,
                    f"📅 Selected Date: *{selected_date}*\n\n👤 Enter your *Full Name*:"
                )

            return "OK", 200

        # ---------------------
        # TEXT HANDLING
        # ---------------------
        if message.get("type") == "text":
            text = message["text"]["body"].strip().lower()

            if text in ["hi", "hello", "hai", "hey"]:
                buttons = [
                    {"type": "reply", "reply": {"id": "slots", "title": "📅 Choose Date"}},
                ]

                send_whatsapp_message(
                    from_number,
                    "👋 *Welcome to Laundry Service!*\n\nChoose pickup date 👇",
                    buttons
                )
                return "OK", 200

            if from_number in user_states:
                state = user_states[from_number]

                if state["step"] == "name":
                    state["name"] = text.title()
                    state["step"] = "mobile"
                    send_whatsapp_message(from_number, "📞 Enter your *Mobile Number*:")
                    return "OK", 200

                if state["step"] == "mobile":
                    state["mobile"] = text
                    state["step"] = "address"
                    send_whatsapp_message(from_number, "📍 Enter *Pickup Address*:")
                    return "OK", 200

                if state["step"] == "address":
                    state["address"] = text

                    order_id = generate_order_id()
                    time_now = datetime.now().strftime("%d-%m-%Y %H:%M")

                    sheet.append_row([
                        order_id,
                        state["date"],
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
                        f"📅 Date: {state['date']}\n"
                        f"👤 Name: {state['name']}\n"
                        f"📞 Mobile: {state['mobile']}\n"
                        f"📍 Address: {state['address']}"
                    )

                    # ADMIN NOTIFICATION
                    send_whatsapp_message(
                        ADMIN_NUMBER,
                        f"🆕 *New Laundry Order*\n\n"
                        f"🆔 {order_id}\n"
                        f"📅 {state['date']}\n"
                        f"👤 {state['name']}\n"
                        f"📞 {state['mobile']}\n"
                        f"📍 {state['address']}"
                    )

                    del user_states[from_number]
                    return "OK", 200

    except Exception as e:
        print("ERROR:", e)

    return "OK", 200


# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
