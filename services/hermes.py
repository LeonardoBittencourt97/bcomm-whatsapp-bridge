"""
Cliente para o Hermes CLI.
Permite delegar processamento de mensagens ao Hermes Agent.
"""
import asyncio
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class HermesClient:
    """Wrapper assíncrono para o CLI do Hermes."""

    def __init__(self):
        self.profile = settings.hermes_profile

    async def chat(self, message: str, timeout: int = 120) -> Optional[str]:
        """
        Envia mensagem ao Hermes via CLI.

        Args:
            message: Texto da mensagem
            timeout: Timeout em segundos

        Returns:
            Resposta do Hermes ou None em caso de erro
        """
        cmd = [
            "hermes",
            "chat",
            "--message", message,
            "--profile", self.profile,
            "--output", "text",
        ]

        logger.info(f"Enviando ao Hermes (profile={self.profile}): {message[:80]}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error(f"Hermes CLI retornou erro (rc={proc.returncode}): {error_msg}")
                return None

            response = stdout.decode().strip()
            logger.info(f"Hermes respondeu ({len(response)} chars)")
            return response

        except asyncio.TimeoutError:
            logger.error(f"Hermes CLI timeout após {timeout}s")
            if proc:
                proc.kill()
            return None
        except FileNotFoundError:
            logger.error("Hermes CLI não encontrado no PATH")
            return None
        except Exception as e:
            logger.error(f"Erro ao executar Hermes CLI: {e}")
            return None

    async def is_available(self) -> bool:
        """Verifica se o Hermes CLI está disponível."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "hermes", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False
