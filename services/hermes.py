"""
Cliente para o Hermes CLI via Docker exec.
Usa sessões nativas do Hermes para memória de conversação.
"""
import asyncio
import json
import logging
import os
from typing import Optional, Dict

from config import settings

logger = logging.getLogger(__name__)

HERMES_CONTAINER = os.getenv("HERMES_CONTAINER", "hermes-vtj5nm6l778wrezwf46uevmj")
SESSION_FILE = "/app/data/hermes_sessions.json"


def _load_sessions() -> Dict[str, str]:
    """Carrega session IDs do disco."""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sessions(sessions: Dict[str, str]):
    """Salva session IDs no disco."""
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions, f)


class HermesClient:
    """Wrapper para o Hermes CLI via Docker exec com sessões nativas."""

    def __init__(self):
        self.profile = settings.hermes_profile
        self.sessions = _load_sessions()

    async def chat(self, message: str, phone: str = "unknown", timeout: int = 120, force_new_session: bool = False) -> Optional[str]:
        """
        Envia mensagem ao Hermes. Se já existe sessão para o phone, retoma.
        Se force_new_session=True, ignora sessão anterior e cria nova.
        """
        cmd = ["docker", "exec", HERMES_CONTAINER, "/opt/hermes/.venv/bin/hermes", "chat"]

        session_id = None

        # Se force_new_session, limpar sessão anterior
        if force_new_session:
            old_session = self.sessions.pop(phone, None)
            if old_session:
                _save_sessions(self.sessions)
                logger.info(f"Sessão anterior {old_session} removida (force_new_session) para {phone}")
            logger.info(f"Forçando nova sessão para {phone} (outreach)")
        else:
            # Se já tem sessão, retomar
            session_id = self.sessions.get(phone)
            if session_id:
                cmd.extend(["--resume", session_id])
                logger.info(f"Retomando sessão {session_id} para {phone}")
            else:
                logger.info(f"Nova sessão para {phone}")

        cmd.extend([
            "--query", message,
            "--profile", self.profile,
            "--cli",
        ])

        logger.info(f"Hermes (phone={phone}): {message[:80]}...")
        await self._track_message(phone, "user", message)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                logger.error(f"Hermes erro (rc={proc.returncode}): {stderr.decode().strip()[:200]}")
                return None

            output = stdout.decode().strip()

            # Extrair session ID do output (última linha com "Session:")
            for line in reversed(output.split("\n")):
                if "Session:" in line:
                    new_session = line.split("Session:")[-1].strip()
                    if new_session != session_id:
                        self.sessions[phone] = new_session
                        _save_sessions(self.sessions)
                        logger.info(f"Nova sessão salva: {new_session} para {phone}")
                    break

            # Extrair resposta (entre markers)
            response = output
            if "╭─" in output and "╰─" in output:
                start = output.index("╭─")
                end = output.index("╰─") + len("╰─")
                response = output[start:end]
                for marker in [
                    "╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮",
                    "╰──────────────────────────────────────────────────────────────────────────────────╯",
                ]:
                    response = response.replace(marker, "")
                response = response.strip()
            # Limpar markers residuais
            response = response.replace("╰─", "").strip()

            logger.info(f"Hermes respondeu ({len(response)} chars)")
            await self._track_message(phone, "agent", response, model_used or "")
            return response

        except asyncio.TimeoutError:
            logger.error(f"Hermes timeout após {timeout}s")
            if proc:
                proc.kill()
            return None
        except Exception as e:
            logger.error(f"Erro Hermes: {e}")
            return None



    async def _track_message(self, phone: str, sender: str, content: str, model: str = ""):
        """Registra mensagem no CRM"""
        try:
            import httpx
            
            if sender == "user":
                endpoint = f"http://localhost:8000/crm/conversations/{phone}/receive"
            else:
                endpoint = f"http://localhost:8000/crm/conversations/{phone}/agent-response"
            
            async with httpx.AsyncClient() as client:
                await client.post(endpoint, json={"content": content}, params={"model": model})
        except Exception as e:
            logger.error(f"Erro ao rastrear mensagem: {e}")

    def get_active_sessions(self) -> list:
        """Retorna sessões ativas do arquivo de sessões."""
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r") as f:
                    sessions = json.load(f)
                return [
                    {"phone": phone, "session_id": session_id}
                    for phone, session_id in sessions.items()
                ]
        except Exception as e:
            logger.error(f"Erro ao ler sessões: {e}")
        return []

    async def is_available(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", HERMES_CONTAINER,
                "/opt/hermes/.venv/bin/hermes", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False
