export const panelStyles = `
:host{display:block;height:100%;--turzi-primary:#6366f1;--turzi-success:#22c55e;--turzi-warning:#f59e0b;--turzi-danger:#ef4444;--turzi-bg:var(--primary-background-color,#0f0f14);--turzi-card:var(--card-background-color,#1a1a24);--turzi-text:var(--primary-text-color,#e2e8f0);--turzi-muted:var(--secondary-text-color,#94a3b8);--turzi-border:rgba(255,255,255,0.06);--turzi-radius:16px;font-family:var(--paper-font-body1_-_font-family,'Inter',sans-serif)}
*{box-sizing:border-box;margin:0;padding:0}
.shell{display:flex;flex-direction:column;height:100vh;background:var(--turzi-bg);color:var(--turzi-text)}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid var(--turzi-border);backdrop-filter:blur(12px)}
.topbar h1{font-size:20px;font-weight:700;display:flex;align-items:center;gap:8px}
.topbar h1 span{font-size:24px}
.tabs{display:flex;gap:4px;padding:8px 24px;border-bottom:1px solid var(--turzi-border);overflow-x:auto}
.tab{padding:10px 20px;border-radius:10px;cursor:pointer;font-size:13px;font-weight:600;color:var(--turzi-muted);transition:all .2s;border:none;background:none;white-space:nowrap}
.tab:hover{color:var(--turzi-text);background:rgba(99,102,241,0.08)}
.tab.active{color:#fff;background:var(--turzi-primary)}
.content{flex:1;overflow-y:auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.card{background:var(--turzi-card);border:1px solid var(--turzi-border);border-radius:var(--turzi-radius);padding:20px;transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.2)}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.card-title{font-size:16px;font-weight:600}
.badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.badge.heating{background:rgba(239,68,68,.15);color:#ef4444}
.badge.cooling{background:rgba(59,130,246,.15);color:#3b82f6}
.badge.idle{background:rgba(34,197,94,.15);color:#22c55e}
.badge.off{background:rgba(148,163,184,.15);color:#94a3b8}
.badge.preheating{background:rgba(245,158,11,.15);color:#f59e0b}
.temp-display{text-align:center;padding:16px 0}
.temp-current{font-size:48px;font-weight:800;line-height:1}
.temp-unit{font-size:20px;font-weight:400;color:var(--turzi-muted)}
.temp-target{font-size:14px;color:var(--turzi-muted);margin-top:4px}
.meta-row{display:flex;justify-content:space-between;padding:8px 0;border-top:1px solid var(--turzi-border);font-size:13px}
.meta-label{color:var(--turzi-muted)}
.comfort-bar{height:6px;border-radius:3px;background:rgba(255,255,255,.06);margin-top:8px;overflow:hidden}
.comfort-fill{height:100%;border-radius:3px;transition:width .5s}
.weather-strip{background:var(--turzi-card);border:1px solid var(--turzi-border);border-radius:var(--turzi-radius);padding:20px;margin-bottom:16px;display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.weather-item{text-align:center}
.weather-value{font-size:24px;font-weight:700}
.weather-label{font-size:11px;color:var(--turzi-muted);text-transform:uppercase;letter-spacing:.5px}
.empty-state{text-align:center;padding:80px 20px;color:var(--turzi-muted)}
.empty-state h2{font-size:24px;margin-bottom:8px;color:var(--turzi-text)}
.empty-state p{font-size:14px;max-width:400px;margin:0 auto 24px}
button.primary{background:var(--turzi-primary);color:#fff;border:none;padding:12px 24px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .2s}
button.primary:hover{opacity:.85}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:var(--turzi-muted)}
.form-group select,.form-group input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text);font-size:14px}
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:100;backdrop-filter:blur(4px)}
.modal{background:var(--turzi-card);border:1px solid var(--turzi-border);border-radius:var(--turzi-radius);padding:24px;width:90%;max-width:500px;max-height:80vh;overflow-y:auto}
.modal h2{margin-bottom:20px;font-size:18px}
.btn-row{display:flex;gap:8px;justify-content:flex-end;margin-top:20px}
button.secondary{background:transparent;color:var(--turzi-muted);border:1px solid var(--turzi-border);padding:10px 20px;border-radius:10px;font-size:14px;cursor:pointer}
.schedule-grid{display:grid;grid-template-columns:60px repeat(7,1fr);gap:2px;font-size:11px}
.schedule-header{text-align:center;font-weight:700;padding:8px;color:var(--turzi-muted)}
.schedule-time{padding:4px 6px;color:var(--turzi-muted);text-align:right;font-size:10px}
.schedule-cell{padding:4px;border-radius:4px;cursor:pointer;text-align:center;transition:opacity .15s;min-height:20px}
.schedule-cell:hover{opacity:.8}
.strategy-card{background:var(--turzi-card);border:1px solid var(--turzi-border);border-radius:var(--turzi-radius);padding:20px;margin-bottom:16px}
.strategy-action{font-size:18px;font-weight:700;margin-bottom:8px}
.strategy-reason{font-size:14px;color:var(--turzi-muted);line-height:1.5}
.confidence-badge{display:inline-flex;align-items:center;gap:4px;font-size:12px;padding:4px 8px;border-radius:12px;background:rgba(99,102,241,.1);color:var(--turzi-primary)}
.tier-chip{display:inline-block;padding:4px 12px;border-radius:12px;font-size:12px;font-weight:600}
@media(max-width:600px){.content{padding:12px}.grid{grid-template-columns:1fr}.tabs{padding:8px 12px}}
`;
