# 🌡️ Turzi Smart Thermostat

**An AI-powered Home Assistant integration that keeps you comfortable — automatically.**

Stop dialing your thermostat up and down. Turzi Smart Thermostat learns your home's thermal behaviour, watches the weather, respects your energy rate schedule, and makes intelligent heating/cooling decisions so every room feels right — without you lifting a finger.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

### 🧠 Predictive Comfort Control
- **Weather-aware**: Automatically adjusts targets based on outdoor temperature, humidity, wind, and forecast — pre-heats before a cold front arrives, pre-cools before a heatwave.
- **Humidity compensation**: Adjusts effective temperature targets so 21°C at 80% humidity doesn't feel like a sauna.
- **Wind chill awareness**: Increases heating in drafty conditions when outdoor wind is high.
- **Comfort scoring**: PMV-based (ISO 7730) comfort index per room — see at a glance how comfortable each space actually is, not just the thermostat number.

### 🏠 Per-Space Intelligence
- Each room/zone gets its own climate entity with individual control.
- Supports **any combination** of HVAC system types across zones:

| System | Use Case | Thermal Response |
|---|---|---|
| 🔥 **Floor Heating** | Radiant floor systems | Slow & steady — starts early |
| 🌡️ **Radiator** | Hot water radiators | Moderate response |
| 💨 **Fan-Coil** | Ducted or wall fan-coil units | Fast response |
| ❄️ **Split A/C** | Mini-split heat pumps / A/C | Fastest response |

The strategy engine knows that floor heating needs 2 hours of lead time while a split A/C needs 10 minutes — and plans accordingly.

### 📅 Simple, Visual Scheduling
- **Weekly schedule grid**: Click and drag to paint comfort modes across the week.
- **Modes**: Comfort, Eco, Sleep, Away, Off — each with sensible temperature offsets.
- **Templates**: One-click presets like "Office hours", "Always home", "Night owl".
- **Per-zone schedules**: The living room and bedroom can have completely different schedules.

### ⚡ Energy Rate Awareness (Optional)
- Define your energy rate tiers by name (e.g., "Low", "Normal", "High") and assign them to time slots.
- The strategy engine shifts heating/cooling load to lower-rate periods when possible.
- Pre-heats during "Low" so it can coast through "High" — your comfort stays the same, your bill drops.
- **Fully optional** — if you have a flat rate or don't want to configure this, the thermostat works perfectly without it.

### 🤖 AI Strategy Engine
- Proposes heating/cooling strategies per zone with clear reasoning.
- **Learns over time**: After ~7 days of data, replaces default thermal models with actual measured heat-up/cool-down rates for your specific home.
- **Transparent**: Every decision is explained — "Pre-heating because Eco→Comfort transition in 45 min and floor heating needs 120 min lead time."
- **Graceful degradation**: Works great on day one with sensible defaults; gets smarter with data.

### 🖥️ Dedicated Sidebar Panel
- Full configuration and monitoring UI — no digging through YAML or options flows.
- **5 tabs**: Dashboard, Zones, Schedule, Energy, AI Strategy.
- Matches your Home Assistant theme (dark/light mode).
- Works on desktop and mobile (HA companion app).

---

## 📦 Installation

### HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Click the **⋮** menu → **Custom repositories**.
3. Add `https://github.com/turzi-org/turzi-smart-thermostat` with category **Integration**.
4. Search for "Turzi Smart Thermostat" and click **Install**.
5. **Restart** Home Assistant.

### Manual

1. Download the latest release from the [Releases](https://github.com/turzi-org/turzi-smart-thermostat/releases) page.
2. Copy the `custom_components/turzi_thermostat` folder to your `<config>/custom_components/` directory.
3. **Restart** Home Assistant.

---

## ⚙️ Setup

### 1. Add the Integration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Turzi Smart Thermostat**.
3. Enter a name (e.g., "My Home") and select your **weather entity** (used for forecasts).
4. Click **Submit**.

### 2. Open the Sidebar Panel

After setup, a new **🌡️ Smart Thermostat** entry appears in your sidebar. Click it to open the configuration panel.

### 3. Add Your Zones

In the **Zones** tab:
1. Click **Add Zone**.
2. Give it a name (e.g., "Living Room").
3. Select the **HVAC system type** (floor heating, radiator, fan-coil, split A/C).
4. Pick your **temperature sensor** and optionally a **humidity sensor**.
5. Select the **heating output** (a `switch` entity for valves/relays, or an existing `climate` entity for smart units).
6. Optionally set a **cooling output** for systems that can cool.
7. Set your **target comfort temperature** (default: 21°C).

Repeat for each room.

### 4. Configure Your Schedule

In the **Schedule** tab:
- Select a zone from the dropdown.
- Paint schedule blocks on the weekly grid by clicking and dragging.
- Use **mode colors**: 🟢 Comfort, 🔵 Eco, 🟣 Sleep, ⚪ Away, ⚫ Off.
- Or apply a **template** for quick setup.

### 5. (Optional) Configure Energy Rate Tiers

In the **Energy** tab:
1. Define your rate tiers (e.g., "Low", "Normal", "High") with colors.
2. Paint the weekly grid with your rate schedule.
3. The strategy engine will automatically optimize around your rates.

> **Skip this step** if you have a flat energy rate — the thermostat works great without it.

---

## 🔧 How It Works

```
Every 60 seconds:
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  1. Read indoor sensors (temp + humidity per zone)           │
│  2. Fetch weather (current + hourly + daily forecast)       │
│  3. Check schedule → what mode should each zone be in?      │
│  4. Run comfort model → adjust targets for humidity/wind    │
│  5. Run strategy engine:                                    │
│     • Should we pre-condition for an upcoming transition?   │
│     • Can we shift load to a lower energy tier?             │
│     • Is the weather about to change significantly?         │
│  6. Command the underlying switch/climate entity             │
│  7. Update all HA entities and dashboard                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Schedule Modes

| Mode | Default Offset | Description |
|---|---|---|
| **Comfort** | Target temp | Full comfort — your preferred temperature |
| **Eco** | Target − 2°C | Energy saving, still acceptable |
| **Sleep** | Target − 1°C | Slightly cooler for better sleep |
| **Away** | Target − 4°C | Frost/heat protection only |
| **Off** | — | System disabled |
| **Boost** | Max heat/cool | 30 min burst, then back to schedule |

### Thermal Learning

The strategy engine starts with conservative defaults for each HVAC system type. After ~7 days of operation, it begins learning your home's actual thermal characteristics:

- **How fast does this room heat up?** (depends on insulation, window area, room size)
- **How fast does it cool down?** (depends on outdoor exposure, ventilation)
- **How much does outdoor wind affect indoor temp?**

These learned rates replace the defaults, making pre-conditioning timing increasingly accurate.

---

## 🏗️ Entities Created

### Climate Entities (one per zone)
- `climate.turzi_{zone_name}` — Full thermostat with AUTO/HEAT/COOL modes and preset support.

### Sensor Entities (per zone)
| Entity | Description |
|---|---|
| `sensor.turzi_{zone}_comfort_score` | PMV-based comfort index (0–100) |
| `sensor.turzi_{zone}_effective_target` | Final computed target temperature |
| `sensor.turzi_{zone}_schedule_mode` | Current schedule mode |
| `sensor.turzi_{zone}_energy_tier` | Current energy rate tier |
| `sensor.turzi_{zone}_strategy` | Human-readable strategy explanation |

### Global Sensors
| Entity | Description |
|---|---|
| `sensor.turzi_outdoor_feels_like` | Computed outdoor feels-like temperature |

---

## 🤝 Supported HVAC Configurations

The integration can wrap two types of existing HA entities as zone outputs:

| Output Type | Example | How Turzi Controls It |
|---|---|---|
| **Switch** | `switch.floor_heating_valve` | Turns on/off to maintain target |
| **Climate** | `climate.bedroom_ac` | Sets target temp + HVAC mode |

You can mix and match — floor heating via a relay switch in the living room, and a split A/C climate entity in the bedroom.

---

## 📋 Requirements

- **Home Assistant** 2024.1.0 or newer
- **Recorder** integration enabled (default — needed for thermal learning)
- A **weather** integration configured (e.g., Met.no, OpenWeatherMap, AccuWeather)
- At least one **temperature sensor** per zone
- At least one **switch** or **climate** entity to control per zone

---

## 🐛 Troubleshooting

| Issue | Solution |
|---|---|
| Sidebar panel doesn't appear | Restart HA after installing the integration |
| Weather data missing | Ensure you have a weather integration configured and selected during setup |
| Thermal learning not starting | Needs ~7 days of continuous data. Check that the Recorder integration is enabled |
| Strategy shows "low confidence" | Normal for the first week. Confidence increases as the system collects more data |
| Zone not responding | Verify the underlying switch/climate entity is working independently first |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🏢 Maintainers

**Turzi LLC** — [turzi-org](https://github.com/turzi-org)
