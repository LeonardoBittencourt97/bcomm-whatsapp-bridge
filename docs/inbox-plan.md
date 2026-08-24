# 📥 Plano: Página de Inbox

## 🎯 Objetivo
Criar uma central de atendimento onde todas as conversas aparecem em tempo real.

---

## 📊 Funcionalidades

### **1. Lista de Conversas**
- Lista lateral com todas as conversas
- Indicador de não lidas
- Última mensagem
- Timestamp
- Status (online/offline/digitando)
- Foto do contato
- Nome do contato

### **2. Área de Chat**
- Mensagens da conversa
- Scroll infinito para cima
- Timestamp em cada mensagem
- Tipo de mensagem (texto, áudio, imagem)
- Status da mensagem (enviada, entregue, lida)
- Indicador "digitando..."

### **3. Barra Lateral Direita (Detalhes)**
- Foto do contato
- Nome e telefone
- Informações do contato
- Tags/etiquetas
- Notas internas
- Histórico de atividades

### **4. Ações Rápidas**
- Resposta rápida
- Transferir para humano
- Pausar conversa
- Arquivar
- Bloquear
- Adicionar tag

### **5. Filtros e Busca**
- Busca por nome/telefone
- Filtro por status (ativa, pausada, arquivada)
- Filtro por cliente
- Filtro por período
- Ordenar por (mais recente, mais antigo)

### **6. Notificações**
- Nova mensagem (som + visual)
- Mensagem não lida
- Presença do contato (digitando/lendo)

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      INBOX PAGE                             │
├─────────────┬─────────────────────────┬─────────────────────┤
│   Lista     │      Chat Area          │    Detalhes         │
│  Lateral    │                         │                     │
│             │                         │                     │
│ ┌─────────┐ │ ┌─────────────────────┐ │ ┌─────────────────┐ │
│ │ Busca   │ │ │ Mensagens           │ │ │ Foto            │ │
│ ├─────────┤ │ │ ┌─────────────────┐ │ │ │ Nome            │ │
│ │ Filtros │ │ │ │ Mensagem 1     │ │ │ │ Telefone        │ │
│ ├─────────┤ │ │ │ Mensagem 2     │ │ │ │ Status          │ │
│ │ Lista   │ │ │ │ Mensagem 3     │ │ │ │ Tags            │ │
│ │ de      │ │ │ └─────────────────┘ │ │ ├─────────────────┤ │
│ │ Conversas│ │ │                     │ │ │ Notas           │ │
│ │         │ │ ├─────────────────────┤ │ │ Histórico       │ │
│ └─────────┘ │ │ Input + Ações       │ │ └─────────────────┘ │
│             │ └─────────────────────┘ │                     │
└─────────────┴─────────────────────────┴─────────────────────┘
```

---

## 🗄️ Schema do Banco

### **Tabelas Necessárias**

```sql
-- Conversas
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id),
    client_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active', -- active, paused, archived
    assigned_to UUID REFERENCES users(id),
    last_message_at TIMESTAMP,
    unread_count INTEGER DEFAULT 0,
    tags TEXT[] DEFAULT '{}',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Mensagens
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    direction VARCHAR(10) NOT NULL, -- inbound, outbound
    content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text', -- text, audio, image, document
    status VARCHAR(20) DEFAULT 'sent', -- sent, delivered, read, failed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Contatos
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    avatar_url VARCHAR(500),
    tags TEXT[] DEFAULT '{}',
    custom_fields JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_conversations_client ON conversations(client_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);
CREATE INDEX idx_contacts_phone ON contacts(phone);
```

---

## 🔌 Endpoints

### **Conversas**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/inbox/conversations` | GET | Lista conversas |
| `/inbox/conversations/{id}` | GET | Detalhes da conversa |
| `/inbox/conversations/{id}/messages` | GET | Mensagens da conversa |
| `/inbox/conversations/{id}/status` | PUT | Atualizar status |
| `/inbox/conversations/{id}/assign` | PUT | Atribuir atendente |
| `/inbox/conversations/{id}/tags` | PUT | Atualizar tags |
| `/inbox/conversations/{id}/notes` | PUT | Atualizar notas |

### **Mensagens**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/inbox/messages` | POST | Enviar mensagem |
| `/inbox/messages/{id}/read` | PUT | Marcar como lida |
| `/inbox/messages/search` | GET | Buscar mensagens |

### **Contatos**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/inbox/contacts` | GET | Lista contatos |
| `/inbox/contacts/{id}` | GET | Detalhes do contato |
| `/inbox/contacts/{id}` | PUT | Atualizar contato |

### **Filtros**

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/inbox/stats` | GET | Estatísticas |
| `/inbox/filters` | GET | Filtros disponíveis |

---

## 📱 Componentes do Frontend

### **1. ConversationList.jsx**
```jsx
- Barra de busca
- Filtros (status, cliente, período)
- Lista de conversas
  - Avatar
  - Nome
  - Última mensagem (truncada)
  - Timestamp
  - Badge de não lidas
  - Indicador de status
```

### **2. ChatArea.jsx**
```jsx
- Header (nome, status, ações)
- Lista de mensagens
  - Mensagem recebida (esquerda)
  - Mensagem enviada (direita)
  - Timestamp
  - Tipo (texto, áudio, imagem)
  - Status (✓, ✓✓, ✓✓ azul)
- Input de mensagem
  - Textarea
  - Botão enviar
  - Botão anexar
  - Botão emoji
```

### **3. ContactDetails.jsx**
```jsx
- Foto grande do contato
- Nome completo
- Telefone formatado
- Status (online/offline)
- Tags/etiquetas
- Notas internas
- Histórico de atividades
- Botões de ação
```

### **4. QuickActions.jsx**
```jsx
- Transferir para humano
- Pausar conversa
- Arquivar
- Bloquear
- Adicionar tag
- Nota rápida
```

---

## 🔄 Real-time Updates

### **WebSocket Events**
```javascript
// Nova mensagem
socket.on('new_message', (data) => {
    // Atualizar lista de conversas
    // Adicionar mensagem no chat
    // Tocar som de notificação
});

// Presença do contato
socket.on('contact_presence', (data) => {
    // Atualizar indicador (digitando/lendo)
});

// Status da mensagem
socket.on('message_status', (data) => {
    // Atualizar ✓✓✓
});

// Conversa atribuída
socket.on('conversation_assigned', (data) => {
    // Atualizar conversa na lista
});
```

---

## 🎨 Design

### **Cores (BCOMM)**
- Background: #0b0b0c
- Surface: #0b0e14
- Card: #13161a
- Border: #292d30
- Accent: #3b9eff
- Success: #34c759
- Danger: #ff453a

### **Layout**
- Lista lateral: 320px fixo
- Chat: flexível (restante)
- Detalhes: 300px fixo (toggle)

### **Responsivo**
- Desktop: 3 colunas
- Tablet: 2 colunas (lista + chat)
- Mobile: 1 coluna (navegação)

---

## ⏱️ Cronograma

### **Dia 1-2: Backend**
- [ ] Schema do banco
- [ ] Endpoints de conversas
- [ ] Endpoints de mensagens

### **Dia 3-4: Frontend - Lista**
- [ ] Componente ConversationList
- [ ] Filtros e busca
- [ ] Conexão com API

### **Dia 5-6: Frontend - Chat**
- [ ] Componente ChatArea
- [ ] Input de mensagem
- [ ] Envio de mensagens

### **Dia 7-8: Frontend - Detalhes**
- [ ] Componente ContactDetails
- [ ] Ações rápidas
- [ ] Tags e notas

### **Dia 9: Real-time**
- [ ] WebSocket setup
- [ ] Updates em tempo real
- [ ] Notificações

### **Dia 10: Testes e Deploy**
- [ ] Testes de integração
- [ ] Otimização
- [ ] Deploy

---

## 📋 Entregáveis

### Backend
- [ ] Schema do banco
- [ ] 12+ endpoints
- [ ] WebSocket events
- [ ] Documentação

### Frontend
- [ ] Página Inbox completa
- [ ] 4+ componentes
- [ ] Real-time updates
- [ ] Responsivo

### Testes
- [ ] Testes de API
- [ ] Testes de UI
- [ ] Testes de performance

---

## 🚀 Dependências

| Item | Status |
|------|--------|
| Supabase | ✅ Disponível |
| Bridge existente | ✅ Funcionando |
| Auth básico | ⚠️ Necessário mínimo |
| WebSocket | ❌ Implementar |

---

**Status:** ⏳ Aguardando aprovação
