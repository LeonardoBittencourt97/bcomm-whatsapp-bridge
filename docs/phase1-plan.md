# 🗺️ FASE 1: Fundação - Plano de Implementação Detalhado

## 📋 Visão Geral

**Objetivo:** Estabelecer a base sólida do sistema com autenticação, banco de dados e configuração do agente.

**Duração estimada:** 2 semanas (10 dias úteis)

**Dependências:** 
- Supabase já disponível em `http://supabase.agent-bcomm.space`
- BetterAuth para autenticação

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│  React/Next.js + TailwindCSS + Shadcn/UI                   │
└─────────────────────────┬───────────────────────────────────┘
                          │ API Calls
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND                              │
│  FastAPI (Python) - Bridge existente                        │
│  + Novos endpoints para auth e config                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      DATABASE                               │
│  Supabase (PostgreSQL + Auth + Realtime)                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │    auth     │ │   public    │ │  storage    │           │
│  │  (BetterAuth│ │   (dados)   │ │ (arquivos)  │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

---

## 📅 Cronograma Detalhado

### **SEMANA 1: Database + Auth**

#### **Dia 1-2: Setup do Supabase**

**Objetivo:** Configurar banco de dados e tabelas iniciais

**Tarefas:**
1. Criar projeto no Supabase (ou usar existente)
2. Configurar connection string
3. Criar tabelas iniciais:

```sql
-- Usuários do sistema
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'agent', -- admin, manager, agent, viewer
    avatar_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Sessões de login
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(500) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    ip_address VARCHAR(45),
    user_agent TEXT
);

-- Configurações do agente
CREATE TABLE agent_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id VARCHAR(100) NOT NULL, -- identificador do cliente/instância
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    UNIQUE(client_id)
);

-- Config padrão do agente
CREATE TABLE agent_defaults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

4. Criar índices para performance:

```sql
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_sessions_token ON sessions(token);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_agent_config_client ON agent_config(client_id);
```

5. Configurar RLS (Row Level Security):

```sql
-- Habilitar RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_config ENABLE ROW LEVEL SECURITY;

-- Políticas básicas
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Admins can do everything" ON users
    USING (role = 'admin');
```

6. Criar função para verificar sessão:

```sql
CREATE OR REPLACE FUNCTION check_session(session_token VARCHAR)
RETURNS TABLE(user_id UUID, user_role VARCHAR, is_valid BOOLEAN) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.user_id,
        u.role,
        (s.expires_at > NOW()) as is_valid
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.token = session_token
    AND u.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;
```

**Entregáveis:**
- [ ] Schema do banco criado
- [ ] Migrações executadas
- [ ] RLS configurado
- [ ] Funções auxiliares criadas

---

#### **Dia 3-4: Sistema de Autenticação**

**Objetivo:** Implementar login/logout e controle de sessão

**Tarefas:**
1. Criar endpoints de autenticação:

```python
# auth.py
from fastapi import APIRouter, HTTPException, Depends, Header
from datetime import datetime, timedelta
import hashlib
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(email: str, password: str):
    """Login do usuário"""
    # 1. Buscar usuário por email
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    # 2. Verificar senha
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    # 3. Criar sessão
    session_token = create_session(user.id, user.role)
    
    # 4. Atualizar último login
    await update_last_login(user.id)
    
    return {
        "token": session_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
    }

@router.post("/logout")
async def logout(token: str = Header(...)):
    """Logout do usuário"""
    await delete_session(token)
    return {"status": "ok"}

@router.get("/me")
async def get_current_user(token: str = Header(...)):
    """Retorna usuário atual"""
    user = await get_user_from_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return user

@router.post("/refresh")
async def refresh_session(token: str = Header(...)):
    """Renova sessão"""
    new_token = await refresh_session_token(token)
    return {"token": new_token}
```

2. Criar middleware de autenticação:

```python
# middleware/auth.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Rotas públicas
        public_paths = ["/auth/login", "/health", "/webhook"]
        if any(request.url.path.startswith(p) for p in public_paths):
            return await call_next(request)
        
        # Verificar token
        token = request.headers.get("Authorization")
        if not token:
            raise HTTPException(status_code=401, detail="Token não fornecido")
        
        # Validar sessão
        user = await validate_session(token.replace("Bearer ", ""))
        if not user:
            raise HTTPException(status_code=401, detail="Sessão inválida")
        
        # Adicionar usuário ao request
        request.state.user = user
        
        return await call_next(request)
```

3. Criar funções auxiliares:

```python
# auth/utils.py
import bcrypt
import secrets
from datetime import datetime, timedelta

def hash_password(password: str) -> str:
    """Hash da senha"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    """Verifica senha"""
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def generate_session_token() -> str:
    """Gera token de sessão"""
    return secrets.token_urlsafe(32)

def create_session_token(user_id: str, role: str) -> str:
    """Cria sessão e retorna token"""
    token = generate_session_token()
    expires_at = datetime.now() + timedelta(hours=24)
    # Salvar no banco
    save_session(user_id, token, expires_at)
    return token
```

**Entregáveis:**
- [ ] Endpoint POST /auth/login
- [ ] Endpoint POST /auth/logout
- [ ] Endpoint GET /auth/me
- [ ] Endpoint POST /auth/refresh
- [ ] Middleware de autenticação
- [ ] Funções de hash/verificação de senha

---

#### **Dia 5: Seed Data e Testes**

**Objetivo:** Criar dados iniciais e testar autenticação

**Tarefas:**
1. Criar script de seed:

```python
# scripts/seed.py
async def seed():
    # Criar admin padrão
    admin = {
        "email": "admin@bcomm.com",
        "name": "Administrador",
        "password": "admin123",  # Será hasheada
        "role": "admin"
    }
    await create_user(admin)
    
    # Criar config padrão do agente
    default_config = {
        "greeting": "Olá! Como posso ajudar?",
        "business_hours": {"start": "09:00", "end": "18:00"},
        "transfer_keywords": ["humano", "atendente", "pessoa"],
        "max_response_length": 500
    }
    await save_agent_default(default_config)
```

2. Criar testes de autenticação:

```python
# tests/test_auth.py
def test_login_success():
    response = client.post("/auth/login", json={
        "email": "admin@bcomm.com",
        "password": "admin123"
    })
    assert response.status_code == 200
    assert "token" in response.json()

def test_login_wrong_password():
    response = client.post("/auth/login", json={
        "email": "admin@bcomm.com",
        "password": "wrong"
    })
    assert response.status_code == 401

def test_protected_route():
    response = client.get("/admin/metrics")
    assert response.status_code == 401
```

**Entregáveis:**
- [ ] Script de seed
- [ ] Dados iniciais criados
- [ ] Testes de autenticação
- [ ] Documentação da API

---

### **SEMANA 2: Configuração do Agente**

#### **Dia 6-7: Schema de Configuração**

**Objetivo:** Definir estrutura de configuração do agente

**Tarefas:**
1. Criar schema de configuração:

```python
# schemas/agent_config.py
from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum

class BusinessHours(BaseModel):
    start: str = "09:00"
    end: str = "18:00"
    timezone: str = "America/Sao_Paulo"
    work_days: List[int] = [1, 2, 3, 4, 5]  # Seg-Sex

class AgentPersonality(BaseModel):
    tone: str = "professional"  # professional, casual, friendly
    language: str = "pt-BR"
    max_response_length: int = 500
    typing_delay_enabled: bool = True
    typing_delay_min: float = 4.0
    typing_delay_max: float = 15.0

class TransferRules(BaseModel):
    keywords: List[str] = ["humano", "atendente", "pessoa", "gerente"]
    max_turns_before_transfer: int = 10
    sentiment_threshold: float = -0.5  # Negatividade para transferir

class GreetingConfig(BaseModel):
    welcome_message: str = "Olá! Como posso ajudar?"
    outside_hours_message: str = "Estamos fora do horário comercial. Retornaremos em breve."
    holiday_message: str = "Feliz feriado! Estaremos de volta amanhã."

class AgentConfiguration(BaseModel):
    """Configuração completa do agente"""
    client_id: str
    
    # Personalidade
    personality: AgentPersonality = AgentPersonality()
    
    # Horário comercial
    business_hours: BusinessHours = BusinessHours()
    
    # Saudação
    greeting: GreetingConfig = GreetingConfig()
    
    # Transferência
    transfer_rules: TransferRules = TransferRules()
    
    # Contexto do agente
    system_prompt: Optional[str] = None
    context_documents: List[str] = []  # IDs de documentos
    
    # Limites
    rate_limit: int = 20  # Mensagens por minuto
    batch_wait: float = 10.0  # Segundos para agrupar
    
    # Features
    human_delay_enabled: bool = True
    test_mode: bool = False
    test_numbers: List[str] = []
```

2. Criar endpoints de configuração:

```python
# config.py
@router.get("/agent/{client_id}")
async def get_agent_config(client_id: str):
    """Retorna configuração do agente"""
    config = await load_config(client_id)
    return config

@router.put("/agent/{client_id}")
async def update_agent_config(client_id: str, config: AgentConfiguration):
    """Atualiza configuração do agente"""
    await save_config(client_id, config)
    return {"status": "updated"}

@router.get("/agent/{client_id}/defaults")
async def get_default_config():
    """Retorna configuração padrão"""
    return await load_default_config()

@router.post("/agent/{client_id}/reset")
async def reset_agent_config(client_id: str):
    """Reseta configuração para padrão"""
    default = await load_default_config()
    await save_config(client_id, default)
    return {"status": "reset"}
```

3. Criar service de configuração:

```python
# services/agent_config_service.py
class AgentConfigService:
    def __init__(self, db):
        self.db = db
        self.cache = {}
    
    async def get_config(self, client_id: str) -> AgentConfiguration:
        """Busca configuração (com cache)"""
        if client_id in self.cache:
            return self.cache[client_id]
        
        config = await self.db.fetch_one(
            "SELECT config FROM agent_config WHERE client_id = :client_id",
            {"client_id": client_id}
        )
        
        if config:
            agent_config = AgentConfiguration(**config["config"])
            self.cache[client_id] = agent_config
            return agent_config
        
        # Retorna config padrão
        return await self.get_default_config()
    
    async def save_config(self, client_id: str, config: AgentConfiguration):
        """Salva configuração"""
        await self.db.execute(
            """INSERT INTO agent_config (client_id, config, updated_at) 
               VALUES (:client_id, :config, NOW())
               ON CONFLICT (client_id) 
               DO UPDATE SET config = :config, updated_at = NOW()""",
            {"client_id": client_id, "config": config.dict()}
        )
        self.cache[client_id] = config
    
    async def get_default_config(self) -> AgentConfiguration:
        """Retorna configuração padrão"""
        return AgentConfiguration(client_id="default")
```

**Entregáveis:**
- [ ] Schema de configuração criado
- [ ] Endpoints de configuração
- [ ] Service de configuração
- [ ] Cache implementado

---

#### **Dia 8-9: Integração com Bridge**

**Objetivo:** Conectar configuração com o bridge existente

**Tarefas:**
1. Atualizar bridge para usar configuração:

```python
# services/config.py
class ConfigurableBridge:
    def __init__(self):
        self.config_service = AgentConfigService()
    
    async def process_message(self, message, client_id):
        # 1. Carregar configuração do cliente
        config = await self.config_service.get_config(client_id)
        
        # 2. Verificar horário comercial
        if not self.is_business_hours(config.business_hours):
            return config.greeting.outside_hours_message
        
        # 3. Verificar se contato está pausado
        if await self.is_paused(client_id, message.from_number):
            return None
        
        # 4. Processar com configuração
        response = await self.generate_response(message, config)
        
        # 5. Aplicar delay se habilitado
        if config.personality.typing_delay_enabled:
            await self.apply_typing_delay(response, config.personality)
        
        return response
```

2. Criar endpoints para testar configuração:

```python
# test_config.py
@router.post("/agent/{client_id}/test")
async def test_agent_config(client_id: str, message: str):
    """Testa como o agente responderia"""
    config = await config_service.get_config(client_id)
    
    # Simular processamento
    response = await simulate_response(message, config)
    
    return {
        "message": message,
        "response": response,
        "config_applied": config.dict()
    }

@router.get("/agent/{client_id}/preview")
async def preview_config(client_id: str):
    """Preview da configuração"""
    config = await config_service.get_config(client_id)
    return {
        "greeting": config.greeting.welcome_message,
        "business_hours": config.business_hours,
        "transfer_keywords": config.transfer_rules.keywords
    }
```

**Entregáveis:**
- [ ] Bridge integrada com configuração
- [ ] Endpoint de teste
- [ ] Endpoint de preview
- [ ] Documentação

---

#### **Dia 10: Testes e Deploy**

**Objetivo:** Garantir qualidade e publicar

**Tarefas:**
1. Testes integrados:

```python
# tests/integration/test_config_flow.py
async def test_full_config_flow():
    # 1. Login
    token = await login("admin@bcomm.com", "admin123")
    
    # 2. Criar config
    config = {"client_id": "test", "personality": {"tone": "casual"}}
    await update_config("test", config, token)
    
    # 3. Verificar config
    saved = await get_config("test", token)
    assert saved["personality"]["tone"] == "casual"
    
    # 4. Testar agente
    response = await test_agent("test", "Olá!")
    assert "response" in response
```

2. Documentação da API:

```markdown
# API Documentation

## Authentication
- POST /auth/login - Login
- POST /auth/logout - Logout
- GET /auth/me - Usuário atual
- POST /auth/refresh - Renovar sessão

## Agent Configuration
- GET /agent/{client_id} - Buscar config
- PUT /agent/{client_id} - Atualizar config
- POST /agent/{client_id}/test - Testar agente
- POST /agent/{client_id}/reset - Resetar config
```

3. Deploy:

```bash
# Migration do banco
python scripts/migrate.py

# Seed de dados
python scripts/seed.py

# Deploy da aplicação
docker-compose up -d

# Verificar health
curl http://localhost:8000/health
```

**Entregáveis:**
- [ ] Testes executados
- [ ] Documentação completa
- [ ] Deploy realizado
- [ ] Health check OK

---

## 📊 Entregáveis da Fase 1

### Backend
- [ ] Schema do banco de dados
- [ ] Sistema de autenticação completo
- [ ] Middleware de proteção
- [ ] Endpoints de configuração do agente
- [ ] Service de configuração com cache
- [ ] Integração com bridge

### Frontend (Dashboard)
- [ ] Página de login
- [ ] Página de configuração do agente
- [ ] Formulário de configuração
- [ ] Preview de configuração

### Infraestrutura
- [ ] Migrações do banco
- [ ] Scripts de seed
- [ ] Testes automatizados
- [ ] Documentação da API

---

## 🔧 Tecnologias

| Componente | Tecnologia | Justificativa |
|------------|-----------|---------------|
| Backend | FastAPI | Já existe no bridge |
| Database | Supabase | Já disponível, completo |
| Auth | BetterAuth | Simples, seguro |
| Cache | Redis (opcional) | Performance |
| Frontend | React + Shadcn | Moderno, rápido |
| Testes | Pytest | Padrão Python |

---

## ⚠️ Riscos e Mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Supabase offline | Alto | Cache local + retry |
| Auth complexity | Médio | BetterAuth simplifica |
| Performance | Médio | Cache + índices |
| Segurança | Alto | RLS + validação |

---

## 📈 Métricas de Sucesso

- [ ] Login/logout funcionando
- [ ] Sessões expiram corretamente
- [ ] Config salva e carregada
- [ ] Bridge usa configuração
- [ ] Testes passando 100%
- [ ] API documentada

---

## 🚀 Próximos Passos (após Fase 1)

1. **Fase 2:** Base de conhecimento + RAG
2. **Fase 3:** Inbox + Contatos
3. **Fase 4:** Pipelines + CRM

---

**Status:** ⏳ Aguardando aprovação para iniciar
