"""
Pydantic schemas para o bridge server.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class MessageStatus(str, Enum):
    """Status de processamento da mensagem."""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class MessageSource(str, Enum):
    """Origem da mensagem."""
    HERMES = "hermes"
    LLM = "llm"
    MANUAL = "manual"


# ── Webhook (Evolution API → Bridge) ───────────────────────────────

class WebhookEvent(BaseModel):
    """Evento recebido do webhook da Evolution API."""
    event: str = Field(..., description="Tipo do evento")
    instance: str = Field(..., description="Nome da instância")
    data: Optional[Union[dict, list]] = Field(default=None, description="Dados do evento")
    sender: Optional[str] = Field(default=None, description="Remetente")
    timestamp: Optional[int] = Field(default=None, description="Timestamp do evento")


class IncomingMessage(BaseModel):
    """Mensagem extraída do evento do webhook."""
    message_id: str = Field(..., description="ID da mensagem")
    from_number: str = Field(..., description="Número do remetente")
    to_number: str = Field(..., description="Número do destinatário")
    content: str = Field(..., description="Conteúdo da mensagem")
    instance: str = Field(..., description="Instância Evolution")
    timestamp: datetime = Field(default_factory=datetime.now)
    message_type: str = Field(default="text", description="Tipo: text, image, etc.")
    caption: Optional[str] = Field(default=None, description="Legenda (para mídia)")
    media_url: Optional[Union[str, dict, None]] = Field(default=None, description="URL/chave da mídia")
    media_type: Optional[str] = Field(default=None, description="Tipo de mídia: audio, image, video")


# ── LLM ────────────────────────────────────────────────────────────

class LLMResponse(BaseModel):
    """Resposta processada pelo LLM."""
    content: str = Field(..., description="Resposta gerada")
    source: MessageSource = Field(default=MessageSource.LLM)
    model: Optional[str] = Field(default=None, description="Modelo utilizado")
    processing_time_ms: Optional[float] = Field(
        default=None, description="Tempo de processamento"
    )


# ── Send (Bridge → Evolution API) ──────────────────────────────────

class SendMessageRequest(BaseModel):
    """Request para enviar mensagem manualmente."""
    to_number: str = Field(..., description="Número do destinatário")
    message: str = Field(..., description="Conteúdo da mensagem")
    instance: Optional[str] = Field(
        default=None,
        description="Instância (usa default do .env se omitido)",
    )


class SendMessageResponse(BaseModel):
    """Response ao enviar mensagem."""
    success: bool = Field(..., description="Se enviou com sucesso")
    message_id: Optional[str] = Field(default=None, description="ID da mensagem enviada")
    error: Optional[str] = Field(default=None, description="Erro, se houver")


# ── Health ──────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    service: str = Field(default="bcomm-whatsapp-bridge")
    evolution_api: str = Field(default="unknown", description="Status da Evolution API")
    version: str = Field(default="1.0.0")
    uptime_seconds: Optional[float] = Field(default=None)
