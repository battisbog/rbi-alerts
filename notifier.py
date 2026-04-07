import os
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

    body = (
        f"RBI REGULATORY ALERT\n\n"
        f"{circular.get('summary', 'Summary not available. Please read the circular directly.')}\n\n"
        f"Read full circular: {circular['url']}"
    )

    try:
        message = twilio.messages.create(
            from_=WHATSAPP_FROM,
            to=to,
            body=body,
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
