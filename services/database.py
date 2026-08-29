"""
Cliente Supabase para o bridge.
Fornece acesso ao PostgreSQL via PostgREST API.
"""
import logging
from typing import Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None

# Default schema for bcomm_inbox tables
DEFAULT_SCHEMA = "bcomm_inbox"


def get_supabase(url: str, service_key: str) -> Client:
    """
    Retorna instância singleton do cliente Supabase.

    Args:
        url: URL do Supabase (ex: http://supabase.agent-bcomm.space)
        service_key: Service Role Key (acesso total)

    Returns:
        Cliente Supabase
    """
    global _supabase_client

    if _supabase_client is None:
        logger.info(f"Conectando ao Supabase: {url}")
        _supabase_client = create_client(url, service_key)
        logger.info("Supabase conectado com sucesso")

    return _supabase_client


def get_client() -> Optional[Client]:
    """Retorna cliente Supabase já inicializado (ou None)."""
    return _supabase_client


def ensure_supabase():
    """Garante que o cliente Supabase está inicializado. Levanta HTTPException 503 se não."""
    from fastapi import HTTPException
    if get_client() is None:
        raise HTTPException(status_code=503, detail="Database not configured")


def _parse_table(table: str) -> tuple[str, str]:
    """
    Parse schema-qualified table name.
    
    "bcomm_inbox.conversations" -> ("bcomm_inbox", "conversations")
    "conversations" -> (DEFAULT_SCHEMA, "conversations")
    """
    if "." in table:
        schema, tbl = table.split(".", 1)
        return schema, tbl
    return DEFAULT_SCHEMA, table


def _get_table_ref(client: Client, table: str):
    """Retorna referência de tabela com schema correto."""
    schema, tbl = _parse_table(table)
    return client.schema(schema).table(tbl)


# ── Helpers de query ──────────────────────────────────────────────

async def upsert(table: str, data: dict | list[dict], on_conflict: str = None) -> dict | list:
    """
    Insert ou update no Supabase.

    Args:
        table: Nome da tabela (ex: "bcomm_inbox.conversations")
        data: Dados para inserir/atualizar
        on_conflict: Coluna para conflito (upsert)

    Returns:
        Dados inseridos/atualizados
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return None

    try:
        query = _get_table_ref(client, table).upsert(data)
        if on_conflict:
            query = query.on_conflict(on_conflict)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Erro no upsert em {table}: {e}")
        return None


async def select(
    table: str,
    columns: str = "*",
    filters: dict = None,
    order: str = None,
    limit: int = None,
    offset: int = None,
) -> list[dict]:
    """
    Busca dados no Supabase.

    Args:
        table: Nome da tabela (ex: "bcomm_inbox.conversations")
        columns: Colunas para selecionar
        filters: Filtros {coluna: valor}
        order: Ordenação (ex: "created_at.desc")
        limit: Limite de resultados
        offset: Offset para paginação

    Returns:
        Lista de registros
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return []

    try:
        query = _get_table_ref(client, table).select(columns)

        if filters:
            for col, val in filters.items():
                if isinstance(val, dict):
                    op = list(val.keys())[0]
                    value = val[op]
                    if op == "in":
                        value = "(" + ",".join(str(v) for v in value) + ")"
                    query = query.filter(col, op, value)
                else:
                    query = query.eq(col, val)

        if order:
            parts = order.split(".")
            col = parts[0]
            desc = parts[1] == "desc" if len(parts) > 1 else False
            query = query.order(col, desc=desc)

        if limit:
            query = query.limit(limit)

        if offset:
            query = query.offset(offset)

        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Erro no select em {table}: {e}")
        return []


async def insert(table: str, data: dict | list[dict]) -> dict | list:
    """
    Insere dados no Supabase.

    Args:
        table: Nome da tabela (ex: "bcomm_inbox.conversations")
        data: Dados para inserir

    Returns:
        Dados inseridos
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return None

    try:
        result = _get_table_ref(client, table).insert(data).execute()
        return result.data
    except Exception as e:
        logger.error(f"Erro no insert em {table}: {e}")
        return None


async def update(table: str, data: dict, filters: dict) -> dict:
    """
    Atualiza dados no Supabase.

    Args:
        table: Nome da tabela (ex: "bcomm_inbox.conversations")
        data: Dados para atualizar
        filters: Filtros {coluna: valor}

    Returns:
        Dados atualizados
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return None

    try:
        query = _get_table_ref(client, table).update(data)
        for col, val in filters.items():
            query = query.eq(col, val)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Erro no update em {table}: {e}")
        return None


async def delete(table: str, filters: dict) -> bool:
    """
    Deleta dados no Supabase.

    Args:
        table: Nome da tabela (ex: "bcomm_inbox.conversations")
        filters: Filtros {coluna: valor}

    Returns:
        True se sucesso
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return False

    try:
        query = _get_table_ref(client, table).delete()
        for col, val in filters.items():
            query = query.eq(col, val)
        query.execute()
        return True
    except Exception as e:
        logger.error(f"Erro no delete em {table}: {e}")
        return False


async def rpc(function_name: str, params: dict = None) -> any:
    """
    Chama uma função RPC no Supabase.

    Args:
        function_name: Nome da função
        params: Parâmetros

    Returns:
        Resultado da função
    """
    client = get_client()
    if not client:
        logger.error("Supabase não inicializado")
        return None

    try:
        result = client.rpc(function_name, params).execute()
        return result.data
    except Exception as e:
        logger.error(f"Erro no rpc {function_name}: {e}")
        return None
