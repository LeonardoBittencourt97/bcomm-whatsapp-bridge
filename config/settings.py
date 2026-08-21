"""
Configurações globais do bridge.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações carregadas de variáveis de ambiente."""
    
    # Evolution API
    evolution_api_url: str = "http://localhost:8080"
    evolution_api_key: str = ""
    evolution_instance: str = "BCOMM"
    
    # LLM
    llm_api_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4"
    
    # Hermes
    hermes_profile: str = "bcomm-atendente"
    hermes_container: str = "hermes-agent"
    use_hermes: bool = True
    
    # STT
    stt_api_url: str = "http://localhost:8001/v1"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    
    # Bridge
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    
    # Multi-tenant
    clients_dir: str = "/opt/data/clients"
    
    # Human delay
    human_delay_enabled: bool = True
    human_delay_min: float = 4.0
    human_delay_max: float = 15.0
    
    # Batch processing
    batch_wait_seconds: float = 10.0
    batch_max_wait: float = 150.0  # 2.5 minutes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton
settings = Settings()
