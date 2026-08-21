"""
Loader de configurações de clientes multi-tenant.
Lê configs de /data/clients/{name}/config.yaml.
"""
import os
import yaml
import logging
from typing import Optional
from .schemas import ClientConfig

logger = logging.getLogger(__name__)


class ClientLoader:
    """
    Carrega e gerencia configurações de clientes.
    
    Suporta hot-reload sem necessidade de deploy.
    """
    
    def __init__(self, clients_dir: str = "/data/clients"):
        self.clients_dir = clients_dir
        self._cache: dict[str, ClientConfig] = {}
    
    def load_client(self, name: str) -> Optional[ClientConfig]:
        """
        Carrega configuração de um cliente específico.
        
        Args:
            name: Nome do cliente (nome do diretório)
        
        Returns:
            ClientConfig ou None se não encontrado
        """
        if name in self._cache:
            return self._cache[name]
        
        config_path = os.path.join(self.clients_dir, name, "config.yaml")
        if not os.path.exists(config_path):
            logger.warning(f"Client config not found: {config_path}")
            return None
        
        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)
            
            config = ClientConfig(**data)
            self._cache[name] = config
            logger.info(f"Loaded client config: {name}")
            return config
        except Exception as e:
            logger.error(f"Error loading client config {name}: {e}")
            return None
    
    def list_clients(self) -> list[str]:
        """Lista todos os clientes disponíveis."""
        if not os.path.exists(self.clients_dir):
            return []
        return [
            d for d in os.listdir(self.clients_dir)
            if os.path.isdir(os.path.join(self.clients_dir, d))
        ]
    
    def reload_clients(self):
        """Recarrega todas as configurações (hot-reload)."""
        self._cache.clear()
        for name in self.list_clients():
            self.load_client(name)
        logger.info(f"Reloaded {len(self._cache)} client configs")
    
    def get_client_by_instance(self, instance: str) -> Optional[ClientConfig]:
        """
        Busca cliente pelo nome da instância Evolution API.
        
        Args:
            instance: Nome da instância (ex: BCOMM)
        
        Returns:
            ClientConfig ou None se não encontrado
        """
        for name in self.list_clients():
            config = self.load_client(name)
            if config and config.instance == instance:
                return config
        return None
    
    def save_client(self, name: str, config: ClientConfig) -> bool:
        """
        Salva configuração de um cliente.
        
        Args:
            name: Nome do cliente
            config: Configuração do cliente
        
        Returns:
            True se salvo com sucesso
        """
        client_dir = os.path.join(self.clients_dir, name)
        os.makedirs(client_dir, exist_ok=True)
        
        config_path = os.path.join(client_dir, "config.yaml")
        try:
            with open(config_path, "w") as f:
                yaml.dump(config.model_dump(), f, default_flow_style=False)
            
            # Atualizar cache
            self._cache[name] = config
            logger.info(f"Saved client config: {name}")
            return True
        except Exception as e:
            logger.error(f"Error saving client config {name}: {e}")
            return False
    
    def delete_client(self, name: str) -> bool:
        """
        Remove configuração de um cliente.
        
        Args:
            name: Nome do cliente
        
        Returns:
            True se removido com sucesso
        """
        import shutil
        
        client_dir = os.path.join(self.clients_dir, name)
        if not os.path.exists(client_dir):
            return False
        
        try:
            shutil.rmtree(client_dir)
            self._cache.pop(name, None)
            logger.info(f"Deleted client config: {name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting client config {name}: {e}")
            return False
