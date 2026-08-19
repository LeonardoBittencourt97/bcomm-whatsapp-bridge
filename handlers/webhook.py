"""
Handler de webhooks da Evolution API.
Extrai mensagens do payload e despacha para processamento.
"""
import base64
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

    # Evolution API aninha o conteúdo em message_data["message"]
    inner = message_data.get("message", {})

    # Ignorar mensagens enviadas por nós mesmos
    if key.get("fromMe", False):
        logger.debug("Ignorando mensagem enviada por nós")
        return None

    # Extrair conteúdo
    message_type = "text"
    content = ""
    caption = None
    media_url = None
    media_type = None

    # Check both top-level message_data and the nested "message" dict
    sources = [message_data, inner]
    for src in sources:
        if "conversation" in src:
            content = src["conversation"]
            break
        elif "extendedTextMessage" in src:
            content = src["extendedTextMessage"].get("text", "")
            break
        elif "imageMessage" in src:
            message_type = "image"
            media_type = "image"
            content = src["imageMessage"].get("caption", "[imagem]")
            caption = src["imageMessage"].get("caption")
            media_url = src["imageMessage"].get("mediaKey") or src["imageMessage"].get("url")
            break
        elif "audioMessage" in src:
            message_type = "audio"
            media_type = "audio"
            content = "[áudio]"
            # Armazenar mediaKey raw (dict binário) para descriptografia
            mk = src["audioMessage"].get("mediaKey")
            if isinstance(mk, dict):
                media_url = str(mk)  # Armazenar como string do dict
            elif isinstance(mk, str):
                media_url = mk
            else:
                media_url = src["audioMessage"].get("url")
            break
        elif "documentMessage" in src:
            message_type = "document"
            content = src["documentMessage"].get("fileName", "[documento]")
            break
    else:
        logger.warning(f"Tipo de mensagem não suportado: {list(message_data.keys())}")
        return None

    if not content:
        logger.warning("Mensagem vazia, ignorando")
        return None

    # Construir IncomingMessage
    remote_jid = key.get("remoteJid", "")
    from_number = remote_jid.replace("@s.whatsapp.net", "").replace("@lid", "")

    # Extrair CDN URL se disponível (para download de mídia encriptada)
    cdn_url = None
    if message_type == "audio":
        for src in sources:
            if "audioMessage" in src:
                cdn_url = src["audioMessage"].get("url")
                break

    msg = IncomingMessage(
        message_id=key.get("id", "unknown"),
        from_number=from_number,
        to_number=key.get("remoteJid", ""),
        content=content,
        instance=event.instance,
        message_type=message_type,
        caption=caption,
        media_url=media_url,
        media_type=media_type,
        media_cdn_url=cdn_url,
    )

    logger.info(
        f"Mensagem extraída: id={msg.message_id}, "
        f"from={msg.from_number}, type={msg.message_type}"
    )

    return msg
