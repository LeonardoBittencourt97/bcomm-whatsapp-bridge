"""
Cliente para o Hermes CLI.
Permite delegar processamento de mensagens ao Hermes Agent.
"""
import asyncio
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Caminho do Hermes CLI dentro do container (montado como read-only)
HERMES_CLI = "/opt/hermes/.venv/bin/hermes"


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
            HERMES_CLI,
            "chat",
            "--query", message,
            "--profile", self.profile,
            "--cli",
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

            # Extrair apenas a resposta do Hermes (remover markers)
            if "╭─" in response and "╰─" in response:
                start = response.index("╭─")
                end = response.index("╰─") + len("╰─")
                response = response[start:end]
                # Limpar markers
                response = response.replace("╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮", "")
                response = response.replace("╰──────────────────────────────────────────────────────────────────────────────────╯", "")
                response = response.strip()

            logger.info(f"Hermes respondeu ({len(response)} chars)")
            return response

        except asyncio.TimeoutError:
            logger.error(f"Hermes CLI timeout após {timeout}s")
            if proc:
                proc.kill()
            return None
        except FileNotFoundError:
            logger.error(f"Hermes CLI não encontrado: {HERMES_CLI}")
            return None
        except Exception as e:
            logger.error(f"Erro ao executar Hermes CLI: {e}")
            return None

    async def is_available(self) -> bool:
        """Verifica se o Hermes CLI está disponível."""
        try:
            proc = await asyncio.create_subprocess_exec(
                HERMES_CLI, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False
