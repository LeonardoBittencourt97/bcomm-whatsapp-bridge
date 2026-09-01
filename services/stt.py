"""
Serviço de Speech-to-Text usando OpenAI Whisper API (compatível).
Transcreve áudio baixado da Evolution API em texto.
"""
import io
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class STTClient:
    """Wrapper para transcrição de áudio via API Whisper-compatible."""

    def __init__(self):
        self.api_url = settings.stt_api_url.rstrip("/")
        self.api_key = settings.stt_api_key or settings.opencode_api_key
        self.model = settings.stt_model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers=headers,
                timeout=120.0,
            )
        return self._client

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.ogg",
        language: Optional[str] = None,
    ) -> Optional[str]:
        """
        Transcreve áudio usando a API Whisper.

        Args:
            audio_bytes: Dados do áudio em bytes
            filename: Nome do arquivo (necessário para multipart)
            language: Código do idioma (ex: "pt", "en"). None = auto-detect.

        Returns:
            Texto transcrito ou None em caso de erro
        """
        client = await self._get_client()

        # Determinar content-type baseado na extensão
        content_type_map = {
            ".ogg": "audio/ogg",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".opus": "audio/opus",
            ".oga": "audio/ogg",
        }
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".ogg"
        content_type = content_type_map.get(ext, "audio/ogg")

        # Montar multipart form
        files = {"file": (filename, io.BytesIO(audio_bytes), content_type)}
        data = {"model": self.model}
        if language:
            data["language"] = language

        logger.info(
            f"Transcrevendo áudio: {filename} ({len(audio_bytes)} bytes, "
            f"model={self.model})"
        )

        try:
            resp = await client.post(
                "/audio/transcriptions",
                files=files,
                data=data,
            )
            resp.raise_for_status()
            result = resp.json()
            text = result.get("text", "").strip()
            logger.info(f"Transcrição concluída: {len(text)} caracteres")
            return text

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Erro HTTP na transcrição: {e.response.status_code} - "
                f"{e.response.text[:200]}"
            )
            return None
        except Exception as e:
            logger.error(f"Erro na transcrição: {e}")
            return None

    async def transcribe_from_url(
        self,
        audio_url: str,
        filename: str = "audio.ogg",
        language: Optional[str] = None,
    ) -> Optional[str]:
        """
        Baixa áudio de uma URL e transcreve.

        Args:
            audio_url: URL do áudio
            filename: Nome do arquivo
            language: Código do idioma (None = auto-detect)

        Returns:
            Texto transcrito ou None
        """
        try:
            # Baixar o áudio
            async with httpx.AsyncClient(timeout=60.0) as dl:
                resp = await dl.get(audio_url)
                resp.raise_for_status()
                audio_bytes = resp.content
        except Exception as e:
            logger.error(f"Erro ao baixar áudio de {audio_url}: {e}")
            return None

        return await self.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
        )

    async def health_check(self) -> bool:
        """Verifica se a API STT está acessível."""
        client = await self._get_client()
        try:
            # Usar endpoint /health se existir, senão assumir disponível
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            # Se o endpoint não existir, verificar com outro request
            try:
                resp = await client.get("/v1/audio/transcriptions")
                # 405 ou422 = servidor rodando (só não aceita GET)
                return resp.status_code in (200, 405, 422)
            except Exception:
                return False

    async def close(self):
        """Fecha o cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
