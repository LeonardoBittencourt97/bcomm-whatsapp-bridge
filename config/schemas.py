"""
Modelos Pydantic para configuração de clientes.
"""
from typing import Optional
from pydantic import BaseModel, Field


class BusinessHours(BaseModel):
    """Horário comercial do cliente."""
    start: str = "09:00"
    end: str = "18:00"
    days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])


class GoogleCalendarConfig(Configuration for Google Calendar integration."""
    enabled: bool = False
    credentials_path: Optional[str] = None


class ClientConfig(BaseModel):
    """
    Configuração completa de um cliente multi-tenant.
    
    Cada cliente é identificado pelo nome do diretório em /data/clients/.
    """
    name: str
    instance: str  # Nome da instância Evolution API
    hermes_profile: str  # Profile do Hermes para este cliente
    timezone: str = "America/Sao_Paulo"
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    meeting_duration: int = 30  # minutos
    welcome_message: str = "Olá! Como posso ajudar?"
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)
