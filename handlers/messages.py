"""
Processamento de mensagens recebidas.
Coordena LLM/Hermes e envio de respostas.
"""
import asyncio
import logging
import random
import time
from typing import Optional

from config import settings
from models.schemas import IncomingMessage, LLMResponse, MessageSource
from services.evolution import EvolutionClient
from services.hermes import HermesClient
from services.llm import LLMClient
from services.stt import STTClient

logger = logging.getLogger(__name__)

# ── Rate Limiting ──────────────────────────────────────────────────

_rate_limits: dict[str, list[float]] = {}


def _check_rate_limit(phone: str) -> bool:
    now = time.time()
    window = 60.0
    if phone not in _rate_limits:
        _rate_limits[phone] = []
    _rate_limits[phone] = [t for t in _rate_limits[phone] if now - t < window]
    if len(_rate_limits[phone]) >= settings.rate_limit_per_minute:
        logger.warning(f"Rate limit atingido para {phone}")
        return False
    _rate_limits[phone].append(now)
    return True


def _calculate_typing_delay(response_length: int) -> float:
    """
    Calcula delay de digitação baseado no tamanho da resposta.
    
    Humano digita entre 40-50 WPM (palavras por minuto).
    Média de 5 caracteres por palavra + espaço = 6 chars/palavra.
    
    - 40 WPM = 240 chars/min = 4 chars/seg (digitação lenta)
    - 50 WPM = 300 chars/min = 5 chars/seg (digitação rápida)
    
    Retorna delay entre 4-10 segundos para mensagens curtas.
    """
    if response_length <= 0:
        return 2.0
    
    # Caracteres por segundo (4-5 chars/seg)
    chars_per_sec_min = 4.0  # digitação lenta
    chars_per_sec_max = 5.0  # digitação rápida
    
    # Calcular tempo baseado no tamanho
    time_min = response_length / chars_per_sec_max  # tempo mais rápido
    time_max = response_length / chars_per_sec_min  # tempo mais lento
    
    # Adicionar tempo de reação (0.5-1.5s)
    reaction_time = random.uniform(0.5, 1.5)
    
    # Delay final com variação aleatória
    delay = reaction_time + random.uniform(time_min, time_max)
    
    # Limitar entre 4-10 segundos para mensagens curtas
    # Para mensagens longas, pode ser mais
    delay = max(4.0, min(delay, 15.0))
    
    return round(delay, 1)


# ── Prompts ─────────────────────────────────────────────────────────

def _load_prompt(name: str) -> str:
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
    result = await llm.generate(prompt=prompt, system_prompt=system_prompt or None)
    if result:
        return result["content"], result["model"], "llm"

    logger.warning("LLM padrão falhou, tentando com temperatura baixa...")
    result = await llm.generate(prompt=prompt, system_prompt=system_prompt or None, temperature=0.2)
    if result:
        return result["content"], result["model"], "llm_low_temp"

    logger.warning("LLM com temperatura baixa falhou, tentando prompt simplificado...")
    simplified = "Responda de forma breve e direta: " + prompt
    result = await llm.generate(prompt=simplified, system_prompt=None, temperature=0.3, max_tokens=512)
    if result:
        return result["content"], result["model"], "llm_simplified"

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
    if not message.media_url:
        logger.warning("Mensagem de áudio sem media_url")
        return None

    logger.info(f"Transcrevendo áudio: media_url={str(message.media_url)[:80]}")

    audio_bytes = None

    if isinstance(message.media_url, str) and message.media_url.startswith("http"):
        try:
            client = await evolution._get_client()
            resp = await client.get(message.media_url)
            resp.raise_for_status()
            audio_bytes = resp.content
            logger.info(f"Áudio baixado via URL: {len(audio_bytes)} bytes")
        except Exception as e:
            logger.warning(f"Falha ao baixar via URL: {e}")

    if not audio_bytes and message.media_cdn_url:
        try:
            client = await evolution._get_client()
            resp = await client.get(message.media_cdn_url)
            resp.raise_for_status()
            encrypted_data = resp.content
            logger.info(f"Áudio encriptado baixado: {len(encrypted_data)} bytes")

            import ast
            mk_dict = ast.literal_eval(message.media_url)
            media_key = bytes(mk_dict.values())

            from services.whatsapp_crypto import decrypt_whatsapp_audio
            audio_bytes = decrypt_whatsapp_audio(encrypted_data, media_key)
            logger.info(f"Áudio desencriptado: {len(audio_bytes)} bytes, magic: {audio_bytes[:4]}")
        except Exception as e:
            logger.error(f"Erro ao desencriptar áudio: {type(e).__name__}: {e}")

    if audio_bytes:
        filename = "audio.ogg"
        if audio_bytes[:4] == b"RIFF":
            filename = "audio.wav"
        elif audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
            filename = "audio.mp3"
        elif audio_bytes[:4] == b"fLaC":
            filename = "audio.flac"

        text = await stt.transcribe(audio_bytes=audio_bytes, filename=filename)
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
    start = time.monotonic()

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
            f"Usuário WhatsApp {message.from_number} diz: {content}", phone=message.from_number
        )
        if hermes_response:
            response_content = hermes_response
            source = MessageSource.HERMES
        else:
            logger.warning("Hermes falhou, fallback para LLM")

    # Fallback: LLM direto com cadeia de fallback
    if response_content is None:
        response_content, model_used, source_label = await _try_llm_with_fallback(
            llm=llm, prompt=content, system_prompt=system_prompt,
        )
        if source_label == "fallback":
            source = MessageSource.MANUAL
        else:
            source = MessageSource.LLM

    # ── Calcular delay de digitação baseado no tamanho da resposta ──
    if settings.human_delay_enabled and response_content:
        typing_delay = _calculate_typing_delay(len(response_content))
        
        # Enviar indicador "digitando..." com duração calculada
        logger.info(f"Enviando indicador 'digitando...' por {typing_delay}s (resposta: {len(response_content)} chars)")
        await evolution.send_presence(
            message.from_number, 
            presence="composing", 
            delay=int(typing_delay)
        )
        
        # Aguardar o tempo de digitação
        await asyncio.sleep(typing_delay)

    elapsed_ms = (time.monotonic() - start) * 1000

    # Enviar resposta via Evolution API
    send_result = await evolution.send_text(
        to_number=message.from_number, message=response_content,
    )

    if not send_result["success"]:
        logger.error(f"Falha ao enviar resposta: {send_result.get('error')}")

    logger.info(f"Mensagem processada em {elapsed_ms:.0f}ms (source={source.value}, sent={send_result['success']})")

    return LLMResponse(
        content=response_content, source=source, model=model_used, processing_time_ms=elapsed_ms,
    )
