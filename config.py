"""
Configuração do bridge server via variáveis de ambiente.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configurações centralizadas via env vars."""

    # Evolution API
    evolution_api_url: str = Field(..., description="URL base da Evolution API")
    evolution_api_key: str = Field(..., description="API key da Evolution API")
    evolution_instance: str = Field(..., description="Nome da instância Evolution")

    # Hermes
    hermes_profile: str = Field(default="default", description="Profile do Hermes CLI")

    # LLM (OpenCode Go)
    opencode_api_key: str = Field(default="", description="API key do OpenCode")
    opencode_model: str = Field(default="mimo-v2.5", description="Modelo LLM")
    opencode_api_url: str = Field(
        default="http://localhost:11434/v1",
        description="URL da API LLM (compatível OpenAI)",
    )

    # Server
    port: int = Field(default=8000, description="Porta do servidor")
    debug: bool = Field(default=False, description="Modo debug")

    # Rate limiting
    rate_limit_per_minute: int = Field(
        default=20, description="Máximo de mensagens por minuto por contato"
    )

    # STT (Speech-to-Text via Whisper)
    stt_api_url: str = Field(default="https://openrouter.ai/api/v1", description="URL da API STT (OpenRouter)")
    stt_api_key: str = Field(default="", description="API key para STT (usa OPENCODE_API_KEY se vazio)")
    stt_model: str = Field(default="openai/whisper-1", description="Modelo STT (openai/whisper-1 ou openai/whisper-large-v3-turbo)")

    # Logging
    log_level: str = Field(default="INFO", description="Nível de log")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
