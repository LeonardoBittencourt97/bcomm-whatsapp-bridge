"""
BComm WhatsApp Bridge
Bridge server FastAPI para conectar Evolution API ao Hermes Agent
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("🚀 BComm WhatsApp Bridge starting up...")
    logger.info(f"Evolution API URL: {os.getenv('EVOLUTION_API_URL', 'not set')}")
    logger.info(f"Hermes API URL: {os.getenv('HERMES_API_URL', 'not set')}")
    yield
    logger.info("👋 BComm WhatsApp Bridge shutting down...")


app = FastAPI(
    title="BComm WhatsApp Bridge",
    description="Bridge server para conectar Evolution API ao Hermes Agent",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "BComm WhatsApp Bridge",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check for monitoring."""
    return {"status": "healthy"}


@app.post("/webhook/evolution")
async def webhook_evolution(request: Request):
    """
    Webhook endpoint para receber mensagens da Evolution API.
    
    Processa mensagens recebidas via WhatsApp e encaminha para Hermes Agent.
    """
    try:
        body = await request.json()
        logger.info(f"📨 Webhook received: {body.get('event', 'unknown')}")
        
        event_type = body.get("event", "")
        
        # Process different event types
        if event_type == "messages.upsert":
            return await handle_message(body)
        elif event_type == "connection.update":
            return await handle_connection_update(body)
        else:
            logger.info(f"ℹ️ Ignoring event type: {event_type}")
            return JSONResponse(
                status_code=200,
                content={"status": "ignored", "event": event_type},
            )
    
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_message(body: dict) -> JSONResponse:
    """Process incoming WhatsApp messages."""
    data = body.get("data", {})
    message = data.get("message", {})
    key = data.get("key", {})
    
    # Extract message info
    sender = key.get("remoteJid", "")
    message_text = message.get("conversation") or message.get("extendedTextMessage", {}).get("text", "")
    
    logger.info(f"💬 Message from {sender}: {message_text[:50]}...")
    
    # TODO: Forward to Hermes Agent and get response
    # response = await hermes_client.process_message(sender, message_text)
    # await evolution_client.send_message(sender, response)
    
    return JSONResponse(
        status_code=200,
        content={"status": "received", "sender": sender},
    )


async def handle_connection_update(body: dict) -> JSONResponse:
    """Handle connection status updates."""
    state = body.get("data", {}).get("state", "unknown")
    logger.info(f"🔗 Connection state: {state}")
    
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "state": state},
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
    )
