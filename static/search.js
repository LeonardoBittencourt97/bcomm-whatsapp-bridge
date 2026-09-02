// Global Ctrl+K search modal — included on pages that don't already have it.
// Pages with their own search (e.g. crm.html) do not include this.

(function(){
    if(document.getElementById('search-modal'))return;

    const modal=document.createElement('div');
    modal.id='search-modal';
    modal.className='search-overlay';
    modal.innerHTML=`
        <div class="search-box">
            <div class="search-input-wrap">
                <span class="icon">🔍</span>
                <input id="search-input" placeholder="Buscar contatos, deals, mensagens..." autocomplete="off">
            </div>
            <div class="search-results" id="search-results"></div>
        </div>`;
    modal.onclick=e=>{if(e.target===modal)window.closeSearch()};
    document.body.appendChild(modal);

    // Inject CSS for search-overlay (matches crm.html styles)
    if(!document.getElementById('search-modal-css')){
        const css=document.createElement('style');
        css.id='search-modal-css';
        css.textContent=`
            .search-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);z-index:250;display:none;align-items:flex-start;justify-content:center;padding-top:15vh}
            .search-overlay.show{display:flex}
            .search-overlay .search-box{background:var(--card);border:1px solid var(--border);border-radius:var(--rl);width:600px;max-width:90vw;overflow:hidden}
            .search-overlay .search-input-wrap{display:flex;align-items:center;padding:16px;border-bottom:1px solid var(--border);gap:12px}
            .search-overlay .search-input-wrap .icon{font-size:18px;color:var(--muted)}
            .search-overlay .search-input-wrap input{flex:1;background:transparent;border:none;color:var(--text);font-size:16px;font-family:inherit;outline:none}
            .search-overlay .search-input-wrap input::placeholder{color:var(--muted)}
            .search-overlay .search-results{max-height:400px;overflow-y:auto;padding:8px}
            .search-overlay .search-group-label{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;padding:8px 12px;letter-spacing:.5px}
            .search-overlay .search-result{padding:10px 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:12px;transition:background .1s}
            .search-overlay .search-result:hover{background:var(--elevated)}
            .search-overlay .search-result .sr-icon{width:32px;height:32px;border-radius:8px;background:var(--elevated);display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
            .search-overlay .search-result .sr-info{flex:1;min-width:0}
            .search-overlay .search-result .sr-title{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
            .search-overlay .search-result .sr-sub{font-size:12px;color:var(--muted)}`;
        document.head.appendChild(css);
    }

    let _searchTimer=null;
    window.openSearch=function(){
        document.getElementById('search-modal').classList.add('show');
        setTimeout(()=>document.getElementById('search-input').focus(),50);
    };
    window.closeSearch=function(){
        document.getElementById('search-modal').classList.remove('show');
        const i=document.getElementById('search-input');if(i)i.value='';
        const r=document.getElementById('search-results');if(r)r.innerHTML='';
    };
    window._debounceSearch=function(){
        clearTimeout(_searchTimer);
        _searchTimer=setTimeout(_doSearch,300);
    };

    async function _doSearch(){
        const q=document.getElementById('search-input').value.trim();
        if(!q||q.length<2){document.getElementById('search-results').innerHTML='';return}
        const r=await fetch('/crm/search?q='+encodeURIComponent(q)+'&limit=5',{headers:{Accept:'application/json'}}).then(x=>x.json()).catch(()=>null);
        if(!r){document.getElementById('search-results').innerHTML='<div class="empty" style="padding:20px"><div class="empty-text">Nenhum resultado</div></div>';return}
        let html='';
        if(r.contacts&&r.contacts.length){html+='<div class="search-group-label">Contatos</div>';r.contacts.forEach(c=>{html+=`<div class="search-result" onclick="closeSearch();window.location.href='/contacts'"><div class="sr-icon">📇</div><div class="sr-info"><div class="sr-title">${c.name||c.phone||''}</div><div class="sr-sub">${c.phone||''}</div></div></div>`})}
        if(r.deals&&r.deals.length){html+='<div class="search-group-label">Negócios</div>';r.deals.forEach(d=>{html+=`<div class="search-result" onclick="closeSearch();window.location.href='/pipelines'"><div class="sr-icon">💰</div><div class="sr-info"><div class="sr-title">${d.title||''}</div><div class="sr-sub">R$ ${parseFloat(d.value||0).toLocaleString('pt-BR')}</div></div></div>`})}
        if(r.organizations&&r.organizations.length){html+='<div class="search-group-label">Organizações</div>';r.organizations.forEach(o=>{html+=`<div class="search-result" onclick="closeSearch();window.location.href='/organizations'"><div class="sr-icon">🏢</div><div class="sr-info"><div class="sr-title">${o.name||''}</div><div class="sr-sub">${o.cnpj||''}</div></div></div>`})}
        if(r.messages&&r.messages.length){html+='<div class="search-group-label">Mensagens</div>';r.messages.forEach(m=>{html+=`<div class="search-result" onclick="closeSearch();window.location.href='/crm'"><div class="sr-icon">💬</div><div class="sr-info"><div class="sr-title">${(m.content||'').substring(0,60)}</div><div class="sr-sub">${m.sender||''}</div></div></div>`})}
        if(!html)html='<div class="empty" style="padding:20px"><div class="empty-text">Nenhum resultado</div></div>';
        document.getElementById('search-results').innerHTML=html;
    }

    document.getElementById('search-input').addEventListener('input',window._debounceSearch);

    document.addEventListener('keydown',e=>{
        if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();window.openSearch()}
        if(e.key==='Escape')window.closeSearch()
    });

    // Wire up existing search-trigger in topbar (if present)
    const trigger=document.querySelector('.search-trigger');
    if(trigger){
        trigger.style.cursor='pointer';
        trigger.addEventListener('click',window.openSearch);
    }
})();