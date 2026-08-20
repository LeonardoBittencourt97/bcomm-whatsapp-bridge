"""
Client configuration loader for multi-tenant support.
Loads client configs from /data/clients/{name}/config.yaml
Prompts stay in Hermes profiles (SOUL.md).
"""
import os
import yaml
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/data/clients"))
_clients_cache: Optional[Dict[str, Any]] = None


def _load_client_config(client_dir: Path) -> Dict[str, Any]:
    config_file = client_dir / "config.yaml"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def get_client_config(instance_name: str) -> Dict[str, Any]:
    client_dir = CLIENTS_DIR / instance_name
    if client_dir.exists():
        return _load_client_config(client_dir)
    
    # Fallback to default
    default = os.getenv("DEFAULT_CLIENT", "BCOMM")
    default_dir = CLIENTS_DIR / default
    if default_dir.exists():
        return _load_client_config(default_dir)
    
    return {"name": instance_name, "timezone": "America/Sao_Paulo"}


def get_hermes_profile(instance_name: str) -> str:
    config = get_client_config(instance_name)
    return config.get("hermes_profile", f"{instance_name.lower()}-atendente")


def get_credentials_path(instance_name: str, filename: str) -> Optional[Path]:
    path = CLIENTS_DIR / instance_name / "credentials" / filename
    return path if path.exists() else None


def list_clients() -> list[str]:
    if CLIENTS_DIR.exists():
        return [d.name for d in CLIENTS_DIR.iterdir() if d.is_dir() and (d / "config.yaml").exists()]
    return []


def reload_config():
    pass  # No cache to clear, always reads from disk
