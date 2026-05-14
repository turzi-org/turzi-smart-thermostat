/**
 * Turzi Smart Thermostat — Sidebar Panel
 * Main entry point. Uses Shadow DOM + vanilla JS (no build step).
 */
import { panelStyles } from './styles.js';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'zones', label: 'Zones', icon: '🏠' },
  { id: 'schedule', label: 'Schedule', icon: '📅' },
  { id: 'energy', label: 'Energy', icon: '⚡' },
  { id: 'strategy', label: 'AI Strategy', icon: '🤖' },
  { id: 'settings', label: 'Settings', icon: '⚙️' },
];

const MODE_COLORS = {
  comfort: '#22c55e', eco: '#3b82f6', sleep: '#8b5cf6',
  away: '#64748b', off: '#1e293b', boost: '#ef4444',
};

const ACTION_LABELS = {
  heating: 'Heating', cooling: 'Cooling', idle: 'Idle',
  off: 'Off', preheating: 'Pre-heating', pre_heat: 'Pre-heating',
  pre_cool: 'Pre-cooling', heat: 'Heating', cool: 'Cooling',
};

class TurziThermostatPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._panel = null;
    this._tab = 'dashboard';
    this._config = null;
    this._dashboard = null;
    this._entities = null;
    this._modal = null;
    this._scheduleSpace = null;
    this._entryId = null;
    this._dashPoll = null;  // interval handle for dashboard refresh
  }

  set hass(h) {
    this._hass = h;
    if (!this._entryId && !this._findingEntry) this._init();
    // Do NOT call _loadDashboard() here — HA calls this setter on every state
    // change, which would cause constant re-renders and collapse open panels.
  }

  set panel(p) { this._panel = p; }

  async _init() {
    this._findingEntry = true;
    await this._findEntryId();
    this._findingEntry = false;
    if (this._entryId && !this._config) {
      await this._loadConfig();
      // Start dashboard poll if that's the active tab
      if (this._tab === 'dashboard' && !this._dashPoll) {
        this._loadDashboard();
        this._dashPoll = setInterval(() => this._loadDashboard(), 30_000);
      }
    }
  }

  async _findEntryId() {
    if (!this._hass) return;
    try {
      const entries = await this._hass.callWS({ type: 'config_entries/get', domain: 'turzi_thermostat' });
      if (entries && entries.length) {
        this._entryId = entries[0].entry_id;
        console.log('[Turzi] Found entry_id:', this._entryId);
      } else {
        console.warn('[Turzi] No config entries found for turzi_thermostat');
      }
    } catch (e) {
      console.warn('[Turzi] Could not auto-detect entry_id', e);
    }
  }

  async _ws(type, data = {}) {
    if (!this._hass) return null;
    if (!this._entryId) {
      await this._findEntryId();
      if (!this._entryId) { console.error('[Turzi] No entry_id available'); return null; }
    }
    return this._hass.callWS({ type, entry_id: this._entryId, ...data });
  }

  async _loadConfig() {
    this._config = await this._ws('turzi_thermostat/get_config');
    this._render();
  }

  async _loadDashboard() {
    this._dashboard = await this._ws('turzi_thermostat/get_dashboard');
    if (this._tab === 'dashboard') this._render();
  }

  async _loadEntities() {
    if (!this._entities) {
      try {
        this._entities = await this._hass.callWS({ type: 'turzi_thermostat/get_available_entities' });
      } catch (e) {
        console.error('[Turzi] Failed to load entities', e);
        this._entities = { temperature_sensors: [], humidity_sensors: [], heating_outputs: [], cooling_outputs: [] };
      }
    }
    return this._entities;
  }

  _setTab(t) {
    this._tab = t;
    this._render();
    // Stop any existing poll
    if (this._dashPoll) { clearInterval(this._dashPoll); this._dashPoll = null; }
    if (t === 'dashboard') {
      // Load immediately, then poll every 30s
      this._loadDashboard();
      this._dashPoll = setInterval(() => this._loadDashboard(), 30_000);
    }
  }

  _render() {
    const s = this.shadowRoot;
    s.innerHTML = `<style>${panelStyles}</style>
    <div class="shell">
      <div class="topbar"><h1><span>🌡️</span> Turzi Smart Thermostat</h1></div>
      <div class="tabs">${TABS.map(t =>
        `<button class="tab ${this._tab === t.id ? 'active' : ''}" data-tab="${t.id}">${t.icon} ${t.label}</button>`
      ).join('')}</div>
      <div class="content" id="content"></div>
    </div>`;
    s.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => this._setTab(b.dataset.tab)));
    const c = s.getElementById('content');
    switch (this._tab) {
      case 'dashboard': this._renderDashboard(c); break;
      case 'zones': this._renderZones(c); break;
      case 'schedule': this._renderSchedule(c); break;
      case 'energy': this._renderEnergy(c); break;
      case 'strategy': this._renderStrategy(c); break;
      case 'settings': this._renderSettings(c); break;
    }
  }

  // === DASHBOARD TAB ===
  _renderDashboard(c) {
    const d = this._dashboard;
    if (!d) { c.innerHTML = '<p style="color:var(--turzi-muted)">Loading...</p>'; return; }
    const w = d.weather || {};
    let html = `<div class="weather-strip">
      <div class="weather-item"><div class="weather-value">${w.outdoor_temp != null ? w.outdoor_temp + '°' : '--'}</div><div class="weather-label">Outside</div></div>
      <div class="weather-item"><div class="weather-value">${w.outdoor_humidity != null ? w.outdoor_humidity + '%' : '--'}</div><div class="weather-label">Humidity</div></div>
      <div class="weather-item"><div class="weather-value">${w.wind_speed != null ? w.wind_speed : '--'}</div><div class="weather-label">Wind km/h</div></div>
      <div class="weather-item"><div class="weather-value">${w.condition || '--'}</div><div class="weather-label">Condition</div></div>
    </div><div class="grid">`;
    const spaces = d.spaces || {};
    if (!Object.keys(spaces).length) {
      html += '</div>' + this._emptyState('No zones configured', 'Add zones in the Zones tab to start monitoring.', 'Go to Zones', 'zones');
    } else {
      for (const [id, sp] of Object.entries(spaces)) {
        const action = sp.hvac_action || 'idle';
        const badgeClass = action.replace('pre_', 'pre');
        const score = sp.comfort_score != null ? sp.comfort_score : '--';
        const scoreColor = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
        const overrideBadge = sp.has_override
          ? `<span style="font-size:11px;background:#f59e0b22;color:#f59e0b;border:1px solid #f59e0b44;border-radius:6px;padding:2px 8px;margin-left:8px">✏️ Override</span>`
          : '';
        const ovOpen = this._ovOpen?.has(id);
        html += `<div class="card" data-space-id="${id}">
          <div class="card-header"><span class="card-title">${sp.name}${overrideBadge}</span><span class="badge ${badgeClass}">${ACTION_LABELS[action] || action}</span></div>
          <div class="temp-display"><span class="temp-current">${sp.current_temp != null ? sp.current_temp.toFixed(1) : '--'}</span><span class="temp-unit">°C</span>
            <div class="temp-target">Target: ${sp.target_temp != null ? sp.target_temp.toFixed(1) + '°C' : '--'}</div></div>
          <div class="meta-row"><span class="meta-label">Mode</span><span style="color:${MODE_COLORS[sp.schedule_mode] || '#fff'}">${(sp.schedule_mode || '').charAt(0).toUpperCase() + (sp.schedule_mode || '').slice(1)}</span></div>
          ${sp.energy_tier ? `<div class="meta-row"><span class="meta-label">Energy Tier</span><span>${sp.energy_tier}</span></div>` : ''}
          <div class="meta-row"><span class="meta-label">Comfort</span><span style="color:${scoreColor}">${score}${score !== '--' ? '/100' : ''}</span></div>
          ${score !== '--' ? `<div class="comfort-bar"><div class="comfort-fill" style="width:${score}%;background:${scoreColor}"></div></div>` : ''}
          ${sp.strategy_reason ? `<div class="meta-row" style="border:none;margin-top:8px"><span style="font-size:12px;color:var(--turzi-muted);font-style:italic">💡 ${sp.strategy_reason}</span></div>` : ''}
          <button class="ov-toggle secondary" style="width:100%;margin-top:12px;font-size:12px;padding:6px;text-align:left">
            ${ovOpen ? '▾' : '▸'} ✏️ Override
          </button>
          <div class="ov-body" style="display:${ovOpen ? 'flex' : 'none'};flex-direction:column;gap:8px;margin-top:8px">
            <div style="display:flex;gap:8px;align-items:center">
              <label style="font-size:12px;color:var(--turzi-muted);min-width:90px">Temp (°C)</label>
              <input type="number" step="0.5" min="10" max="35" value="${sp.override_temp ?? sp.target_temp ?? 21}"
                class="ov-temp" style="flex:1;padding:6px 10px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text)">
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              <label style="font-size:12px;color:var(--turzi-muted);min-width:90px">Mode</label>
              <select class="ov-mode" style="flex:1;padding:6px 10px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text)">
                <option value="">— Use schedule —</option>
                ${['comfort','eco','sleep','away','boost'].map(m => `<option value="${m}" ${sp.override_mode === m ? 'selected' : ''}>${m.charAt(0).toUpperCase()+m.slice(1)}</option>`).join('')}
              </select>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end">
              ${sp.has_override ? `<button class="secondary ov-clear" style="font-size:12px;padding:6px 12px">↩ Resume schedule</button>` : ''}
              <button class="primary ov-set" style="font-size:12px;padding:6px 14px">Apply</button>
            </div>
          </div>
        </div>`;
      }
      html += '</div>';
    }
    c.innerHTML = html;
    // Wire up override toggle + buttons
    if (!this._ovOpen) this._ovOpen = new Set();
    c.querySelectorAll('[data-space-id]').forEach(card => {
      const spaceId = card.dataset.spaceId;
      // Toggle open/close without re-render
      card.querySelector('.ov-toggle')?.addEventListener('click', () => {
        const body = card.querySelector('.ov-body');
        const btn = card.querySelector('.ov-toggle');
        const isOpen = body.style.display !== 'none';
        body.style.display = isOpen ? 'none' : 'flex';
        btn.textContent = `${isOpen ? '▸' : '▾'} ✏️ Override`;
        if (isOpen) this._ovOpen.delete(spaceId); else this._ovOpen.add(spaceId);
      });
      card.querySelector('.ov-set')?.addEventListener('click', async () => {
        const temp = parseFloat(card.querySelector('.ov-temp').value);
        const mode = card.querySelector('.ov-mode').value || null;
        await this._ws('turzi_thermostat/set_override', { space_id: spaceId, temp: isNaN(temp) ? null : temp, mode });
        await this._loadDashboard();
      });
      card.querySelector('.ov-clear')?.addEventListener('click', async () => {
        await this._ws('turzi_thermostat/clear_override', { space_id: spaceId });
        await this._loadDashboard();
      });
    });
  }

  // === ZONES TAB ===
  _renderZones(c) {
    const spaces = this._config?.spaces || {};
    let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px"><h2>Zones</h2><button class="primary" id="addZone">+ Add Zone</button></div>';
    if (!Object.keys(spaces).length) {
      html += this._emptyState('No zones yet', 'Add your first zone to start controlling your climate.');
    } else {
      html += '<div class="grid">';
      const typeIcons = { floor_heating: '🔥', radiator: '🌡️', fan_coil: '💨', split_ac: '❄️' };
      const typeLabels = { floor_heating: 'Floor Heating', radiator: 'Radiator', fan_coil: 'Fan-Coil', split_ac: 'Split A/C' };
      for (const [id, sp] of Object.entries(spaces)) {
        html += `<div class="card">
          <div class="card-header"><span class="card-title">${typeIcons[sp.hvac_type] || ''} ${sp.name}</span>
            <button class="secondary" style="padding:4px 12px;font-size:12px" data-edit="${id}">Edit</button></div>
          <div class="meta-row"><span class="meta-label">System</span><span>${typeLabels[sp.hvac_type] || sp.hvac_type}</span></div>
          <div class="meta-row"><span class="meta-label">Temp Sensor</span><span style="font-size:12px">${sp.temp_sensor}</span></div>
          <div class="meta-row"><span class="meta-label">Heating</span><span style="font-size:12px">${sp.heating_output}</span></div>
          ${sp.cooling_output ? `<div class="meta-row"><span class="meta-label">Cooling</span><span style="font-size:12px">${sp.cooling_output}</span></div>` : ''}
          <div class="meta-row"><span class="meta-label">Target</span><span>${sp.target_temp}°C</span></div>
        </div>`;
      }
      html += '</div>';
    }
    c.innerHTML = html;
    c.querySelector('#addZone')?.addEventListener('click', () => this._showZoneModal());
    c.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => this._showZoneModal(b.dataset.edit)));
  }

  async _showZoneModal(editId = null) {
    const ents = await this._loadEntities();
    const existing = editId ? this._config?.spaces?.[editId] : null;
    const s = this.shadowRoot;
    const div = document.createElement('div');
    div.className = 'modal-backdrop';
    div.innerHTML = `<div class="modal"><h2>${editId ? 'Edit' : 'Add'} Zone</h2>
      <div class="form-group"><label>Name</label><input id="zName" value="${existing?.name || ''}"></div>
      <div class="form-group"><label>HVAC System</label><select id="zType">
        ${['floor_heating','radiator','fan_coil','split_ac'].map(t => `<option value="${t}" ${existing?.hvac_type === t ? 'selected' : ''}>${t.replace(/_/g,' ')}</option>`).join('')}</select></div>
      <div class="form-group"><label>Temperature Sensor</label>${this._ssHtml('zTemp', ents?.temperature_sensors || [], existing?.temp_sensor, 'Search sensors...')}</div>
      <div class="form-group"><label>Humidity Sensor <span style="color:var(--turzi-muted);font-size:12px">(optional)</span></label>${this._ssHtml('zHum', ents?.humidity_sensors || [], existing?.humidity_sensor, 'None')}</div>
      <div class="form-group"><label>Heating Output</label>${this._ssHtml('zHeat', ents?.heating_outputs || [], existing?.heating_output, 'Search outputs...')}</div>
      <div class="form-group"><label>Cooling Output <span style="color:var(--turzi-muted);font-size:12px">(optional)</span></label>${this._ssHtml('zCool', ents?.cooling_outputs || [], existing?.cooling_output, 'None')}</div>
      <div class="form-group"><label>Auxiliary Heating <span style="color:var(--turzi-muted);font-size:12px">(optional)</span></label>${this._ssHtml('zAux', [...(ents?.heating_outputs||[]), ...(ents?.switches||[])], existing?.auxiliary_heating, 'None')}</div>
      <div class="form-group"><label>Target Temperature (°C)</label><input id="zTarget" type="number" step="0.5" min="5" max="35" value="${existing?.target_temp || 21}"></div>
      <div class="btn-row">${editId ? `<button class="secondary" id="zDel" style="margin-right:auto;color:#ef4444">Delete</button>` : ''}
        <button class="secondary" id="zCancel">Cancel</button><button class="primary" id="zSave">Save</button></div></div>`;
    s.appendChild(div);
    this._initSearchableSelects(div);
    div.querySelector('#zCancel').addEventListener('click', () => div.remove());
    div.querySelector('#zDel')?.addEventListener('click', async () => {
      await this._ws('turzi_thermostat/delete_space', { space_id: editId });
      div.remove(); await this._loadConfig(); this._setTab('zones');
    });
    div.querySelector('#zSave').addEventListener('click', async () => {
      const space = {
        name: div.querySelector('#zName').value,
        hvac_type: div.querySelector('#zType').value,
        temp_sensor: div.querySelector('#zTemp-val').value,
        humidity_sensor: div.querySelector('#zHum-val').value || null,
        heating_output: div.querySelector('#zHeat-val').value,
        cooling_output: div.querySelector('#zCool-val').value || null,
        auxiliary_heating: div.querySelector('#zAux-val').value || null,
        target_temp: parseFloat(div.querySelector('#zTarget').value),
      };
      if (!space.name || !space.temp_sensor || !space.heating_output) { alert('Name, temp sensor, and heating output are required.'); return; }
      await this._ws('turzi_thermostat/save_spaces', { spaces: [space] });
      div.remove(); this._entities = null; await this._loadConfig(); this._setTab('zones');
    });
  }

  // --- Searchable entity selector ---
  _ssHtml(id, options, selectedValue, placeholder = 'Search...') {
    const selected = options.find(o => o.entity_id === selectedValue);
    const display = selected ? `${selected.name} (${selected.entity_id})` : (selectedValue || '');
    const opts = options.map(o =>
      `<div class="ss-opt" data-val="${o.entity_id}">${o.name} <span style="opacity:.5;font-size:11px">${o.entity_id}</span></div>`
    ).join('');
    return `<div class="ss-wrap" style="position:relative">
      <input id="${id}-search" class="ss-search" autocomplete="off" spellcheck="false"
        placeholder="${placeholder}" value="${display}"
        style="width:100%;box-sizing:border-box;padding:8px 12px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text)">
      <input type="hidden" id="${id}-val" value="${selectedValue || ''}">
      <div class="ss-drop" style="display:none;position:absolute;z-index:9999;left:0;right:0;top:calc(100% + 2px);max-height:220px;overflow-y:auto;border-radius:8px;border:1px solid var(--turzi-border);background:#1e2a3a;box-shadow:0 12px 32px #000a">
        <div class="ss-opt" data-val="" style="padding:8px 12px;opacity:.6;font-style:italic;cursor:pointer">— None —</div>
        ${opts}
      </div>
    </div>`;
  }

  _initSearchableSelects(container) {
    container.querySelectorAll('.ss-wrap').forEach(wrap => {
      const search = wrap.querySelector('.ss-search');
      const val = wrap.querySelector('.ss-search + input[type=hidden], input[type=hidden]');
      const drop = wrap.querySelector('.ss-drop');
      const opts = () => [...drop.querySelectorAll('.ss-opt')];

      const show = () => { drop.style.display = 'block'; filter(); };
      const hide = () => setTimeout(() => { drop.style.display = 'none'; }, 150);
      const filter = () => {
        const q = search.value.toLowerCase();
        opts().forEach(o => { o.style.display = o.textContent.toLowerCase().includes(q) ? '' : 'none'; });
      };

      search.addEventListener('focus', show);
      search.addEventListener('input', filter);
      search.addEventListener('blur', hide);

      drop.addEventListener('mousedown', e => {
        const opt = e.target.closest('.ss-opt');
        if (!opt) return;
        val.value = opt.dataset.val;
        search.value = opt.dataset.val ? opt.innerText.trim() : '';
        drop.style.display = 'none';
      });
    });
  }

  // === SCHEDULE TAB ===
  _renderSchedule(c) {
    const spaces = this._config?.spaces || {};
    const ids = Object.keys(spaces);
    if (!ids.length) { c.innerHTML = this._emptyState('No zones', 'Add zones first to configure schedules.', 'Go to Zones', 'zones'); return; }
    if (!this._scheduleSpace || !spaces[this._scheduleSpace]) this._scheduleSpace = ids[0];
    const schedule = this._config?.schedule?.[this._scheduleSpace] || [];
    const days = ['mon','tue','wed','thu','fri','sat','sun'];
    const dayLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const hours = Array.from({length: 24}, (_, i) => i);
    const modes = Object.keys(MODE_COLORS);

    let html = `<div style="display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
      <h2>Schedule</h2>
      <select id="schSpace" style="padding:8px 12px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text)">
        ${ids.map(id => `<option value="${id}" ${id === this._scheduleSpace ? 'selected' : ''}>${spaces[id].name}</option>`).join('')}</select>
      <div style="margin-left:auto;display:flex;gap:8px">${modes.filter(m => m !== 'boost').map(m => `<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px"><span style="width:12px;height:12px;border-radius:3px;background:${MODE_COLORS[m]}"></span>${m}</span>`).join('')}</div>
    </div>`;

    // Build a lookup: for each day+hour, what mode?
    const grid = {};
    days.forEach(d => { grid[d] = {}; hours.forEach(h => grid[d][h] = null); });
    schedule.forEach(b => {
      const startH = parseInt(b.start.split(':')[0]);
      const endH = parseInt(b.end.split(':')[0]) || 24;
      (b.days || []).forEach(d => { for (let h = startH; h < endH; h++) grid[d][h] = b.mode; });
    });

    html += `<div class="schedule-grid"><div class="schedule-header"></div>${dayLabels.map(d => `<div class="schedule-header">${d}</div>`).join('')}`;
    hours.forEach(h => {
      html += `<div class="schedule-time">${String(h).padStart(2,'0')}:00</div>`;
      days.forEach((d, di) => {
        const mode = grid[d][h] || 'off';
        html += `<div class="schedule-cell" data-day="${d}" data-hour="${h}" style="background:${MODE_COLORS[mode] || MODE_COLORS.off}">&nbsp;</div>`;
      });
    });
    html += '</div>';
    html += `<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
      <span style="font-size:13px;color:var(--turzi-muted);line-height:36px">Paint mode:</span>
      ${modes.filter(m => m !== 'boost').map(m => `<button class="secondary schMode" data-mode="${m}" style="padding:6px 14px;font-size:12px;border-color:${MODE_COLORS[m]}">${m}</button>`).join('')}
      <button class="primary" id="schSave" style="margin-left:auto">Save Schedule</button></div>`;
    c.innerHTML = html;

    let paintMode = 'comfort';
    c.querySelectorAll('.schMode').forEach(b => b.addEventListener('click', () => {
      paintMode = b.dataset.mode;
      c.querySelectorAll('.schMode').forEach(x => x.style.background = 'transparent');
      b.style.background = MODE_COLORS[paintMode];
      b.style.color = '#fff';
    }));
    let painting = false;
    c.querySelectorAll('.schedule-cell').forEach(cell => {
      cell.addEventListener('mousedown', (e) => { painting = true; cell.style.background = MODE_COLORS[paintMode]; grid[cell.dataset.day][parseInt(cell.dataset.hour)] = paintMode; e.preventDefault(); });
      cell.addEventListener('mouseenter', () => { if (painting) { cell.style.background = MODE_COLORS[paintMode]; grid[cell.dataset.day][parseInt(cell.dataset.hour)] = paintMode; } });
    });
    document.addEventListener('mouseup', () => painting = false, { once: false });

    c.querySelector('#schSpace').addEventListener('change', (e) => { this._scheduleSpace = e.target.value; this._renderSchedule(c); });
    c.querySelector('#schSave').addEventListener('click', async () => {
      // Convert grid to blocks
      const blocks = [];
      days.forEach(d => {
        let current = null, start = null;
        hours.forEach(h => {
          const m = grid[d][h];
          if (m !== current) { if (current && current !== 'off') blocks.push({ days: [d], start: `${String(start).padStart(2,'0')}:00`, end: `${String(h).padStart(2,'0')}:00`, mode: current }); current = m; start = h; }
        });
        if (current && current !== 'off') blocks.push({ days: [d], start: `${String(start).padStart(2,'0')}:00`, end: '23:59', mode: current });
      });
      await this._ws('turzi_thermostat/save_schedule', { space_id: this._scheduleSpace, blocks });
      await this._loadConfig();
      alert('Schedule saved!');
    });
  }

  // === ENERGY TAB ===
  _renderEnergy(c) {
    const rates = this._config?.energy_rates || { tiers: [], schedule: [] };
    if (!rates.tiers.length) {
      c.innerHTML = this._emptyState('Energy tiers not configured', 'This is optional. Define your electricity rate tiers to enable energy-aware scheduling.', 'Set Up Tiers', 'energy_setup');
      c.querySelector('[data-action]')?.addEventListener('click', () => this._showTierModal());
      return;
    }

    const tiers = rates.tiers;
    const tierColors = {};
    tiers.forEach(t => { tierColors[t.name] = t.color || '#888'; });

    const days = ['mon','tue','wed','thu','fri','sat','sun'];
    const dayLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const hours = Array.from({length: 24}, (_, i) => i);

    let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap">
      <h2>Energy Rates</h2>
      <button class="primary" id="editTiers">Edit Tiers</button>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      ${tiers.map(t => `<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px"><span style="width:12px;height:12px;border-radius:3px;background:${t.color || '#888'}"></span>${t.name}</span>`).join('')}
    </div>`;

    // Build grid from existing schedule
    const grid = {};
    days.forEach(d => { grid[d] = {}; hours.forEach(h => grid[d][h] = null); });
    (rates.schedule || []).forEach(b => {
      const startH = parseInt(b.start.split(':')[0]);
      const endH = parseInt(b.end.split(':')[0]) || 24;
      (b.days || []).forEach(d => { for (let h = startH; h < endH; h++) grid[d][h] = b.tier; });
    });

    html += `<div class="schedule-grid"><div class="schedule-header"></div>${dayLabels.map(d => `<div class="schedule-header">${d}</div>`).join('')}`;
    hours.forEach(h => {
      html += `<div class="schedule-time">${String(h).padStart(2,'0')}:00</div>`;
      days.forEach(d => {
        const tier = grid[d][h];
        const bg = tier ? (tierColors[tier] || '#888') : 'var(--turzi-border)';
        html += `<div class="schedule-cell" data-day="${d}" data-hour="${h}" style="background:${bg}">&nbsp;</div>`;
      });
    });
    html += '</div>';

    html += `<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <span style="font-size:13px;color:var(--turzi-muted);line-height:36px">Paint tier:</span>
      ${tiers.map(t => `<button class="secondary eTier" data-tier="${t.name}" style="padding:6px 14px;font-size:12px;border-color:${t.color || '#888'}">${t.name}</button>`).join('')}
      <button class="secondary eTier" data-tier="" style="padding:6px 14px;font-size:12px;border-color:var(--turzi-muted)">Clear</button>
      <button class="primary" id="eSchSave" style="margin-left:auto">Save Energy Schedule</button>
    </div>`;

    c.innerHTML = html;

    let paintTier = tiers[0]?.name || '';
    c.querySelectorAll('.eTier').forEach(b => b.addEventListener('click', () => {
      paintTier = b.dataset.tier;
      c.querySelectorAll('.eTier').forEach(x => { x.style.background = 'transparent'; x.style.color = ''; });
      b.style.background = paintTier ? (tierColors[paintTier] || '#888') : 'var(--turzi-muted)';
      b.style.color = '#fff';
    }));

    let painting = false;
    const paintCell = (cell) => {
      grid[cell.dataset.day][parseInt(cell.dataset.hour)] = paintTier || null;
      cell.style.background = paintTier ? (tierColors[paintTier] || '#888') : 'var(--turzi-border)';
    };
    c.querySelectorAll('.schedule-cell').forEach(cell => {
      cell.addEventListener('mousedown', (e) => { painting = true; paintCell(cell); e.preventDefault(); });
      cell.addEventListener('mouseenter', () => { if (painting) paintCell(cell); });
    });
    document.addEventListener('mouseup', () => painting = false);

    c.querySelector('#editTiers')?.addEventListener('click', () => this._showTierModal());
    c.querySelector('#eSchSave')?.addEventListener('click', async () => {
      // Convert grid to blocks
      const blocks = [];
      days.forEach(d => {
        let current = null, start = null;
        hours.forEach(h => {
          const t = grid[d][h];
          if (t !== current) {
            if (current) blocks.push({ days: [d], start: `${String(start).padStart(2,'0')}:00`, end: `${String(h).padStart(2,'0')}:00`, tier: current });
            current = t; start = h;
          }
        });
        if (current) blocks.push({ days: [d], start: `${String(start).padStart(2,'0')}:00`, end: '23:59', tier: current });
      });
      await this._ws('turzi_thermostat/save_energy_rates', { tiers: tiers, schedule: blocks });
      await this._loadConfig();
      alert('Energy schedule saved!');
    });
  }

  _showTierModal() {
    const existing = this._config?.energy_rates?.tiers || [];
    const s = this.shadowRoot;
    const div = document.createElement('div');
    div.className = 'modal-backdrop';
    const colors = ['#22c55e','#f59e0b','#ef4444','#3b82f6','#8b5cf6'];
    let tiers = existing.length ? [...existing] : [{ name: 'Low', color: colors[0] }, { name: 'Normal', color: colors[1] }, { name: 'High', color: colors[2] }];
    const renderTiers = () => {
      div.querySelector('#tierList').innerHTML = tiers.map((t, i) => `<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <input type="color" value="${t.color}" data-i="${i}" class="tColor" style="width:36px;height:36px;border:none;background:none;cursor:pointer">
        <input value="${t.name}" data-i="${i}" class="tName" style="flex:1;padding:8px;border-radius:8px;border:1px solid var(--turzi-border);background:var(--turzi-bg);color:var(--turzi-text)">
        <button class="secondary tDel" data-i="${i}" style="padding:4px 8px">✕</button></div>`).join('');
      div.querySelectorAll('.tName').forEach(el => el.addEventListener('input', () => { tiers[el.dataset.i].name = el.value; }));
      div.querySelectorAll('.tColor').forEach(el => el.addEventListener('input', () => { tiers[el.dataset.i].color = el.value; }));
      div.querySelectorAll('.tDel').forEach(el => el.addEventListener('click', () => { tiers.splice(el.dataset.i, 1); renderTiers(); }));
    };
    div.innerHTML = `<div class="modal"><h2>Energy Rate Tiers</h2><p style="color:var(--turzi-muted);font-size:13px;margin-bottom:16px">Define your tiers from lowest to highest rate.</p>
      <div id="tierList"></div>
      <button class="secondary" id="tierAdd" style="margin-top:8px">+ Add Tier</button>
      <div class="btn-row"><button class="secondary" id="tierCancel">Cancel</button><button class="primary" id="tierSave">Save</button></div></div>`;
    s.appendChild(div);
    renderTiers();
    div.querySelector('#tierAdd').addEventListener('click', () => { tiers.push({ name: '', color: colors[tiers.length % colors.length] }); renderTiers(); });
    div.querySelector('#tierCancel').addEventListener('click', () => div.remove());
    div.querySelector('#tierSave').addEventListener('click', async () => {
      const validTiers = tiers.filter(t => t.name.trim());
      await this._ws('turzi_thermostat/save_energy_rates', { tiers: validTiers, schedule: this._config?.energy_rates?.schedule || [] });
      div.remove(); await this._loadConfig(); this._setTab('energy');
    });
  }

  // === STRATEGY TAB ===
  _renderStrategy(c) {
    const d = this._dashboard;
    const spaces = d?.spaces || {};
    if (!Object.keys(spaces).length) { c.innerHTML = this._emptyState('No data yet', 'Add zones and wait for the first update cycle.'); return; }
    let html = '<h2 style="margin-bottom:20px">AI Strategy</h2>';
    for (const [id, sp] of Object.entries(spaces)) {
      const action = sp.hvac_action || 'idle';
      const score = sp.comfort_score != null ? sp.comfort_score : '--';
      html += `<div class="strategy-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <span class="strategy-action">${sp.name}</span>
          <span class="badge ${action}">${ACTION_LABELS[action] || action}</span></div>
        <div class="strategy-reason">${sp.strategy_reason || 'Waiting for data...'}</div>
        <div style="display:flex;gap:12px;margin-top:12px;flex-wrap:wrap">
          <span class="confidence-badge">Comfort: ${score}${score !== '--' ? '/100' : ''}</span>
          ${sp.energy_tier ? `<span class="confidence-badge">${sp.energy_tier} rate</span>` : ''}
        </div></div>`;
    }
    c.innerHTML = html;
  }

  // === SETTINGS TAB ===
  async _renderSettings(c) {
    const settings = this._config?.settings || {};
    const ents = await this._loadEntities();
    const switches = ents?.switches || [];

    const currentMode = settings.seasonal_mode || 'auto';
    const currentSwitch = settings.seasonal_switch_entity || '';

    c.innerHTML = `
      <h2 style="margin-bottom:24px">Settings</h2>

      <div class="card" style="max-width:520px">
        <div class="card-header"><span class="card-title">🌡️ Seasonal Mode</span></div>
        <p style="color:var(--turzi-muted);font-size:13px;margin:0 0 16px">
          Controls whether the system is allowed to heat, cool, or both.
          In <strong>Winter</strong> mode only heating is active.
          In <strong>Summer</strong> mode only cooling is active.
          <strong>Auto</strong> allows both based on conditions.
        </p>
        <div class="form-group">
          <label>Mode</label>
          <select id="sSeasonalMode">
            <option value="auto" ${currentMode === 'auto' ? 'selected' : ''}>Auto (heat &amp; cool)</option>
            <option value="winter" ${currentMode === 'winter' ? 'selected' : ''}>❄️ Winter (heating only)</option>
            <option value="summer" ${currentMode === 'summer' ? 'selected' : ''}>☀️ Summer (cooling only)</option>
          </select>
        </div>
        <div class="form-group">
          <label>HVAC Season Switch <span style="color:var(--turzi-muted);font-size:12px">(optional)</span></label>
          <p style="color:var(--turzi-muted);font-size:12px;margin:0 0 8px">
            If your HVAC has a physical winter/summer switch entity, select it here.
            The system will automatically toggle it (ON = winter, OFF = summer).
          </p>
          ${this._ssHtml('sSeasonalSwitch', switches, currentSwitch, 'Search switches...')}
        </div>
      </div>

      <div class="card" style="max-width:520px;margin-top:16px">
        <div class="card-header"><span class="card-title">🧠 Comfort Engine</span></div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
            <input type="checkbox" id="sHumidity" ${settings.humidity_compensation !== false ? 'checked' : ''}
              style="width:18px;height:18px;accent-color:var(--turzi-primary)">
            Humidity compensation
          </label>
          <p style="color:var(--turzi-muted);font-size:12px;margin:6px 0 0">Adjusts target temp based on indoor humidity (high humidity feels warmer)</p>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
            <input type="checkbox" id="sWind" ${settings.wind_compensation !== false ? 'checked' : ''}
              style="width:18px;height:18px;accent-color:var(--turzi-primary)">
            Wind compensation
          </label>
          <p style="color:var(--turzi-muted);font-size:12px;margin:6px 0 0">Adjusts target temp based on outdoor wind speed (wind makes it feel colder)</p>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
            <input type="checkbox" id="sPrecon" ${settings.preconditioning_enabled !== false ? 'checked' : ''}
              style="width:18px;height:18px;accent-color:var(--turzi-primary)">
            Preconditioning
          </label>
          <p style="color:var(--turzi-muted);font-size:12px;margin:6px 0 0">Starts heating/cooling before a schedule transition so the room is ready on time</p>
        </div>
      </div>

      <div style="max-width:520px;margin-top:20px;display:flex;justify-content:flex-end">
        <button class="primary" id="sSave">Save Settings</button>
      </div>`;

    this._initSearchableSelects(c);

    c.querySelector('#sSave').addEventListener('click', async () => {
      const newSettings = {
        seasonal_mode: c.querySelector('#sSeasonalMode').value,
        seasonal_switch_entity: c.querySelector('#sSeasonalSwitch-val').value || null,
        humidity_compensation: c.querySelector('#sHumidity').checked,
        wind_compensation: c.querySelector('#sWind').checked,
        preconditioning_enabled: c.querySelector('#sPrecon').checked,
      };
      await this._ws('turzi_thermostat/save_settings', { settings: newSettings });
      await this._loadConfig();
      // Show brief save confirmation
      const btn = c.querySelector('#sSave');
      if (btn) { btn.textContent = '✓ Saved'; btn.disabled = true; setTimeout(() => { btn.textContent = 'Save Settings'; btn.disabled = false; }, 2000); }
    });
  }

  _emptyState(title, desc, btnText = null, btnAction = null) {
    return `<div class="empty-state"><h2>${title}</h2><p>${desc}</p>
      ${btnText ? `<button class="primary" data-action="${btnAction}">${btnText}</button>` : ''}</div>`;
  }
}

customElements.define('turzi-thermostat-panel', TurziThermostatPanel);
