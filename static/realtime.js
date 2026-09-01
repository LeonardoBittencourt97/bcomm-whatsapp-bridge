/* ============================================================================
   Realtime Notifications - BCOMM
   Conecta ao Supabase Realtime via WebSocket e mostra notificacoes
   quando ha INSERTs em messages, conversations, deals, activities.
   ============================================================================ */

// Configuracao (injetada pelas paginas via window.SUPABASE_* ou padrao)
const SUPABASE_URL = window.SUPABASE_URL || 'https://supabase.agent-bcomm.space';
const SUPABASE_ANON_KEY = window.SUPABASE_ANON_KEY || 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc4NDA4MTg4MCwiZXhwIjo0OTM5NzU1NDgwLCJyb2xlIjoic2VydmljZV9yb2xlIn0.dVqc4-jFSFR1w3P0T_3Oi_h6XJwL6QcBF-y8Hu9V1sg';

let realtimeChannel = null;
let supabaseClient = null;
let toastQueue = [];
let displayedToasts = 0;
const MAX_TOASTS = 4;
const TOAST_DURATION = 5000;
const PHONE_ICON = '📱';
const DEAL_ICON = '💰';
const ACTIVITY_ICON = '📋';
const CONTACT_ICON = '👤';

/* === Carregar Supabase JS do CDN (uma vez) === */
function loadSupabaseJS() {
    return new Promise((resolve, reject) => {
        if (window.supabase) return resolve(window.supabase);
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2';
        s.onload = () => resolve(window.supabase);
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

/* === Mostrar toast === */
function showRealtimeToast(opts) {
    const { icon, title, sub, link } = opts;
    const el = document.createElement('div');
    el.className = 'realtime-toast';
    el.innerHTML = `
        <div class="icon">${icon || '🔔'}</div>
        <div class="text">
            <div class="title">${escapeHtml(title || '')}</div>
            <div class="sub">${escapeHtml(sub || '')}</div>
        </div>
    `;
    if (link) {
        el.onclick = () => { window.location.href = link; };
    } else {
        el.onclick = () => el.remove();
    }
    document.body.appendChild(el);
    displayedToasts++;
    setTimeout(() => {
        el.style.animation = 'slideIn .3s ease reverse';
        setTimeout(() => { el.remove(); displayedToasts--; }, 300);
    }, TOAST_DURATION);
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* === Enfileirar toast (limite) === */
function queueToast(opts) {
    if (displayedToasts >= MAX_TOASTS) {
        toastQueue.push(opts);
        return;
    }
    showRealtimeToast(opts);
}

/* === Handlers de eventos === */
function handleMessage(payload) {
    const m = payload.new || {};
    const phone = m.sender_phone || m.phone || m.conversation_id || '';
    queueToast({
        icon: PHONE_ICON,
        title: 'Nova mensagem',
        sub: phone || 'Conversa',
        link: '/crm'
    });
    // Atualizar lista de conversas se funcao existir
    if (typeof window.loadConversations === 'function') {
        clearTimeout(window._reloadConversations);
        window._reloadConversations = setTimeout(() => window.loadConversations(), 500);
    }
    // Atualizar mensagens do chat se conversa aberta
    if (typeof window.selectConv === 'function' && window.currentPhone) {
        clearTimeout(window._reloadChat);
        window._reloadChat = setTimeout(() => window.selectConv(window.currentPhone), 500);
    }
    // Atualizar resumo da conversa aberta
    if (typeof window.loadConversationSummary === 'function' && window.currentPhone) {
        clearTimeout(window._reloadSummary);
        window._reloadSummary = setTimeout(() => window.loadConversationSummary(window.currentPhone), 500);
    }
}

function handleConversation(payload) {
    const c = payload.new || {};
    queueToast({
        icon: CONTACT_ICON,
        title: 'Nova conversa',
        sub: c.phone || '',
        link: '/crm'
    });
    if (typeof window.loadConversations === 'function') {
        clearTimeout(window._reloadConversations);
        window._reloadConversations = setTimeout(() => window.loadConversations(), 500);
    }
    // Atualizar resumo se conversa aberta mudou
    if (typeof window.loadConversationSummary === 'function' && window.currentPhone) {
        clearTimeout(window._reloadSummary);
        window._reloadSummary = setTimeout(() => window.loadConversationSummary(window.currentPhone), 500);
    }
}

function handleDeal(payload) {
    const d = payload.new || {};
    queueToast({
        icon: DEAL_ICON,
        title: 'Novo negócio',
        sub: d.title || '',
        link: '/pipelines'
    });
    if (typeof window.loadPipeline === 'function') {
        clearTimeout(window._reloadPipeline);
        window._reloadPipeline = setTimeout(() => window.loadPipeline(), 500);
    }
}

function handleActivity(payload) {
    const a = payload.new || {};
    queueToast({
        icon: ACTIVITY_ICON,
        title: 'Nova atividade',
        sub: a.subject || a.type || '',
        link: '/activities'
    });
    if (typeof window.loadActivities === 'function') {
        clearTimeout(window._reloadActivities);
        window._reloadActivities = setTimeout(() => window.loadActivities(), 500);
    }
}

/* === Inicializar Realtime === */
async function initRealtime() {
    try {
        const supabase = await loadSupabaseJS();
        if (!supabase || !supabase.createClient) {
            console.warn('[realtime] Supabase JS nao carregou');
            return;
        }
        supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
            realtime: { params: { eventsPerSecond: 10 } }
        });
        realtimeChannel = supabaseClient
            .channel('bcomm-inbox-' + Math.random().toString(36).slice(2, 8))
            .on('postgres_changes',
                { event: 'INSERT', schema: 'bcomm_inbox', table: 'messages' },
                handleMessage)
            .on('postgres_changes',
                { event: 'INSERT', schema: 'bcomm_inbox', table: 'conversations' },
                handleConversation)
            .on('postgres_changes',
                { event: 'UPDATE', schema: 'bcomm_inbox', table: 'conversations' },
                handleConversation)
            .on('postgres_changes',
                { event: 'INSERT', schema: 'bcomm_inbox', table: 'deals' },
                handleDeal)
            .on('postgres_changes',
                { event: 'INSERT', schema: 'bcomm_inbox', table: 'activities' },
                handleActivity)
            .subscribe((status) => {
                console.log('[realtime] subscription status:', status);
            });
        console.log('[realtime] initRealtime OK');
    } catch (e) {
        console.error('[realtime] init error:', e);
    }
}

/* === Cleanup === */
window.addEventListener('beforeunload', () => {
    if (realtimeChannel && supabaseClient) {
        supabaseClient.removeChannel(realtimeChannel);
    }
});

// Inicializar quando DOM estiver pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRealtime);
} else {
    initRealtime();
}
