import os
import json
from twilio.rest import Client as TwilioClient

twilio = TwilioClient(
    os.environ["TWILIO_ACCOUNT_SID"],
    os.environ["TWILIO_AUTH_TOKEN"],
)
WHATSAPP_FROM = os.environ["TWILIO_WHATSAPP_FROM"]  # whatsapp:+14155238886


def send_whatsapp(to_number: str, circular: dict):
    """Send WhatsApp notification via Twilio sandbox."""
    # Ensure number has whatsapp: prefix
    to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"

    try:
        message = twilio.messages.create(
            from_=WHATSAPP_FROM,
            to=to,
            content_sid="HX4c778e89d150316d1fad12ad0d9d453f",
            content_variables=json.dumps({
                "1": circular.get("summary", "Summary not available."),
                "2": circular["url"]
            }),
        )
        print(f"[notifier] WhatsApp sent to {to_number} — SID: {message.sid}")
    except Exception as e:
        print(f"[notifier] Failed to send WhatsApp to {to_number}: {e}")


def notify_all(subscribers: list[dict], circular: dict):
    """Send notifications to all subscribers."""
    for sub in subscribers:
        whatsapp = sub.get("whatsapp")
        if whatsapp:
            send_whatsapp(whatsapp, circular)
