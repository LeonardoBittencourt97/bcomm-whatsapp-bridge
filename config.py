"""
Configuração do bridge server via variáveis de ambiente.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configurações centralizadas via env vars."""

    # Evolution API
    evolution_api_url: str = Field(default="https://evolution-api.agent-bcomm.space", description="URL base da Evolution API")
    evolution_api_key: str = Field(default="1F0C0840D74A-4EFF-B413-AF2DE616B30E", description="API key da Evolution API")
    evolution_instance: str = Field(default="BCOMM", description="Nome da instância Evolution")

    # Hermes
    hermes_profile: str = Field(default="bcomm-atendente", description="Profile do Hermes CLI")

    # LLM (OpenCode Go)
    opencode_api_key: str = Field(default="", description="API key do OpenCode")
    opencode_model: str = Field(default="mimo-v2.5", description="Modelo LLM")
    opencode_api_url: str = Field(default="https://opencode.ai/zen/go/v1", description="URL da API LLM")

    # Server
    port: int = Field(default=8000, description="Porta do servidor")
    debug: bool = Field(default=False, description="Modo debug")

    # Rate limiting
    rate_limit_per_minute: int = Field(default=20, description="Máximo de mensagens por minuto por contato")

    # STT
    stt_api_url: str = Field(default="https://stt.agent-bcomm.space/v1", description="URL da API STT")
    stt_api_key: str = Field(default="", description="API key para STT")
    stt_model: str = Field(default="whisper-1", description="Modelo STT")

    # Logging
    log_level: str = Field(default="INFO", description="Nível de log")

    # Multi-tenant
    clients_dir: str = Field(default="/opt/data/clients", description="Diretório de clientes")

    # Supabase
    supabase_url: str = Field(default="http://supabase.agent-bcomm.space", description="URL do Supabase")
    supabase_service_key: str = Field(default="", description="Service Role Key do Supabase")
    supabase_anon_key: str = Field(default="", description="Anon Key do Supabase")

    # Auth / JWT
    jwt_secret: str = Field(default="", description="Secret para assinatura JWT (obrigatório em produção)")
    jwt_algorithm: str = Field(default="HS256", description="Algoritmo JWT")
    jwt_expire_hours: int = Field(default=24, description="Expiração do token JWT em horas")
    cookie_domain: str = Field(default="", description="Domínio do cookie (vazio = auto)")
    cookie_secure: bool = Field(default=True, description="Cookie apenas HTTPS")

    # CORS
    cors_origins: str = Field(default="http://localhost:8000", description="Origens permitidas (separadas por vírgula)")

    # Master user setup
    master_email: str = Field(default="admin@bcomm.com", description="Email do usuário master")
    master_password: str = Field(default="", description="Senha do usuário master (obrigatória para setup)")

    # Human delay
    human_delay_enabled: bool = Field(default=True, description="Ativar delay humanizado")
    human_delay_min: float = Field(default=4.0, description="Delay mínimo em segundos")
    human_delay_max: float = Field(default=15.0, description="Delay máximo em segundos")

    # Batch processing
    batch_wait_seconds: float = Field(default=10.0, description="Espera por mensagens adicionais")
    batch_max_wait: float = Field(default=150.0, description="Máximo de espera")

    # Test mode
    test_mode: bool = Field(default=False, description="Modo teste (só responde números permitidos)")
    test_numbers: str = Field(default="", description="Números permitidos no modo teste (separados por vírgula)")

    # Pause/Resume
    paused_clients: str = Field(default="", description="Clientes pausados (separados por vírgula)")
    paused_contacts: str = Field(default="", description="Contatos pausados no formato cliente:numero (separados por vírgula)")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
