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


# ── Processamento ───────────────────────────────────────────────────

async def process_incoming_message(
    message: IncomingMessage,
    evolution: EvolutionClient,
    hermes: HermesClient,
    llm: LLMClient,
    use_hermes: bool = False,
) -> LLMResponse:
    """
    Processa uma mensagem recebida e retorna resposta.

    Args:
        message: Mensagem recebida
        evolution: Cliente Evolution API
        hermes: Cliente Hermes CLI
        llm: Cliente LLM
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

    # Carregar prompt de sistema
    system_prompt = _load_prompt("atendimento")

    response_content = None
    source = MessageSource.LLM
    model_used = None

    # Tentar Hermes CLI primeiro (se habilitado)
    if use_hermes:
        hermes_response = await hermes.chat(
            f"Usuário WhatsApp {message.from_number} diz: {message.content}"
        )
        if hermes_response:
            response_content = hermes_response
            source = MessageSource.HERMES
        else:
            logger.warning("Hermes falhou, fallback para LLM")

    # Fallback: LLM direto
    if response_content is None:
        llm_result = await llm.generate(
            prompt=message.content,
            system_prompt=system_prompt or None,
        )
        if llm_result:
            response_content = llm_result["content"]
            model_used = llm_result["model"]
        else:
            response_content = "Desculpe, não consegui processar sua mensagem no momento. Tente novamente mais tarde."
            source = MessageSource.MANUAL

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
