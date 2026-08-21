"""
Loader de configurações de clientes multi-tenant.
"""
import os
import yaml
import logging
from typing import Dict, Optional

from models.schemas import ClientConfig

logger = logging.getLogger("bridge.client_loader")


class ClientLoader:
    """Carrega e gerencia configurações de clientes."""

    def __init__(self, clients_dir: str = "/opt/data/clients"):
        self._clients_dir = clients_dir
        self._clients: Dict[str, ClientConfig] = {}
        self._instance_map: Dict[str, str] = {}  # instance -> client_name
        self.load_all()

    def load_all(self) -> None:
        """Carrega todos os clientes do diretório."""
        if not os.path.exists(self._clients_dir):
            logger.warning(f"Clientes dir não encontrado: {self._clients_dir}")
            return

        for name in os.listdir(self._clients_dir):
            config_path = os.path.join(self._clients_dir, name, "config.yaml")
            if os.path.isfile(config_path):
                try:
                    config = self.load(name)
                    if config:
                        self._clients[name] = config
                        self._instance_map[config.instance] = name
                        logger.info(f"Cliente carregado: {name} (instance={config.instance})")
                except Exception as e:
                    logger.error(f"Erro ao carregar cliente {name}: {e}")

    def load(self, name: str) -> Optional[ClientConfig]:
        """Carrega config de um cliente específico."""
        config_path = os.path.join(self._clients_dir, name, "config.yaml")
        if not os.path.exists(config_path):
            return None

        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)

        return ClientConfig(**data)

    def reload(self) -> None:
        """Recarrega todas as configs."""
        self._clients.clear()
        self._instance_map.clear()
        self.load_all()

    def get_by_instance(self, instance_name: str) -> Optional[ClientConfig]:
        """Busca cliente pelo nome da instância Evolution API."""
        client_name = self._instance_map.get(instance_name)
        if client_name:
            return self._clients.get(client_name)
        return None

    def get(self, name: str) -> Optional[ClientConfig]:
        """Busca cliente pelo nome."""
        return self._clients.get(name)

    def list_all(self) -> list:
        """Lista todos os clientes."""
        return [
            {"name": name, "instance": c.instance, "hermes_profile": c.hermes_profile}
            for name, c in self._clients.items()
        ]

    @property
    def client_count(self) -> int:
        return len(self._clients)
