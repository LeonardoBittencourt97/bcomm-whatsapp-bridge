"""
Cliente HTTP para a Evolution API.
Responsável por enviar mensagens via WhatsApp.
"""
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class EvolutionClient:
    """Wrapper para a Evolution API REST."""

    def __init__(self):
        self.base_url = settings.evolution_api_url.rstrip("/")
        self.api_key = settings.evolution_api_key
        self.default_instance = settings.evolution_instance
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def send_text(
        self,
        to_number: str,
        message: str,
        instance: Optional[str] = None,
    ) -> dict:
        """
        Envia mensagem de texto via Evolution API.

        Args:
            to_number: Número do destinatário (formato: 5511999999999)
            message: Texto da mensagem
            instance: Nome da instância (usa default se omitido)

        Returns:
            dict com resultado do envio
        """
        inst = instance or self.default_instance
        client = await self._get_client()

        payload = {
            "number": to_number,
            "text": message,
        }

        url = f"/message/sendText/{inst}"
        logger.info(f"Enviando mensagem para {to_number} via instância {inst}")

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Mensagem enviada com sucesso: {data.get('key', {}).get('id')}")
            return {
                "success": True,
                "message_id": data.get("key", {}).get("id"),
                "data": data,
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao enviar mensagem: {e.response.status_code} - {e.response.text}")
            return {"success": False, "error": str(e), "status_code": e.response.status_code}
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return {"success": False, "error": str(e)}

    async def download_media(
        self,
        media_key: str,
        instance: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Baixa mídia (áudio/imagem) via Evolution API.

        Args:
            media_key: Chave da mídia (mediaKey da mensagem)
            instance: Nome da instância (usa default se omitido)

        Returns:
            Bytes do arquivo ou None em caso de erro
        """
        inst = instance or self.default_instance
        client = await self._get_client()
        url = f"/chat/downloadMedia/{inst}/{media_key}"

        logger.info(f"Baixando mídia: mediaKey={media_key}")

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            logger.info(f"Mídia baixada: {len(resp.content)} bytes")
            return resp.content
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Erro HTTP ao baixar mídia: {e.response.status_code} - "
                f"{e.response.text[:200]}"
            )
            return None
        except Exception as e:
            logger.error(f"Erro ao baixar mídia: {e}")
            return None

    async def health_check(self) -> bool:
        """Verifica se a Evolution API está acessível."""
        client = await self._get_client()
        try:
            resp = await client.get(f"/instance/fetchInstances")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Health check Evolution API falhou: {e}")
            return False

    async def close(self):
        """Fecha o cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
