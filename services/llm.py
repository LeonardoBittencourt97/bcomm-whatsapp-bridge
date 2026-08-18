"""
Cliente LLM via API compatível com OpenAI (OpenCode Go / vLLM / Ollama).
"""
import logging
import time
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper para chamadas LLM via API OpenAI-compatible."""

    def __init__(self):
        self.api_url = settings.opencode_api_url.rstrip("/")
        self.api_key = settings.opencode_api_key
        self.model = settings.opencode_model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers=headers,
                timeout=120.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Optional[dict]:
        """
        Gera resposta via LLM.

        Args:
            prompt: Mensagem do usuário
            system_prompt: Prompt de sistema (opcional)
            temperature: Temperatura de geração
            max_tokens: Máximo de tokens na resposta

        Returns:
            dict com content, model, processing_time_ms ou None
        """
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        start = time.monotonic()
        logger.info(f"Gerando resposta via LLM (model={self.model})")

        try:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            elapsed_ms = (time.monotonic() - start) * 1000

            content = data["choices"][0]["message"]["content"]
            model_used = data.get("model", self.model)

            logger.info(
                f"LLM respondeu em {elapsed_ms:.0f}ms "
                f"(model={model_used}, tokens={data.get('usage', {}).get('completion_tokens', '?')})"
            )

            return {
                "content": content,
                "model": model_used,
                "processing_time_ms": elapsed_ms,
                "usage": data.get("usage"),
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP LLM: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Erro LLM: {e}")
            return None

    async def health_check(self) -> bool:
        """Verifica se a API LLM está acessível."""
        client = await self._get_client()
        try:
            resp = await client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Fecha o cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
