"""
Testes do webhook handler.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from handlers.webhook import extract_message
from models.schemas import WebhookEvent, IncomingMessage


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def text_message_event() -> dict:
    """Evento simulado de mensagem de texto recebida."""
    return {
        "event": "messages.upsert",
        "instance": "bcomm-main",
        "data": {
            "key": {
                "id": "msg_123",
                "remoteJid": "5511999998888@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "conversation": "Olá, gostaria de agendar uma consulta",
            },
            "messageTimestamp": 1724000000,
        },
    }


@pytest.fixture
def text_message_event_extended() -> dict:
    """Evento com extendedTextMessage."""
    return {
        "event": "messages.upsert",
        "instance": "bcomm-main",
        "data": {
            "key": {
                "id": "msg_456",
                "remoteJid": "5511888887777@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "extendedTextMessage": {
                    "text": "Preciso de ajuda com meu pedido",
                },
            },
        },
    }


@pytest.fixture
def from_me_event() -> dict:
    """Evento de mensagem enviada por nós."""
    return {
        "event": "messages.upsert",
        "instance": "bcomm-main",
        "data": {
            "key": {
                "id": "msg_789",
                "remoteJid": "5511777776666@s.whatsapp.net",
                "fromMe": True,
            },
            "message": {
                "conversation": "Olá! Sua mensagem foi recebida.",
            },
        },
    }


@pytest.fixture
def non_message_event() -> dict:
    """Evento que não é mensagem."""
    return {
        "event": "connection.update",
        "instance": "bcomm-main",
        "data": {"state": "open"},
    }


# ── Testes ──────────────────────────────────────────────────────────

class TestExtractMessage:

    def test_extrai_mensagem_texto(self, text_message_event):
        event = WebhookEvent(**text_message_event)
        msg = extract_message(event)

        assert msg is not None
        assert msg.message_id == "msg_123"
        assert msg.from_number == "5511999998888"
        assert msg.content == "Olá, gostaria de agendar uma consulta"
        assert msg.instance == "bcomm-main"
        assert msg.message_type == "text"

    def test_extrai_mensagem_estendida(self, text_message_event_extended):
        event = WebhookEvent(**text_message_event_extended)
        msg = extract_message(event)

        assert msg is not None
        assert msg.from_number == "5511888887777"
        assert msg.content == "Preciso de ajuda com meu pedido"

    def test_ignora_mensagem_enviada(self, from_me_event):
        event = WebhookEvent(**from_me_event)
        msg = extract_message(event)

        assert msg is None

    def test_ignora_evento_nao_mensagem(self, non_message_event):
        event = WebhookEvent(**non_message_event)
        msg = extract_message(event)

        assert msg is None

    def test_evento_sem_dados(self):
        event = WebhookEvent(
            event="messages.upsert",
            instance="bcomm-main",
            data=None,
        )
        msg = extract_message(event)

        assert msg is None
