// Стили раздела — внутри бандла, с префиксом .opsx, чтобы не трогать основную сборку.
export const CSS = `
.opsx { color:#1e293b; font-size:14px; }
.opsx h1 { font-size:24px; font-weight:700; margin:4px 0 4px; }
.opsx h2 { font-size:15px; font-weight:600; margin:0 0 12px; color:#0f172a; }
.opsx .opsx-h2-gap { margin-top:18px; }
.opsx-muted { color:#64748b; }
.opsx-mb { margin-bottom:12px; }
.opsx-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:13px; }
.opsx-head { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; flex-wrap:wrap; margin-bottom:16px; }
.opsx-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.opsx-btn { display:inline-block; padding:9px 16px; border-radius:6px; border:1px solid #cbd5e1; background:#fff; color:#0f172a; cursor:pointer; font-size:14px; font-weight:500; text-decoration:none; }
.opsx-btn:hover { border-color:#0d9488; color:#0f766e; }
.opsx-btn:disabled { opacity:.6; cursor:not-allowed; }
.opsx-btn-primary { background:linear-gradient(135deg,#0d9488,#06b6d4); color:#fff; border-color:transparent; }
.opsx-btn-primary:hover { color:#fff; background:linear-gradient(135deg,#0f766e,#0891b2); }
.opsx-link { background:none; border:none; color:#0f766e; cursor:pointer; padding:0; font-size:14px; margin-bottom:8px; }
.opsx-alert { padding:12px 14px; border-radius:8px; background:#f1f5f9; margin-bottom:14px; }
.opsx-alert ul { margin:6px 0 0 18px; }
.opsx-alert-err { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
.opsx-alert-ok { background:#f0fdfa; color:#115e59; border:1px solid #99f6e4; }
.opsx-alert-warn { background:#fffbeb; color:#92400e; border:1px solid #fde68a; }
.opsx-warn-text { color:#92400e; margin-top:4px; }
.opsx-filters { display:flex; gap:14px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }
.opsx-input { padding:9px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:14px; min-width:320px; background:#fff; }
.opsx-select { min-width:260px; max-width:360px; padding:6px 8px; }
.opsx-check { display:flex; gap:6px; align-items:center; cursor:pointer; user-select:none; }
.opsx-table-wrap { overflow-x:auto; background:#fff; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); }
.opsx-table { width:100%; border-collapse:collapse; }
.opsx-table th { text-align:left; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.03em; color:#64748b; padding:10px 12px; border-bottom:1px solid #e2e8f0; background:#f8fafc; white-space:nowrap; }
.opsx-table td { padding:10px 12px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
.opsx-table tbody tr { cursor:pointer; }
.opsx-table tbody tr:hover { background:#f0fdfa; }
.opsx-table tbody tr.opsx-row-static { cursor:default; }
.opsx-table tbody tr.opsx-row-static:hover { background:transparent; }
.opsx-table-compact td, .opsx-table-compact th { padding:7px 10px; }
.opsx-row-off td { color:#94a3b8; }
.opsx-name { font-weight:500; display:flex; align-items:center; gap:8px; }
.opsx-drive { display:inline-flex; color:#94a3b8; padding:2px; border-radius:4px; }
.opsx-drive:hover { color:#0f766e; background:#ccfbf1; }
.opsx-legal { font-size:15px; color:#334155; margin:2px 0 4px; }
.opsx-sub { font-size:12px; color:#94a3b8; margin-top:2px; }
.opsx-pill { display:inline-block; font-size:12px; padding:2px 8px; border-radius:999px; background:#e2e8f0; color:#475569; margin-right:4px; }
.opsx-pill-on { background:#ccfbf1; color:#0f766e; }
.opsx-pill-warn { background:#fef3c7; color:#92400e; }
.opsx-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width: 860px) { .opsx-grid { grid-template-columns:1fr; } .opsx-input { min-width:0; width:100%; } }
.opsx-card { background:#fff; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); padding:18px 20px; margin-bottom:16px; }
.opsx-card summary { cursor:pointer; font-weight:600; }
.opsx-kv { display:grid; grid-template-columns:160px 1fr; gap:12px; padding:6px 0; border-bottom:1px dashed #eef2f7; }
.opsx-kv:last-child { border-bottom:none; }
.opsx-k { color:#64748b; }
.opsx-break { word-break:break-all; }
.opsx-chips { display:flex; flex-wrap:wrap; gap:6px; }
.opsx-chip { font-size:12px; padding:3px 9px; border-radius:999px; background:#f1f5f9; color:#334155; }
.opsx-chip-on { background:#ccfbf1; color:#0f766e; font-weight:500; }
.opsx-chip-off { background:#f8fafc; color:#94a3b8; }
.opsx-sub-grid { margin-top:14px; }
.opsx-pre { margin-top:12px; font-size:12px; background:#0f172a; color:#e2e8f0; padding:14px; border-radius:6px; overflow:auto; max-height:480px; }
.opsx-cells { display:flex; flex-wrap:wrap; gap:4px; }
.opsx-st { display:inline-block; font-size:12px; padding:2px 7px; border-radius:4px; background:#f1f5f9; color:#334155; white-space:nowrap; }
.opsx-st-accepted { background:#dcfce7; color:#166534; }
.opsx-st-submitted { background:#e0f2fe; color:#075985; }
.opsx-st-rejected { background:#fee2e2; color:#991b1b; }
.opsx-st-due { background:#fef3c7; color:#92400e; }
.opsx-st-not_required { background:#f1f5f9; color:#94a3b8; }
.opsx-pill-susp { background:#ffedd5; color:#9a3412; font-weight:600; }
.opsx-block-head { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.opsx-block-head h2 { margin:0; }
.opsx .opsx-h3 { font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:.03em; color:#64748b; margin:16px 0 8px; }
.opsx-flag { display:flex; justify-content:space-between; gap:16px; padding:10px 12px; border-radius:6px; border:1px solid #e2e8f0; margin-bottom:8px; }
.opsx-flag-susp { border-left:4px solid #f97316; background:#fffaf5; }
.opsx-flag-conf { border-left:4px solid #0d9488; }
.opsx-flag-off { border-left:4px solid #cbd5e1; color:#64748b; }
.opsx-flag-main { min-width:0; }
.opsx-flag-actions { display:flex; gap:8px; align-items:flex-start; flex-shrink:0; }
.opsx-trigger { font-size:13px; margin-top:3px; word-break:break-word; }
.opsx-trigger-list { margin:3px 0 0 18px; }
.opsx-dismiss { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.opsx-obl-form { border:1px dashed #cbd5e1; border-radius:8px; padding:12px; margin:12px 0; display:flex; flex-direction:column; gap:8px; }
.opsx-obl-form label { display:flex; flex-direction:column; gap:4px; font-size:13px; color:#475569; }
.opsx-obl-row { display:flex; gap:12px; flex-wrap:wrap; }
.opsx-input-sm { min-width:0; width:200px; padding:6px 10px; }
.opsx-textarea { min-width:0; width:100%; font-family:inherit; }
.opsx-history { margin-top:12px; }
.opsx-history summary { cursor:pointer; color:#64748b; font-size:13px; margin-bottom:8px; }
.opsx-basis { font-size:12px; color:#0f766e; margin-top:2px; max-width:420px; }
@media (max-width: 860px) { .opsx-flag { flex-direction:column; } }
.opsx-sticky { position:sticky; bottom:0; background:#f8fafc; padding:12px 0; justify-content:flex-end; }
.opsx-tabs { display:flex; gap:4px; border-bottom:1px solid #e2e8f0; margin-bottom:14px; }
.opsx-tab { background:none; border:none; border-bottom:2px solid transparent; padding:9px 14px; font-size:14px; font-weight:500; color:#64748b; cursor:pointer; margin-bottom:-1px; }
.opsx-tab:hover { color:#0f766e; }
.opsx-tab-on { color:#0f766e; border-bottom-color:#0d9488; }
.opsx-drive-link { display:inline-flex; align-items:center; gap:6px; color:#0f766e; text-decoration:none; white-space:nowrap; padding:3px 8px; border-radius:6px; border:1px solid #ccfbf1; background:#f0fdfa; font-size:13px; }
.opsx-drive-link:hover { background:#ccfbf1; }
.opsx-pill-hidden { background:#1e293b; color:#f8fafc; }
.opsx-row-hidden td { background:#f8fafc; }
.opsx-switch { position:relative; width:38px; height:22px; border-radius:999px; border:none; background:#cbd5e1; cursor:pointer; padding:0; vertical-align:middle; transition:background .15s; }
.opsx-switch:disabled { opacity:.6; cursor:wait; }
.opsx-switch-on { background:#1e293b; }
.opsx-switch-knob { position:absolute; top:3px; left:3px; width:16px; height:16px; border-radius:50%; background:#fff; transition:left .15s; box-shadow:0 1px 2px rgba(0,0,0,.2); }
.opsx-switch-on .opsx-switch-knob { left:19px; }
.opsx-switch:focus-visible { outline:2px solid #0d9488; outline-offset:2px; }
.opsx-switch-note { margin-left:8px; font-size:12px; }
.opsx-service-text { margin-top:8px; font-size:13px; }
.opsx-service-gap { margin:12px 0 0; }
.opsx-facets { margin-top:-4px; }
.opsx-facet { position:relative; }
.opsx-facet-btn { padding:7px 12px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; cursor:pointer; font-size:13px; color:#334155; max-width:320px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.opsx-facet-btn:hover { border-color:#0d9488; }
.opsx-facet-on { border-color:#0d9488; background:#f0fdfa; color:#0f766e; font-weight:500; }
.opsx-facet-sum { color:inherit; }
.opsx-facet-pop { position:absolute; top:calc(100% + 4px); left:0; z-index:20; min-width:220px; max-height:340px; overflow-y:auto; background:#fff; border:1px solid #e2e8f0; border-radius:8px; box-shadow:0 8px 24px rgba(15,23,42,.12); padding:6px; }
.opsx-facet-item { display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; cursor:pointer; font-size:13px; }
.opsx-facet-item:hover { background:#f1f5f9; }
.opsx-facet-label { flex:1; }
.opsx-facet-count { color:#64748b; font-variant-numeric:tabular-nums; }
.opsx-facet-clear { margin:4px 8px 2px; font-size:13px; }
.opsx-facet-empty { padding:6px 8px; font-size:13px; }
.opsx-forms { font-size:13px; max-width:220px; }
.opsx-note { padding:8px 10px; border-left:3px solid #cbd5e1; background:#f8fafc; border-radius:4px; margin-top:8px; }
.opsx-note-text { white-space:pre-wrap; font-size:13px; }
.opsx-form-notes .opsx-note { margin-top:6px; max-width:420px; }
.opsx-note-add { font-size:12px; margin-top:4px; display:block; }
.opsx-form-cell { min-width:200px; }
`
