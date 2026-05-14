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
  }

  set hass(h) {
    this._hass = h;
    if (!this._entryId && !this._findingEntry) this._init();
    if (this._tab === 'dashboard' && this._entryId) this._loadDashboard();
  }

  set panel(p) { this._panel = p; }

  async _init() {
    this._findingEntry = true;
    await this._findEntryId();
    this._findingEntry = false;
    if (this._entryId && !this._config) this._loadConfig();
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

  _setTab(t) { this._tab = t; this._render(); if (t === 'dashboard') this._loadDashboard(); }

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
        html += `<div class="card">
          <div class="card-header"><span class="card-title">${sp.name}</span><span class="badge ${badgeClass}">${ACTION_LABELS[action] || action}</span></div>
          <div class="temp-display"><span class="temp-current">${sp.current_temp != null ? sp.current_temp.toFixed(1) : '--'}</span><span class="temp-unit">°C</span>
            <div class="temp-target">Target: ${sp.target_temp != null ? sp.target_temp.toFixed(1) + '°C' : '--'}</div></div>
          <div class="meta-row"><span class="meta-label">Mode</span><span style="color:${MODE_COLORS[sp.schedule_mode] || '#fff'}">${(sp.schedule_mode || '').charAt(0).toUpperCase() + (sp.schedule_mode || '').slice(1)}</span></div>
          ${sp.energy_tier ? `<div class="meta-row"><span class="meta-label">Energy Tier</span><span>${sp.energy_tier}</span></div>` : ''}
          <div class="meta-row"><span class="meta-label">Comfort</span><span style="color:${scoreColor}">${score}${score !== '--' ? '/100' : ''}</span></div>
          ${score !== '--' ? `<div class="comfort-bar"><div class="comfort-fill" style="width:${score}%;background:${scoreColor}"></div></div>` : ''}
          ${sp.strategy_reason ? `<div class="meta-row" style="border:none;margin-top:8px"><span style="font-size:12px;color:var(--turzi-muted);font-style:italic">💡 ${sp.strategy_reason}</span></div>` : ''}
        </div>`;
      }
      html += '</div>';
    }
    c.innerHTML = html;
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
          <div class="meta-row"><span class="meta-label">Sensitivity</span><span>${sp.comfort_sensitivity}</span></div>
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
    const optionsHtml = (list, selected) => (list || []).map(e =>
      `<option value="${e.entity_id}" ${e.entity_id === selected ? 'selected' : ''}>${e.name}</option>`
    ).join('');
    div.innerHTML = `<div class="modal"><h2>${editId ? 'Edit' : 'Add'} Zone</h2>
      <div class="form-group"><label>Name</label><input id="zName" value="${existing?.name || ''}"></div>
      <div class="form-group"><label>HVAC System</label><select id="zType">
        ${['floor_heating','radiator','fan_coil','split_ac'].map(t => `<option value="${t}" ${existing?.hvac_type === t ? 'selected' : ''}>${t.replace(/_/g,' ')}</option>`).join('')}</select></div>
      <div class="form-group"><label>Temperature Sensor</label><select id="zTemp"><option value="">Select...</option>${optionsHtml(ents?.temperature_sensors, existing?.temp_sensor)}</select></div>
      <div class="form-group"><label>Humidity Sensor (optional)</label><select id="zHum"><option value="">None</option>${optionsHtml(ents?.humidity_sensors, existing?.humidity_sensor)}</select></div>
      <div class="form-group"><label>Heating Output</label><select id="zHeat"><option value="">Select...</option>${optionsHtml(ents?.heating_outputs, existing?.heating_output)}</select></div>
      <div class="form-group"><label>Cooling Output (optional)</label><select id="zCool"><option value="">None</option>${optionsHtml(ents?.cooling_outputs, existing?.cooling_output)}</select></div>
      <div class="form-group"><label>Target Temperature (°C)</label><input id="zTarget" type="number" step="0.5" min="5" max="35" value="${existing?.target_temp || 21}"></div>
      <div class="form-group"><label>Comfort Sensitivity</label><select id="zSens">
        ${['low','medium','high'].map(s => `<option value="${s}" ${existing?.comfort_sensitivity === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="btn-row">${editId ? `<button class="secondary" id="zDel" style="margin-right:auto;color:#ef4444">Delete</button>` : ''}
        <button class="secondary" id="zCancel">Cancel</button><button class="primary" id="zSave">Save</button></div></div>`;
    s.appendChild(div);
    div.querySelector('#zCancel').addEventListener('click', () => div.remove());
    div.querySelector('#zDel')?.addEventListener('click', async () => {
      await this._ws('turzi_thermostat/delete_space', { space_id: editId });
      div.remove(); await this._loadConfig(); this._setTab('zones');
    });
    div.querySelector('#zSave').addEventListener('click', async () => {
      const space = {
        name: div.querySelector('#zName').value,
        hvac_type: div.querySelector('#zType').value,
        temp_sensor: div.querySelector('#zTemp').value,
        humidity_sensor: div.querySelector('#zHum').value || null,
        heating_output: div.querySelector('#zHeat').value,
        cooling_output: div.querySelector('#zCool').value || null,
        target_temp: parseFloat(div.querySelector('#zTarget').value),
        comfort_sensitivity: div.querySelector('#zSens').value,
      };
      if (!space.name || !space.temp_sensor || !space.heating_output) { alert('Name, temp sensor, and heating output are required.'); return; }
      await this._ws('turzi_thermostat/save_spaces', { spaces: [space] });
      div.remove(); this._entities = null; await this._loadConfig(); this._setTab('zones');
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
    let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px"><h2>Energy Rate Tiers</h2><button class="primary" id="editTiers">Edit Tiers</button></div><div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">`;
    rates.tiers.forEach(t => { html += `<span class="tier-chip" style="background:${t.color || '#888'}22;color:${t.color || '#888'};border:1px solid ${t.color || '#888'}44">${t.name}</span>`; });
    html += '</div><p style="color:var(--turzi-muted);font-size:13px">Energy rate schedule painting coming in the next update.</p>';
    c.innerHTML = html;
    c.querySelector('#editTiers')?.addEventListener('click', () => this._showTierModal());
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

  _emptyState(title, desc, btnText = null, btnAction = null) {
    return `<div class="empty-state"><h2>${title}</h2><p>${desc}</p>
      ${btnText ? `<button class="primary" data-action="${btnAction}">${btnText}</button>` : ''}</div>`;
  }
}

customElements.define('turzi-thermostat-panel', TurziThermostatPanel);
