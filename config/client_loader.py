"""
Client configuration loader for multi-tenant support.
Loads client configs from config/clients.yaml.
"""
import yaml
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "clients.yaml"
_clients_config: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    global _clients_config
    if _clients_config is not None:
        return _clients_config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _clients_config = yaml.safe_load(f)
            logger.info(f"Loaded client config: {len(_clients_config.get('clients', {}))} clients")
            return _clients_config
    except FileNotFoundError:
        logger.error(f"Client config not found: {CONFIG_PATH}")
        return {"clients": {}, "default_client": "BCOMM"}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing client config: {e}")
        return {"clients": {}, "default_client": "BCOMM"}


def get_client_config(instance_name: str) -> Dict[str, Any]:
    config = _load_config()
    clients = config.get("clients", {})
    default = config.get("default_client", "BCOMM")
    
    if instance_name in clients:
        return clients[instance_name]
    
    for name, client_config in clients.items():
        if name.upper() == instance_name.upper():
            return client_config
    
    if default in clients:
        logger.warning(f"Client '{instance_name}' not found, using default: {default}")
        return clients[default]
    
    return {
        "name": instance_name,
        "hermes_profile": "default",
        "prompt_file": "prompts/atendimento.md",
        "timezone": "America/Sao_Paulo",
        "business_hours": {"start": "09:00", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
        "meeting_duration": 30,
        "welcome_message": "Olá! Como posso te ajudar?",
    }


def get_hermes_profile(instance_name: str) -> str:
    return get_client_config(instance_name).get("hermes_profile", "default")


def get_prompt_file(instance_name: str) -> str:
    return get_client_config(instance_name).get("prompt_file", "prompts/atendimento.md")


def list_clients() -> list[str]:
    config = _load_config()
    return list(config.get("clients", {}).keys())


def reload_config():
    global _clients_config
    _clients_config = None
    _load_config()
