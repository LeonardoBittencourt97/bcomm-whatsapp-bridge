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


# ── Message Batching ───────────────────────────────────────────────
# Agrupa mensagens do mesmo usuário antes de processar

_message_batches: dict[str, list[IncomingMessage]] = {}
_batch_timers: dict[str, asyncio.Task] = {}
_batch_start: dict[str, float] = {}  # Timestamp do início do batch

BATCH_WAIT_SECONDS = 10.0  # Espera 10s por mensagens adicionais
BATCH_MAX_WAIT = 150.0  # Máximo 2,5 minutos de espera total


def _calculate_typing_delay(response_length: int) -> float:
    """
    Calcula delay de digitação baseado no tamanho da resposta.
    
    Humano digita entre 40-50 WPM.
    - 40 WPM = 240 chars/min = 4 chars/seg
    - 50 WPM = 300 chars/min = 5 chars/seg
    
    Tempo de reação: 0.5-2s
    Range realista: sem limite máximo artificial.
    """
    if response_length <= 0:
        return 2.0
    
    chars_per_sec_min = 4.0
    chars_per_sec_max = 5.0
    
    time_min = response_length / chars_per_sec_max
    time_max = response_length / chars_per_sec_min
    
    reaction_time = random.uniform(0.5, 2.0)
    delay = reaction_time + random.uniform(time_min, time_max)
    delay = max(4.0, delay)
    
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


# ── Typing indicator ───────────────────────────────────────────────

async def _send_typing_indicator(
    evolution: EvolutionClient,
    phone: str,
    duration: float,
):
    """
    Envia indicador "digitando..." de forma CONTÍNUA.
    
    Envia composição com delay de 2 segundos.
    A API WhatsApp mantém o indicador visível por ~3-5 segundos.
    Repete até atingir a duração desejada.
    """
    compose_duration = 2.0  # mantém composing por 2 segundos
    elapsed = 0.0
    
    logger.info(f"Indicador 'digitando...' ativo por {duration:.1f}s")
    
    while elapsed < duration:
        remaining = duration - elapsed
        chunk = min(compose_duration, remaining)
        
        # Enviar composição com delay para manter indicador visível
        await evolution.send_presence(phone, presence="composing", delay=int(chunk))
        elapsed += chunk
    
    logger.info(f"Indicador 'digitando...' finalizado")


# ── Processamento de batch ─────────────────────────────────────────

async def _process_batch(
    phone: str,
    messages: list[IncomingMessage],
    evolution: EvolutionClient,
    hermes: HermesClient,
    llm: LLMClient,
    stt: Optional[STTClient],
    use_hermes: bool,
):
    """Processa um batch de mensagens do mesmo usuário."""
    start = time.monotonic()
    
    # Concatenar todas as mensagens do batch
    combined_content = "\n".join([f"[Mensagem {i+1}] {m.content}" for i, m in enumerate(messages)])
    first_msg = messages[0]
    
    logger.info(f"Processando batch de {len(messages)} mensagens de {phone}: {combined_content[:100]}...")
    
    if not _check_rate_limit(phone):
        await evolution.send_text(
            to_number=phone,
            message="Desculpe, você está enviando muitas mensagens. Por favor, aguarde um momento.",
        )
        return

    # ── Transcrever áudio se necessário ──────────────────────────────
    content = combined_content
    transcription_note = None

    for msg in messages:
        if msg.message_type == "audio" and msg.media_url and stt:
            logger.info(f"Áudio detectado, transcrevendo... media_url={msg.media_url}")
            transcribed = await _transcribe_audio(msg, evolution, stt)
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
            f"Usuário WhatsApp {phone} diz: {content}", phone=phone
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

    # ── Delay humanizado com indicador "digitando..." ──────────────
    if settings.human_delay_enabled and response_content:
        typing_delay = _calculate_typing_delay(len(response_content))
        
        # Subtrair o tempo já gasto no processamento
        elapsed_so_far = time.monotonic() - start
        remaining_delay = max(0.0, typing_delay - elapsed_so_far)
        
        if remaining_delay > 0:
            logger.info(
                f"Tempo total estimado: {typing_delay:.1f}s, "
                f"processamento: {elapsed_so_far:.1f}s, "
                f"aguardando mais: {remaining_delay:.1f}s"
            )
            await _send_typing_indicator(evolution, phone, remaining_delay)
        else:
            logger.info(
                f"Processamento ({elapsed_so_far:.1f}s) já excedeu "
                f"tempo estimado ({typing_delay:.1f}s), enviando resposta"
            )

    elapsed_ms = (time.monotonic() - start) * 1000

    # Enviar resposta via Evolution API
    send_result = await evolution.send_text(
        to_number=phone, message=response_content,
    )

    if not send_result["success"]:
        logger.error(f"Falha ao enviar resposta: {send_result.get('error')}")

    logger.info(f"Mensagem processada em {elapsed_ms:.0f}ms (source={source.value}, sent={send_result['success']})")


# ── Interface pública ──────────────────────────────────────────────

async def process_incoming_message(
    message: IncomingMessage,
    evolution: EvolutionClient,
    hermes: HermesClient,
    llm: LLMClient,
    stt: Optional[STTClient] = None,
    use_hermes: bool = False,
) -> LLMResponse:
    """
    Interface pública: adiciona mensagem ao batch e agenda processamento.
    
    Lógica:
    - Espera BATCH_WAIT_SECONDS (10s) por mensagens adicionais
    - Se outra mensagem chegar, reseta o timer
    - Se tempo total exceder BATCH_MAX_WAIT (2,5min), processa imediatamente
    """
    phone = message.from_number
    now = time.monotonic()
    
    # Adicionar ao batch
    if phone not in _message_batches:
        _message_batches[phone] = []
        _batch_start[phone] = now
    _message_batches[phone].append(message)
    
    # Cancelar timer anterior se existir
    if phone in _batch_timers and not _batch_timers[phone].done():
        _batch_timers[phone].cancel()
    
    # Calcular tempo restante antes do limite máximo
    elapsed_total = now - _batch_start[phone]
    remaining_max = BATCH_MAX_WAIT - elapsed_total
    
    if remaining_max <= 0:
        # Já excedeu o tempo máximo — processar imediatamente
        logger.info(f"Tempo máximo atingido ({BATCH_MAX_WAIT}s), processando batch")
        batch = _message_batches.pop(phone, [])
        _batch_start.pop(phone, None)
        if batch:
            asyncio.create_task(_process_batch(
                phone=phone,
                messages=batch,
                evolution=evolution,
                hermes=hermes,
                llm=llm,
                stt=stt,
                use_hermes=use_hermes,
            ))
        return LLMResponse(content="", source=MessageSource.MANUAL, processing_time_ms=0)
    
    # Calcular tempo de espera (mínimo entre batch_wait e tempo restante)
    wait_time = min(BATCH_WAIT_SECONDS, remaining_max)
    
    # Criar novo timer
    async def _process_after_delay():
        await asyncio.sleep(wait_time)
        
        # Pegar todas as mensagens acumuladas
        batch = _message_batches.pop(phone, [])
        _batch_start.pop(phone, None)
        _batch_timers.pop(phone, None)
        
        if batch:
            logger.info(f"Processando batch de {len(batch)} mensagens de {phone}")
            await _process_batch(
                phone=phone,
                messages=batch,
                evolution=evolution,
                hermes=hermes,
                llm=llm,
                stt=stt,
                use_hermes=use_hermes,
            )
    
    _batch_timers[phone] = asyncio.create_task(_process_after_delay())
    
    logger.debug(
        f"Mensagem adicionada ao batch de {phone} "
        f"({len(_message_batches[phone])} msgs, "
        f"esperando {wait_time:.0f}s, "
        f"restam {remaining_max:.0f}s até máximo)"
    )
    
    # Retornar resposta imediata (o processamento real acontece depois)
    return LLMResponse(
        content="",
        source=MessageSource.MANUAL,
        processing_time_ms=0,
    )
