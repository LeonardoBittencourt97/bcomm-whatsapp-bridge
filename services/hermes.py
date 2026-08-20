"""
Cliente para o Hermes CLI via Docker exec.
Usa sessões nativas do Hermes para memória de conversação.
Suporta multi-tenant via profiles por cliente.
"""
import asyncio
import json
import logging
import os
from typing import Optional, Dict

from config import settings
from config.client_loader import get_hermes_profile

logger = logging.getLogger(__name__)

HERMES_CONTAINER = os.getenv("HERMES_CONTAINER", "hermes-vtj5nm6l778wrezwf46uevmj")
SESSION_FILE = "/app/data/hermes_sessions.json"


def _load_sessions() -> Dict[str, str]:
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sessions(sessions: Dict[str, str]):
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions, f)


class HermesClient:
    def __init__(self):
        self.sessions = _load_sessions()

    async def chat(self, message: str, phone: str = "unknown", instance_name: str = "BCOMM", timeout: int = 120) -> Optional[str]:
        profile = get_hermes_profile(instance_name)
        session_key = f"{instance_name}:{phone}"
        
        cmd = ["docker", "exec", HERMES_CONTAINER, "/opt/hermes/.venv/bin/hermes", "chat"]

        session_id = self.sessions.get(session_key)
        if session_id:
            cmd.extend(["--resume", session_id])
            logger.info(f"Retomando sessão {session_id} para {session_key}")
        else:
            logger.info(f"Nova sessão para {session_key}")

        cmd.extend(["--query", message, "--profile", profile, "--cli"])

        logger.info(f"Hermes (profile={profile}, phone={phone}): {message[:80]}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                logger.error(f"Hermes erro (rc={proc.returncode}): {stderr.decode().strip()[:200]}")
                return None

            output = stdout.decode().strip()

            for line in reversed(output.split("\n")):
                if "Session:" in line:
                    new_session = line.split("Session:")[-1].strip()
                    if new_session != session_id:
                        self.sessions[session_key] = new_session
                        _save_sessions(self.sessions)
                        logger.info(f"Nova sessão salva: {new_session} para {session_key}")
                    break

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
            response = response.replace("╰─", "").strip()

            logger.info(f"Hermes respondeu ({len(response)} chars)")
            return response

        except asyncio.TimeoutError:
            logger.error(f"Hermes timeout após {timeout}s")
            if proc:
                proc.kill()
            return None
        except Exception as e:
            logger.error(f"Erro Hermes: {e}")
            return None

    async def is_available(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", HERMES_CONTAINER, "/opt/hermes/.venv/bin/hermes", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False
