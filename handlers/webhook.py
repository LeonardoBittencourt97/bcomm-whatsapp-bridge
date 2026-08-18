"""
Handler de webhooks da Evolution API.
Extrai mensagens do payload e despacha para processamento.
"""
import logging
from typing import Optional

from models.schemas import WebhookEvent, IncomingMessage

logger = logging.getLogger(__name__)


def extract_message(event: WebhookEvent) -> Optional[IncomingMessage]:
    """
    Extrai mensagem de texto do evento do webhook.

    A Evolution API envia diferentes formatos dependendo do evento.
    Este handler foca em 'messages.upsert' (mensagens recebidas).
    """
    if event.event != "messages.upsert":
        logger.debug(f"Ignorando evento: {event.event}")
        return None

    if not event.data:
        logger.warning(f"Evento {event.event} sem dados")
        return None

    data = event.data

    # Mensagem pode estar aninhada em 'data' ou direto no payload
    message_data = data.get("data", data)
    key = data.get("key", message_data.get("key", {}))

    # Ignorar mensagens enviadas por nós mesmos
    if key.get("fromMe", False):
        logger.debug("Ignorando mensagem enviada por nós")
        return None

    # Extrair conteúdo
    message_type = "text"
    content = ""
    caption = None

    if "conversation" in message_data:
        content = message_data["conversation"]
    elif "extendedTextMessage" in message_data:
        content = message_data["extendedTextMessage"].get("text", "")
    elif "imageMessage" in message_data:
        message_type = "image"
        content = message_data["imageMessage"].get("caption", "[imagem]")
        caption = message_data["imageMessage"].get("caption")
    elif "audioMessage" in message_data:
        message_type = "audio"
        content = "[áudio]"
    elif "documentMessage" in message_data:
        message_type = "document"
        content = message_data["documentMessage"].get("fileName", "[documento]")
    else:
        logger.warning(f"Tipo de mensagem não suportado: {list(message_data.keys())}")
        return None

    if not content:
        logger.warning("Mensagem vazia, ignorando")
        return None

    # Construir IncomingMessage
    remote_jid = key.get("remoteJid", "")
    from_number = remote_jid.replace("@s.whatsapp.net", "").replace("@lid", "")

    msg = IncomingMessage(
        message_id=key.get("id", "unknown"),
        from_number=from_number,
        to_number=key.get("remoteJid", ""),
        content=content,
        instance=event.instance,
        message_type=message_type,
        caption=caption,
    )

    logger.info(
        f"Mensagem extraída: id={msg.message_id}, "
        f"from={msg.from_number}, type={msg.message_type}"
    )

    return msg
