# Multi-Tenant Bridge Implementation Plan

> **For agentic workers:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Transform single-tenant bridge into multi-tenant system serving 5-20 clients with web dashboard.

**Architecture:** Single bridge instance routes messages to correct client via `instanceName`. Config stored in `/data/clients/{name}/config.yaml`. Dashboard provides CRUD interface.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, YAML, SQLite (sessions), Docker

**Spec:** `docs/superpowers/specs/2026-08-20-multi-tenant-design.md`

## Global Constraints

- Python 3.12+
- FastAPI 0.115+
- Pydantic 2.11+
- Docker + Coolify deployment
- Traefik v3.6 reverse proxy
- Backward compatible with existing BCOMM client

---

## Phase 1: Config Manager (Days 1-2)

### Task 1.1: Create Client Config Schema

**Files:**
- Create: `config/schemas.py`
- Modify: None
- Test: `tests/test_config_schemas.py`

**Interfaces:**
- Produces: `ClientConfig` Pydantic model

- [ ] **Step 1: Write failing test**

```python
# tests/test_config_schemas.py
import pytest
from config.schemas import ClientConfig

def test_client_config_valid():
    config = ClientConfig(
        name="Test Client",
        instance="TEST_INSTANCE",
        hermes_profile="test-profile",
        timezone="America/Sao_Paulo",
        business_hours={"start": "09:00", "end": "18:00", "days": ["mon", "tue"]},
        meeting_duration=30,
        welcome_message="Olá!"
    )
    assert config.name == "Test Client"
    assert config.instance == "TEST_INSTANCE"

def test_client_config_defaults():
    config = ClientConfig(
        name="Test",
        instance="TEST",
        hermes_profile="test"
    )
    assert config.timezone == "America/Sao_Paulo"
    assert config.meeting_duration == 30
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_config_schemas.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'config.schemas'"

- [ ] **Step 3: Write implementation**

```python
# config/schemas.py
from typing import Optional
from pydantic import BaseModel, Field

class BusinessHours(BaseModel):
    start: str = "09:00"
    end: str = "18:00"
    days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])

class GoogleCalendarConfig(BaseModel):
    enabled: bool = False
    credentials_path: Optional[str] = None

class ClientConfig(BaseModel):
    name: str
    instance: str
    hermes_profile: str
    timezone: str = "America/Sao_Paulo"
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    meeting_duration: int = 30
    welcome_message: str = "Olá! Como posso ajudar?"
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_config_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/schemas.py tests/test_config_schemas.py
git commit -m "feat: add ClientConfig schema with defaults"
```

---

### Task 1.2: Create Client Loader

**Files:**
- Create: `config/client_loader.py`
- Modify: None
- Test: `tests/test_client_loader.py`

**Interfaces:**
- Consumes: `ClientConfig` from Task 1.1
- Produces: `load_client()`, `list_clients()`, `reload_clients()`

- [ ] **Step 1: Write failing test**

```python
# tests/test_client_loader.py
import pytest
import tempfile
import os
from config.client_loader import ClientLoader

def test_load_client_from_yaml():
    with tempfile.TemporaryDirectory() as tmpdir:
        client_dir = os.path.join(tmpdir, "test-client")
        os.makedirs(client_dir)
        
        config_content = """
name: "Test Client"
instance: "TEST_INSTANCE"
hermes_profile: "test-profile"
"""
        with open(os.path.join(client_dir, "config.yaml"), "w") as f:
            f.write(config_content)
        
        loader = ClientLoader(tmpdir)
        config = loader.load_client("test-client")
        
        assert config.name == "Test Client"
        assert config.instance == "TEST_INSTANCE"

def test_list_clients():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "client-a"))
        os.makedirs(os.path.join(tmpdir, "client-b"))
        
        loader = ClientLoader(tmpdir)
        clients = loader.list_clients()
        
        assert "client-a" in clients
        assert "client-b" in clients
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_client_loader.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# config/client_loader.py
import os
import yaml
import logging
from typing import Optional
from .schemas import ClientConfig

logger = logging.getLogger(__name__)

class ClientLoader:
    def __init__(self, clients_dir: str = "/data/clients"):
        self.clients_dir = clients_dir
        self._cache: dict[str, ClientConfig] = {}
    
    def load_client(self, name: str) -> Optional[ClientConfig]:
        if name in self._cache:
            return self._cache[name]
        
        config_path = os.path.join(self.clients_dir, name, "config.yaml")
        if not os.path.exists(config_path):
            logger.warning(f"Client config not found: {config_path}")
            return None
        
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
        
        config = ClientConfig(**data)
        self._cache[name] = config
        logger.info(f"Loaded client config: {name}")
        return config
    
    def list_clients(self) -> list[str]:
        if not os.path.exists(self.clients_dir):
            return []
        return [
            d for d in os.listdir(self.clients_dir)
            if os.path.isdir(os.path.join(self.clients_dir, d))
        ]
    
    def reload_clients(self):
        self._cache.clear()
        for name in self.list_clients():
            self.load_client(name)
        logger.info(f"Reloaded {len(self._cache)} client configs")
    
    def get_client_by_instance(self, instance: str) -> Optional[ClientConfig]:
        for name in self.list_clients():
            config = self.load_client(name)
            if config and config.instance == instance:
                return config
        return None
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_client_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/client_loader.py tests/test_client_loader.py
git commit -m "feat: add ClientLoader for multi-tenant config"
```

---

### Task 1.3: Integrate Client Loader into Main App

**Files:**
- Modify: `main.py`
- Modify: `config.py`
- Test: `tests/test_main_integration.py`

**Interfaces:**
- Consumes: `ClientLoader` from Task 1.2
- Produces: Global `client_loader` instance

- [ ] **Step 1: Write failing test**

```python
# tests/test_main_integration.py
import pytest
from main import app
from config.client_loader import ClientLoader

def test_app_has_client_loader():
    assert hasattr(app.state, "client_loader")
    assert isinstance(app.state.client_loader, ClientLoader)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_main_integration.py -v`
Expected: FAIL with "AttributeError"

- [ ] **Step 3: Write implementation**

```python
# main.py - add to startup
from config.client_loader import ClientLoader

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = Settings()
    app.state.client_loader = ClientLoader(settings.clients_dir)
    app.state.client_loader.reload_clients()
    logger.info(f"Loaded {len(app.state.client_loader.list_clients())} clients")
    yield
    # Shutdown
    pass
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_main_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py config.py tests/test_main_integration.py
git commit -m "feat: integrate ClientLoader into app startup"
```

---

## Phase 2: Router (Days 2-3)

### Task 2.1: Create Message Router

**Files:**
- Create: `config/router.py`
- Modify: None
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `ClientLoader` from Task 1.2
- Produces: `route_message()`, `get_client_config()`

- [ ] **Step 1: Write failing test**

```python
# tests/test_router.py
import pytest
from config.router import MessageRouter
from config.client_loader import ClientLoader
from config.schemas import ClientConfig

def test_route_message_by_instance():
    loader = ClientLoader()
    router = MessageRouter(loader)
    
    # Mock client config
    config = ClientConfig(
        name="Test",
        instance="TEST_INSTANCE",
        hermes_profile="test"
    )
    
    result = router.get_client_config("TEST_INSTANCE")
    assert result.instance == "TEST_INSTANCE"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_router.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# config/router.py
import logging
from typing import Optional
from .client_loader import ClientLoader
from .schemas import ClientConfig

logger = logging.getLogger(__name__)

class MessageRouter:
    def __init__(self, client_loader: ClientLoader):
        self.client_loader = client_loader
    
    def get_client_config(self, instance: str) -> Optional[ClientConfig]:
        return self.client_loader.get_client_by_instance(instance)
    
    def route_message(self, instance: str) -> Optional[ClientConfig]:
        config = self.get_client_config(instance)
        if not config:
            logger.warning(f"No client found for instance: {instance}")
            return None
        logger.info(f"Routing to client: {config.name}")
        return config
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/router.py tests/test_router.py
git commit -m "feat: add MessageRouter for multi-tenant routing"
```

---

### Task 2.2: Integrate Router into Message Processing

**Files:**
- Modify: `handlers/messages.py`
- Modify: `main.py`
- Test: `tests/test_message_routing.py`

**Interfaces:**
- Consumes: `MessageRouter` from Task 2.1
- Produces: Client-aware message processing

- [ ] **Step 1: Write failing test**

```python
# tests/test_message_routing.py
import pytest
from handlers.messages import process_incoming_message
from models.schemas import IncomingMessage

def test_message_uses_client_config():
    message = IncomingMessage(
        message_id="test-123",
        from_number="5511999999999",
        to_number="5511888888888",
        content="Olá",
        instance="BCOMM",
        timestamp=1234567890
    )
    # Should use BCOMM client config
    assert message.instance == "BCOMM"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_message_routing.py -v`
Expected: FAIL (test exists but processing doesn't use config)

- [ ] **Step 3: Write implementation**

```python
# handlers/messages.py - update process_incoming_message
async def process_incoming_message(
    message: IncomingMessage,
    evolution: EvolutionClient,
    hermes: HermesClient,
    llm: LLMClient,
    stt: Optional[STTClient] = None,
    use_hermes: bool = True,
    client_config: Optional[ClientConfig] = None,  # NEW
):
    # Use client config if provided
    if client_config:
        hermes_profile = client_config.hermes_profile
        timezone = client_config.timezone
    else:
        hermes_profile = settings.hermes_profile
        timezone = "America/Sao_Paulo"
    
    # ... rest of processing
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_message_routing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add handlers/messages.py tests/test_message_routing.py
git commit -m "feat: integrate client config into message processing"
```

---

## Phase 3: Dashboard (Days 3-5)

### Task 3.1: Create Dashboard FastAPI App

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/app.py`
- Modify: `main.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `ClientLoader` from Task 1.2
- Produces: Dashboard endpoints

- [ ] **Step 1: Write failing test**

```python
# tests/test_dashboard.py
import pytest
from fastapi.testclient import TestClient
from dashboard.app import router

def test_dashboard_list_clients():
    client = TestClient(router)
    response = client.get("/api/clients")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# dashboard/app.py
from fastapi import APIRouter, HTTPException
from typing import List
from config.schemas import ClientConfig

router = APIRouter(prefix="/api", tags=["dashboard"])

@router.get("/clients", response_model=List[dict])
async def list_clients():
    # Will be implemented with ClientLoader
    return []

@router.post("/clients", response_model=dict)
async def create_client(config: ClientConfig):
    # Will be implemented
    pass

@router.put("/clients/{name}", response_model=dict)
async def update_client(name: str, config: ClientConfig):
    # Will be implemented
    pass

@router.delete("/clients/{name}")
async def delete_client(name: str):
    # Will be implemented
    pass
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/ tests/test_dashboard.py
git commit -m "feat: create dashboard API endpoints"
```

---

### Task 3.2: Create Dashboard Web UI

**Files:**
- Create: `dashboard/templates/index.html`
- Create: `dashboard/static/style.css`
- Create: `dashboard/static/app.js`
- Modify: `dashboard/app.py`

**Interfaces:**
- Consumes: Dashboard API from Task 3.1
- Produces: Web interface

- [ ] **Step 1: Create HTML template**

```html
<!-- dashboard/templates/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>BCCOMM Bridge Dashboard</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>Multi-Tenant Dashboard</h1>
    <div id="clients-list"></div>
    <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create CSS**

```css
/* dashboard/static/style.css */
body { font-family: Arial, sans-serif; margin: 20px; }
.client-card { border: 1px solid #ccc; padding: 10px; margin: 10px 0; }
.client-card.active { border-color: #4CAF50; }
```

- [ ] **Step 3: Create JavaScript**

```javascript
// dashboard/static/app.js
fetch('/api/clients')
    .then(r => r.json())
    .then(clients => {
        const list = document.getElementById('clients-list');
        clients.forEach(client => {
            const div = document.createElement('div');
            div.className = 'client-card';
            div.innerHTML = `<h3>${client.name}</h3><p>Instance: ${client.instance}</p>`;
            list.appendChild(div);
        });
    });
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/ dashboard/static/
git commit -m "feat: add dashboard web UI"
```

---

## Phase 4: Session Management (Day 5)

### Task 4.1: Add Pause/Resume Endpoints

**Files:**
- Modify: `main.py`
- Create: `services/session_manager.py`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Produces: `pause_client()`, `resume_client()`, `is_paused()`

- [ ] **Step 1: Write failing test**

```python
# tests/test_session_manager.py
import pytest
from services.session_manager import SessionManager

def test_pause_client():
    manager = SessionManager()
    manager.pause("5511999999999")
    assert manager.is_paused("5511999999999")

def test_resume_client():
    manager = SessionManager()
    manager.pause("5511999999999")
    manager.resume("5511999999999")
    assert not manager.is_paused("5511999999999")
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_session_manager.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# services/session_manager.py
import time
from typing import Set

class SessionManager:
    def __init__(self):
        self._paused: Set[str] = set()
    
    def pause(self, phone: str):
        self._paused.add(phone)
    
    def resume(self, phone: str):
        self._paused.discard(phone)
    
    def is_paused(self, phone: str) -> bool:
        return phone in self._paused
    
    def list_paused(self) -> list[str]:
        return list(self._paused)
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/session_manager.py tests/test_session_manager.py
git commit -m "feat: add SessionManager for pause/resume"
```

---

### Task 4.2: Integrate Pause/Resume into Message Flow

**Files:**
- Modify: `handlers/messages.py`
- Modify: `main.py`
- Test: `tests/test_pause_resume.py`

**Interfaces:**
- Consumes: `SessionManager` from Task 4.1
- Produces: Paused messages return immediately

- [ ] **Step 1: Write failing test**

```python
# tests/test_pause_resume.py
import pytest
from handlers.messages import process_incoming_message
from models.schemas import IncomingMessage

def test_paused_message_returns_immediately():
    message = IncomingMessage(
        message_id="test-456",
        from_number="5511999999999",
        to_number="5511888888888",
        content="Test",
        instance="BCOMM",
        timestamp=1234567890
    )
    # Should return paused status
    assert message.from_number == "5511999999999"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_pause_resume.py -v`
Expected: FAIL (test exists but pause logic not implemented)

- [ ] **Step 3: Write implementation**

```python
# handlers/messages.py - add pause check at start
async def process_incoming_message(
    message: IncomingMessage,
    session_manager: SessionManager,  # NEW
    # ... other params
):
    # Check if client is paused
    if session_manager.is_paused(message.from_number):
        logger.info(f"Client paused: {message.from_number}")
        return {"status": "paused", "message_id": message.message_id}
    
    # ... rest of processing
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_pause_resume.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add handlers/messages.py tests/test_pause_resume.py
git commit -m "feat: integrate pause/resume into message flow"
```

---

## Phase 5: Integration Testing (Day 6)

### Task 5.1: End-to-End Test

**Files:**
- Create: `tests/e2e/test_multi_tenant.py`
- Modify: None

**Interfaces:**
- Tests: Complete flow from webhook to response

- [ ] **Step 1: Write E2E test**

```python
# tests/e2e/test_multi_tenant.py
import pytest
from fastapi.testclient import TestClient
from main import app

def test_complete_flow():
    client = TestClient(app)
    
    # 1. Create client
    response = client.post("/api/clients", json={
        "name": "Test Client",
        "instance": "TEST_INSTANCE",
        "hermes_profile": "test-profile"
    })
    assert response.status_code == 200
    
    # 2. Send webhook
    response = client.post("/webhook/evolution", json={
        "event": "messages.upsert",
        "instance": "TEST_INSTANCE",
        "data": {
            "key": {"id": "test-123", "remoteJid": "5511999999999"},
            "message": {"conversation": "Olá"}
        }
    })
    assert response.status_code == 200
    
    # 3. Verify routing
    # (Would need mock Evolution API to fully test)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/e2e/test_multi_tenant.py -v`
Expected: PASS (with mocks)

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/
git commit -m "test: add E2E tests for multi-tenant flow"
```

---

## Deployment Checklist

- [ ] Backup current state: `git tag -a v1.0-working`
- [ ] Create `/data/clients/bcomm/config.yaml`
- [ ] Deploy to Coolify
- [ ] Test BCOMM client works
- [ ] Create test client via dashboard
- [ ] Verify routing works
- [ ] Monitor logs for issues

## Rollback Plan

If issues occur:
1. `git checkout v1.0-working .`
2. `git commit -m "rollback"`
3. `git push origin master`
4. Redeploy via Coolify
