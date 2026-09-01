"""
Cliente para o Hermes CLI via Docker exec.
Usa sessões nativas do Hermes para memória de conversação.
Sessões persistidas via Supabase (tabela bcomm_inbox.sessions).
"""
import asyncio
import logging
import os
from typing import Optional, Dict, List

from config import settings
from services.database import get_supabase, select, insert, update, delete

logger = logging.getLogger(__name__)

HERMES_CONTAINER = os.getenv("HERMES_CONTAINER", "bridge-q6o907l7ab6zbjvh4dvwuop6-213407219925")
SESSIONS_TABLE = "bcomm_inbox.sessions"


def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    from services.database import ensure_supabase as _es
    _es()


async def _load_sessions() -> Dict[str, str]:
    """Carrega session IDs do Supabase."""
    _ensure_supabase()
    try:
        rows = await select(
            SESSIONS_TABLE,
            columns="phone,session_id",
        )
        return {row["phone"]: row["session_id"] for row in rows}
    except Exception as e:
        logger.error(f"Erro ao carregar sessões do Supabase: {e}")
        return {}


async def _save_session(phone: str, session_id: str, client_name: str = "BCOMM"):
    """Salva/atualiza uma sessão no Supabase."""
    _ensure_supabase()
    try:
        # Check if session exists, then insert or update
        existing = await select(SESSIONS_TABLE, filters={"phone": phone})
        if existing:
            await update(SESSIONS_TABLE, {
                "session_id": session_id,
                "client_name": client_name,
            }, filters={"phone": phone})
        else:
            await insert(SESSIONS_TABLE, {
                "phone": phone,
                "session_id": session_id,
                "client_name": client_name,
            })
        logger.info(f"Sessão salva no Supabase: {phone} -> {session_id}")
    except Exception as e:
        logger.error(f"Erro ao salvar sessão no Supabase: {e}")


async def _delete_session(phone: str):
    """Remove uma sessão do Supabase."""
    _ensure_supabase()
    try:
        await delete(SESSIONS_TABLE, filters={"phone": phone})
        logger.info(f"Sessão removida do Supabase: {phone}")
    except Exception as e:
        logger.error(f"Erro ao remover sessão do Supabase: {e}")


class HermesClient:
    """Wrapper para o Hermes CLI via Docker exec com sessões nativas."""

    def __init__(self):
        self.profile = settings.hermes_profile
        self._sessions_cache: Optional[Dict[str, str]] = None
        self._processing_status: Dict[str, dict] = {}  # phone -> {status, started_at}

    async def _get_sessions(self) -> Dict[str, str]:
        """Retorna sessões (com cache lazy)."""
        if self._sessions_cache is None:
            self._sessions_cache = await _load_sessions()
        return self._sessions_cache

    async def chat(self, message: str, phone: str = "unknown", timeout: int = 120, force_new_session: bool = False, message_id: str = "", skip_user_tracking: bool = False) -> Optional[str]:
        """
        Envia mensagem ao Hermes. Se já existe sessão para o phone, retoma.
        Se force_new_session=True, ignora sessão anterior e cria nova.
        """
        cmd = ["docker", "exec", HERMES_CONTAINER, "/opt/hermes/.venv/bin/hermes", "chat"]

        sessions = await self._get_sessions()
        session_id = None

        # Se force_new_session, limpar sessão anterior
        if force_new_session:
            old_session = sessions.pop(phone, None)
            if old_session:
                await _delete_session(phone)
                logger.info(f"Sessão anterior {old_session} removida (force_new_session) para {phone}")
            logger.info(f"Forçando nova sessão para {phone}")
        else:
            # Se já tem sessão, retomar
            session_id = sessions.get(phone)
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
        self._processing_status[phone] = {"status": "processing", "started_at": __import__("time").time()}

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
                        sessions[phone] = new_session
                        await _save_session(phone, new_session)
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
            self._processing_status.pop(phone, None)
            return response

        except asyncio.TimeoutError:
            logger.error(f"Hermes timeout após {timeout}s")
            self._processing_status.pop(phone, None)
            if proc:
                proc.kill()
            return None
        except Exception as e:
            logger.error(f"Erro Hermes: {e}")
            self._processing_status.pop(phone, None)
            return None

    async def _track_message(self, phone: str, sender: str, content: str, model: str = "", message_id: str = ""):
        """Registra mensagem no CRM diretamente no Supabase (sem HTTP loop)."""
        try:
            from services.database import select as _select, insert as _insert, update as _update

            _ensure_supabase()

            # Buscar ou criar conversa
            conv_rows = await _select("bcomm_inbox.conversations", filters={"phone": phone})
            if conv_rows:
                conv_id = conv_rows[0]["id"]
            else:
                now = __import__("datetime").datetime.utcnow().isoformat()
                new_conv = {"phone": phone, "status": "active", "agent_enabled": True, "created_at": now, "updated_at": now}
                result = await _insert("bcomm_inbox.conversations", new_conv)
                conv_id = result[0]["id"] if result else None

            if not conv_id:
                return

            # Inserir mensagem
            now = __import__("datetime").datetime.utcnow().isoformat()
            msg_data = {
                "conversation_id": conv_id,
                "sender": sender,
                "content": content,
                "model": model,
                "message_id": message_id,
                "created_at": now,
            }
            await _insert("bcomm_inbox.messages", msg_data)

        except Exception as e:
            logger.error(f"Erro ao rastrear mensagem: {e}")

    async def get_active_sessions(self) -> List[dict]:
        """Retorna sessões ativas do Supabase."""
        try:
            sessions = await _load_sessions()
            return [
                {"phone": phone, "session_id": session_id}
                for phone, session_id in sessions.items()
            ]
        except Exception as e:
            logger.error(f"Erro ao ler sessões: {e}")
        return []

    def get_processing_status(self, phone: str) -> dict:
        """Retorna status de processamento de um phone."""
        status = self._processing_status.get(phone)
        if status:
            elapsed = __import__("time").time() - status["started_at"]
            return {"status": status["status"], "elapsed_seconds": round(elapsed, 1)}
        return {"status": "idle"}

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
