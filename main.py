import os
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from firebase_client import get_subscribers, save_subscriber
from notifier import notify_all
from scraper import scrape_and_summarize


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

scheduler = BackgroundScheduler()


def run_scraper_job():
    print(f"[scheduler] Running scraper at {datetime.utcnow().isoformat()}")
    try:
        new_circulars = scrape_and_summarize()
        if new_circulars:
            subscribers = get_subscribers()
            for circular in new_circulars:
                notify_all(subscribers, circular)
    except Exception as e:
        print(f"[scheduler] Error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    interval_minutes = int(os.environ.get("SCRAPE_INTERVAL_MINUTES", "30"))
    scheduler.add_job(run_scraper_job, "interval", minutes=interval_minutes)
    scheduler.start()
    print(f"[scheduler] Started — scraping every {interval_minutes} min.")
    yield
    scheduler.shutdown()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="RBI Regulatory Alerts", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SubscribeRequest(BaseModel):
    name: str
    whatsapp: str  # e.g. +919876543210


@app.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    # Basic validation
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not req.whatsapp.strip().startswith("+"):
        raise HTTPException(
            status_code=400,
            detail="WhatsApp number must include country code, e.g. +919876543210",
        )

    save_subscriber({
        "name": req.name.strip(),
        "whatsapp": req.whatsapp.strip(),
        "created_at": datetime.utcnow().isoformat(),
    })
    return {"status": "subscribed", "message": f"Welcome, {req.name}!"}


@app.post("/trigger")
async def trigger_scraper():
    """Manually trigger a scrape — useful for testing."""
    try:
        new_circulars = scrape_and_summarize()
        if new_circulars:
            subscribers = get_subscribers()
            for circular in new_circulars:
                notify_all(subscribers, circular)
        return {
            "status": "ok",
            "new_circulars": len(new_circulars),
            "titles": [c["title"] for c in new_circulars],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
