# Home Assistant Configuration

## Documentation
**File structure:**
- `AGENTS.md` (this file) - Quick reference for AI assistants
  - `CLAUDE.md` → symlink to AGENTS.md
- `ha-design.md` - Detailed design docs, implementation checklists
  - `README.md` → symlink to ha-design.md
- `bird-notifier.md` - BirdNET pipeline setup and configuration

## Git Conventions
- Don't override the git author - use the repo owner's configured identity
- Keep commit messages short and simple (one line, ~50 chars)
- No verbose bullet lists or multi-paragraph commit messages

## Overview
This is the Home Assistant configuration for a residential smart home in Wisconsin. The HA instance runs on a local server and is accessible at `http://homeassistant:8123`.

## MCP Integration
Claude has access to Home Assistant via MCP (Model Context Protocol) tools:

**Available MCP tools:**
- `mcp__home-assistant__GetLiveContext` - Get current state of all devices/sensors
- `mcp__home-assistant__HassTurnOn/Off` - Control switches, lights, etc.
- `mcp__home-assistant__HassClimateSetTemperature` - Set thermostat temp
- `mcp__home-assistant__HassLightSet` - Control lights (brightness, color)
- Various media player controls

**MCP limitations:**
- Cannot read automation definitions (use file access instead)
- Cannot read/write config files (use Samba mount instead)
- Good for: checking current state, controlling devices
- Not for: editing automations, template sensors, or config

## File Access (Samba)
Config files are mounted via Samba at `/Volumes/config/` on the Mac.

Key files:
- `/Volumes/config/configuration.yaml` - Main config
- `/Volumes/config/template_sensors.yaml` - Template sensors
- `/Volumes/config/automations.yaml` - Automations
- `/Volumes/config/input_numbers.yaml` - Input number helpers
- `/Volumes/config/input_booleans.yaml` - Input boolean helpers

**After editing files, reload in HA:**
Settings → Developer Tools → YAML → Reload (select appropriate category)

## Key Entities

### Climate
- `climate.t6_pro_z_wave_programmable_thermostat` - Main thermostat (Honeywell T6 Pro Z-Wave)
  - Supports modes: heat, cool, auto, off
  - Fan modes: Auto low, Low, Circulation

### Sensors
| Entity | Description |
|--------|-------------|
| `sensor.indoor_outdoor_meter_6a87_temperature` | Outdoor temperature (primary, reliable) |
| `sensor.indoor_outdoor_meter_6a87_humidity` | Outdoor humidity |
| `sensor.t6_pro_z_wave_programmable_thermostat_air_temperature` | Indoor temperature |
| `sensor.t6_pro_z_wave_programmable_thermostat_humidity` | Indoor humidity |

### Smart HVAC v2 Template Sensors
| Entity | Description |
|--------|-------------|
| `sensor.smart_heating_target` | Heat target from input_numbers, +1°F if humidity < 30% |
| `sensor.smart_cooling_target` | Cool target from input_numbers, adjusted down for high humidity |
| `sensor.smart_hvac_mode` | Desired mode with hysteresis and preconditioning logic |
| `sensor.outdoor_temp_fallback` | Outdoor temp: local sensor → NWS → 65°F default |
| `sensor.forecast_high_today` | Today's forecast high from NWS |
| `sensor.forecast_low_today` | Today's forecast low from NWS |

### Input Helpers
| Entity | Purpose |
|--------|---------|
| `input_boolean.hvac_override_enabled` | Activates temperature hold |
| `input_number.comfort_heating_day` | Day heating target (default 72°F) |
| `input_number.comfort_heating_night` | Night heating target (default 70°F) |
| `input_number.comfort_cooling_day` | Day cooling target (default 76°F) |
| `input_number.comfort_cooling_night` | Night cooling target (default 74°F) |
| `input_number.hvac_hold_temp` | Target temp during hold (60-85°F) |
| `input_number.hvac_override_duration` | Hold duration in hours (1-744) |

## Automations

### Smart HVAC v2 (`automation.smart_hvac_v2`)
**Status:** DISABLED (awaiting testing)

Intelligent HVAC control with hysteresis, preconditioning, and sensor fallbacks.

**Core Logic:**
- Outdoor < 55°F → HEAT mode (exits at 58°F if currently heating)
- Outdoor > 72°F → COOL mode (exits at 69°F if currently cooling)
- 55-72°F (Shoulder) → Heat/cool based on indoor temp, or OFF if comfortable

**Preconditioning (uses NWS forecast):**
- **Precool:** Morning (6-10am) + outdoor < 65°F + forecast high > 80°F → cool to target-2°F
- **Skip-heat:** Would heat but forecast shows warming to 60°F+ within hours → stay OFF

**Fallback Chain (if sensors unavailable):**
1. Local outdoor sensor (`sensor.indoor_outdoor_meter_6a87_temperature`)
2. NWS current temp (`weather.kmsn` temperature attribute)
3. Indoor-temp-based fallback:
   - Indoor < heat target → assume 40°F (will heat)
   - Indoor > cool target → assume 85°F (will cool)
   - Indoor comfortable → assume 65°F (shoulder mode)

**Fallback Behavior:** When all outdoor sensors fail, system maintains comfort targets like a basic thermostat - heats when indoor drops below heat target, cools when indoor rises above cool target.

**Triggers:** Every 15 min, or when `sensor.smart_hvac_mode` changes

**Conditions:** Requires `input_boolean.hvac_override_enabled` = off

### Temperature Hold System
Two automations work together:

**HVAC Hold Set Temperature** (`automation.hvac_hold_set_temperature`)
- Triggers when hold activates OR hold temp is adjusted
- Sets thermostat to `input_number.hvac_hold_temp`

**Resume HVAC After Override** (`automation.resume_hvac_after_override`)
- Starts timer when hold activates OR duration is adjusted
- Auto-clears hold after `input_number.hvac_override_duration` hours
- Timer restarts if duration is changed while holding

### Summer Night Fan Circulation (`automation.summer_night_fan_circulation`)
**Status:** Enabled

On cool summer nights (outdoor > 60°F) when HVAC is off for 30+ min, runs circulation fan for 1 hour to pull cool basement air up.

### ERV Control (RenewAire)
**Setup:** Central ERV controlled by smart outlet (`switch.renewaire`). Bathroom wall switches also control it but are wired through the smart outlet.

Two automations manage ERV based on outdoor conditions:
- **ERV Disable** (`automation.erv_disable_hot_humid_outside`): Turns OFF when outdoor > 75°F AND humidity > 65%
- **ERV Enable** (`automation.erv_enable_acceptable_outside`): Turns ON otherwise

**Rationale:** In hot/humid summer, don't bring in outdoor air (fights AC). Otherwise, let bathroom switches work normally for ventilation.

### Septic Pump Alarm Alert (`automation.septic_pump_alarm_alert`)
**Status:** Enabled

Sends critical mobile notification when vibration sensor detects septic pump alarm.

**Setup:**
- ESP32 with vibration sensor (`binary_sensor.vibrationsensor1_vibration_sensor`) attached to septic alarm housing
- When pump alarm activates, vibration from buzzer triggers sensor

**Notification:**
- Critical alert (bypasses Do Not Disturb on iOS)
- Mode: single (prevents spam during continuous alarm)

### Doorbell Chime and Announcement (`automation.doorbell_chime_announcement`)
**Status:** Enabled

Plays loud doorbell chime and announces when Nest doorbell is pressed.

**Setup:**
- Nest Doorbell (Front Door) - `event.front_door_chime`
- Kitchen Echo Dot for audio output

**Actions:**
1. Saves current Echo Dot volume
2. Sets volume to 80% for audibility
3. Plays doorbell chime sound + announces "Someone is at the door!"
4. Restores original volume after 5 seconds

**Mode:** restart (interrupts in-progress announcements for new doorbell presses)

**Note:** Nest enforces a cooldown period (~30-60 seconds) between doorbell events to prevent spam. Rapid successive presses won't trigger multiple announcements.

## Day/Night Schedule
- **Day:** 6am - 11pm (hour 6-22)
- **Night:** 11pm - 6am (hour 23-5)

## BirdNET Bird Detection

### Architecture
- **Pi Zero 2 W** (192.168.50.42, hostname `birdmic`) - ReSpeaker HAT captures audio, streams RTSP via MediaMTX
- **BirdNET-Pi add-on** - Analyzes RTSP stream (`rtsp://192.168.50.42:8554/birdmic`), publishes detections to MQTT
- **Mosquitto MQTT broker** - HA add-on handling MQTT
- **ESP32-S3-BOX-3B** - Multi-page touchscreen display (ESPHome)

### Key Entities
| Entity | Description |
|--------|-------------|
| `sensor.birdnet_latest_detection` | Latest bird detection (MQTT trigger sensor) |
| `sensor.recent_bird_detections` | SQL: last 20 unique species as JSON (in `detections` attribute) |
| `sensor.recent_birds_display` | Template: parsed bird names (6) + relative times for ESP32 |
| `sensor.forecast_display` | Template: 3-day forecast via `weather.get_forecasts` service (trigger-based) |
| `sensor.ebird_dane_county_frequencies` | REST: eBird frequency data for 521 species (48 weekly values each) |
| `input_boolean.rare_bird_alerts_enabled` | Toggle for rare bird audio alerts |

### MQTT Payload (topic: `birdnet`)
```json
{
  "CommonName": "Red-tailed Hawk",
  "ScientificName": "Buteo jamaicensis",
  "Confidence": 0.8452,
  "Date": "2026-02-22",
  "Time": "09:33:27",
  "SpeciesCode": "rethaw",
  "FlickrImage": "https://..."
}
```

### ESP32-S3-BOX-3B Display
- **Config:** `/Volumes/config/esphome/esp32-s3-box-3-2e8818.yaml`
- **IP:** 192.168.50.189

**Display Pages (swipe left/right to navigate):**
| Page | Index | Content |
|------|-------|---------|
| `bird_idle_page` | 0 | Recent 6 birds with relative times (default home page) |
| `setpoints_page` | 1 | 4 HVAC comfort targets with +/- touch buttons |
| `override_page` | 2 | Temperature hold: temp +/-, duration +/-, start/stop, automation toggle |
| `forecast_page` | 3 | 3-day weather outlook (day, high/low, condition) |
| `energy_page` | 4 | Current power usage vs solar production |
| `bird_page` | N/A | "Bird Detected" - auto-shows 30s on new detection, then returns |

**Touch Controls:**
- Setpoints/Hold pages have enlarged touch zones (60×45px) for reliable button presses
- Navigation: tap left/right edges to change pages
- ESPHome must have "Allow device to make Home Assistant service calls" enabled

### Pi Zero Services
- `mediamtx.service` - RTSP server
- `birdmic.service` - ffmpeg audio capture stream

### Rare Bird Alerts (`automation.rare_bird_tts_alert`)
**Status:** Enabled

Announces via Alexa and sends mobile notification when BirdNET detects a rare bird (< 5% eBird frequency for current week).

**How it works:**
1. BirdNET detection triggers automation
2. Looks up `SpeciesCode` in `sensor.ebird_dane_county_frequencies` for current week (0-47)
3. If frequency < 5% and confidence ≥ 70%:
   - Announces via Kitchen Echo Dot
   - Sends push notification to iPhone with bird name and confidence %
4. Toggle with `input_boolean.rare_bird_alerts_enabled`

**Data source:** eBird bar chart for Dane County (US-WI-025)
- Frequency JSON: `/config/dane_county_frequencies.json` (521 species)
- Rarity script: `/config/scripts/check_rare_bird.py` (returns frequency for species)
- Parser script: `~/src/homeassistant-local/parse_ebird_barchart.py`
- Taxonomy: `~/src/homeassistant-local/eBird_taxonomy_v2025.csv`

**Implementation:**
- `shell_command.set_bird_code` writes species code to `/config/.last_bird_code`
- `sensor.bird_rarity_check` runs Python script, returns frequency (0.0-1.0)
- Automation triggers notification if frequency < 0.05

**Week index calculation:** `(month - 1) * 4 + min((day - 1) // 7, 3)`

**Annual maintenance:** Re-download eBird bar chart in January from https://ebird.org/barchart?r=US-WI-025 and re-run parser

## Common Tasks

### Check current conditions
Use MCP: `mcp__home-assistant__GetLiveContext`

Or via API:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://homeassistant:8123/api/states" | jq '[.[] | select(.entity_id | test("smart_hvac|smart_heating|smart_cooling|indoor_outdoor_meter|t6_pro.*temperature|t6_pro.*humidity"))]'
```

### Enable Smart HVAC v2 for testing
```bash
# Via MCP tools:
# 1. Turn off override: mcp__home-assistant__HassTurnOff with name "Pause Comfort HVAC Automation"
# 2. Enable automation via HA UI: Settings → Automations → Smart HVAC v2 → Enable

# Or via API:
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://homeassistant:8123/api/services/automation/turn_on" \
  -d '{"entity_id": "automation.smart_hvac_v2"}'
```

### Reload after editing config files
Developer Tools → YAML → Select category → Reload

## Notes
- Template sensors cannot be created via REST API - must edit `template_sensors.yaml` and reload
- Input helpers cannot be created via REST API - use UI or edit yaml files
- Automations CAN be created/updated via REST API at `/api/config/automation/config/{id}`
- Always use local outdoor sensor (`sensor.indoor_outdoor_meter_6a87_*`), not Tomorrow.io
- Wisconsin climate: real shoulder seasons in spring/fall make smart HVAC logic worthwhile
- SQL sensor configured in `configuration.yaml` queries HA database for bird history
- Detailed design documentation: see `ha-design.md` in the project repo
- **HA 2023.12+ breaking change:** Weather forecast data must use `weather.get_forecasts` service via trigger-based template sensors (forecast attribute no longer populated automatically)
