"""
Processamento de mensagens recebidas.
Coordena LLM/Hermes e envio de respostas.
"""
import logging
import time
from typing import Optional

from config import settings
from models.schemas import IncomingMessage, LLMResponse, MessageSource
from services.evolution import EvolutionClient
from services.hermes import HermesClient
from services.llm import LLMClient
from services.stt import STTClient

logger = logging.getLogger(__name__)

# ── Rate Limiting (simples, por número) ─────────────────────────────

_rate_limits: dict[str, list[float]] = {}


def _check_rate_limit(phone: str) -> bool:
    """Verifica se o contato está dentro do rate limit."""
    now = time.time()
    window = 60.0  # 1 minuto

    if phone not in _rate_limits:
        _rate_limits[phone] = []

    # Limpar timestamps antigos
    _rate_limits[phone] = [t for t in _rate_limits[phone] if now - t < window]

    if len(_rate_limits[phone]) >= settings.rate_limit_per_minute:
        logger.warning(f"Rate limit atingido para {phone}")
        return False

    _rate_limits[phone].append(now)
    return True

# ── Prompts ─────────────────────────────────────────────────────────

def _load_prompt(name: str) -> str:
    """Carrega prompt de arquivo markdown."""
    prompt_path = f"prompts/{name}.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt não encontrado: {prompt_path}")
        return ""


# ── Fallback chain ──────────────────────────────────────────────────

async def _try_llm_with_fallback(
    llm: LLMClient,
    prompt: str,
    system_prompt: Optional[str],
) -> tuple[Optional[str], Optional[str], str]:
    """
    Tenta gerar resposta via LLM com cadeia de fallback.

    Returns:
        (response_content, model_used, source_label)
    """
    # 1. Tentar com configuração padrão
    result = await llm.generate(
        prompt=prompt,
        system_prompt=system_prompt or None,
    )
    if result:
        return result["content"], result["model"], "llm"

    logger.warning("LLM padrão falhou, tentando com temperatura baixa...")

    # 2. Tentar com temperatura mais baixa
    result = await llm.generate(
        prompt=prompt,
        system_prompt=system_prompt or None,
        temperature=0.2,
    )
    if result:
        return result["content"], result["model"], "llm_low_temp"

    logger.warning("LLM com temperatura baixa falhou, tentando prompt simplificado...")

    # 3. Tentar com prompt simplificado
    simplified = "Responda de forma breve e direta: " + prompt
    result = await llm.generate(
        prompt=simplified,
        system_prompt=None,
        temperature=0.3,
        max_tokens=512,
    )
    if result:
        return result["content"], result["model"], "llm_simplified"

    # 4. Fallback final — mensagem de ajuda
    fallback_msg = (
        "Desculpe, não consegui processar sua mensagem no momento. "
        "Nossa equipe foi notificada. "
        "Para contato direto, acesse: https://bcomm.com.br/contato"
    )
    return fallback_msg, None, "fallback"


# ── Audio transcription ─────────────────────────────────────────────

async def _transcribe_audio(
    message: IncomingMessage,
    evolution: EvolutionClient,
    stt: STTClient,
) -> Optional[str]:
    """
    Transcreve áudio de uma mensagem.

    Baixa áudio encriptado (.enc) do WhatsApp CDN,
    desencripta com mediaKey, depois envia para STT.

    Returns:
        Texto transcrito ou None
    """
    if not message.media_url:
        logger.warning("Mensagem de áudio sem media_url")
        return None

    logger.info(f"Transcrevendo áudio: media_url={str(message.media_url)[:80]}")

    audio_bytes = None

    # Se media_url parece URL HTTP, tentar download direto
    if isinstance(message.media_url, str) and message.media_url.startswith("http"):
        try:
            client = await evolution._get_client()
            resp = await client.get(message.media_url)
            resp.raise_for_status()
            audio_bytes = resp.content
            logger.info(f"Áudio baixado via URL: {len(audio_bytes)} bytes")
        except Exception as e:
            logger.warning(f"Falha ao baixar via URL: {e}")

    # Se media_url é dict string (mediaKey) e tem CDN URL, desencriptar
    if not audio_bytes and message.media_cdn_url:
        try:
            # Baixar arquivo encriptado do CDN
            client = await evolution._get_client()
            resp = await client.get(message.media_cdn_url)
            resp.raise_for_status()
            encrypted_data = resp.content
            logger.info(f"Áudio encriptado baixado: {len(encrypted_data)} bytes")

            # Extrair mediaKey do dict string
            import ast
            mk_dict = ast.literal_eval(message.media_url)
            media_key = bytes(mk_dict.values())

            # Desencriptar
            from services.whatsapp_crypto import decrypt_whatsapp_audio
            audio_bytes = decrypt_whatsapp_audio(encrypted_data, media_key)
            logger.info(f"Áudio desencriptado: {len(audio_bytes)} bytes")
        except Exception as e:
            logger.error(f"Erro ao desencriptar áudio: {e}")

    if audio_bytes:
        # Detectar formato pelo magic bytes
        filename = "audio.ogg"
        if audio_bytes[:4] == b"RIFF":
            filename = "audio.wav"
        elif audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
            filename = "audio.mp3"
        elif audio_bytes[:4] == b"fLaC":
            filename = "audio.flac"

        text = await stt.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
        )
        if text:
            return text

    logger.error("Falha ao transcrever áudio")
    return None


# ── Processamento ───────────────────────────────────────────────────

async def process_incoming_message(
    message: IncomingMessage,
    evolution: EvolutionClient,
    hermes: HermesClient,
    llm: LLMClient,
    stt: Optional[STTClient] = None,
    use_hermes: bool = False,
) -> LLMResponse:
    """
    Processa uma mensagem recebida e retorna resposta.

    Args:
        message: Mensagem recebida
        evolution: Cliente Evolution API
        hermes: Cliente Hermes CLI
        llm: Cliente LLM
        stt: Cliente STT (Speech-to-Text)
        use_hermes: Se True, usa Hermes CLI ao invés de LLM direto

    Returns:
        LLMResponse com a resposta gerada
    """
    start = time.monotonic()

    # Rate limit
    if not _check_rate_limit(message.from_number):
        return LLMResponse(
            content="Desculpe, você está enviando muitas mensagens. Por favor, aguarde um momento.",
            source=MessageSource.MANUAL,
        )

    logger.info(f"Processando mensagem de {message.from_number}: {message.content[:100]}...")

    # ── Transcrever áudio se necessário ──────────────────────────────
    content = message.content
    transcription_note = None

    if message.message_type == "audio" and message.media_url and stt:
        logger.info(f"Áudio detectado, transcrevendo... media_url={message.media_url}")
        transcribed = await _transcribe_audio(message, evolution, stt)

        if transcribed:
            content = transcribed
            transcription_note = transcribed
            logger.info(f"Áudio transcrito: {transcribed[:100]}...")
        else:
            content = "[Não foi possível transcrever o áudio]"
            logger.warning("Falha na transcrição do áudio")

    # Carregar prompt de sistema
    system_prompt = _load_prompt("atendimento")

    response_content = None
    source = MessageSource.LLM
    model_used = None

    # Tentar Hermes CLI primeiro (se habilitado)
    if use_hermes:
        hermes_response = await hermes.chat(
            f"Usuário WhatsApp {message.from_number} diz: {content}"
        )
        if hermes_response:
            response_content = hermes_response
            source = MessageSource.HERMES
        else:
            logger.warning("Hermes falhou, fallback para LLM")

    # Fallback: LLM direto com cadeia de fallback
    if response_content is None:
        response_content, model_used, source_label = await _try_llm_with_fallback(
            llm=llm,
            prompt=content,
            system_prompt=system_prompt,
        )
        if source_label == "fallback":
            source = MessageSource.MANUAL
        elif source_label == "llm_simplified":
            source = MessageSource.LLM
        else:
            source = MessageSource.LLM

    # Adicionar nota de transcrição se aplicável
    if transcription_note:
        response_content = f"(Áudio transcrito: {transcription_note})\n\n{response_content}"

    elapsed_ms = (time.monotonic() - start) * 1000

    # Enviar resposta via Evolution API
    send_result = await evolution.send_text(
        to_number=message.from_number,
        message=response_content,
    )

    if not send_result["success"]:
        logger.error(f"Falha ao enviar resposta: {send_result.get('error')}")

    logger.info(
        f"Mensagem processada em {elapsed_ms:.0f}ms "
        f"(source={source.value}, sent={send_result['success']})"
    )

    return LLMResponse(
        content=response_content,
        source=source,
        model=model_used,
        processing_time_ms=elapsed_ms,
    )
