# Home Assistant Design Document

## Overview

Design and implementation notes for a Wisconsin residential smart home running Home Assistant OS.

**Key Systems:**
- Smart HVAC v2 - Intelligent heating/cooling with hysteresis, preconditioning, forecast awareness
- BirdNET - Birdsong detection via Pi Zero 2 W + ML analysis
- Energy Monitoring - Sense power meter + SolarEdge solar
- ESP32-S3-BOX-3B - Touchscreen display for status and controls

This document tracks current state, planned enhancements, and implementation details.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Home Assistant OS                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Smart HVAC   │  │ BirdNET-Pi   │  │ Energy Monitoring    │   │
│  │ Automation   │  │ Add-on       │  │ Sense + SolarEdge    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
│         ▼                 ▼                      ▼               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Template Sensors & SQL Queries              │    │
│  └─────────────────────────┬───────────────────────────────┘    │
│                            │                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Honeywell T6  │   │ ESP32-S3-BOX  │   │ Pi Zero 2 W   │
│ Z-Wave Therm  │   │ Touchscreen   │   │ Bird Mic      │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Current State (Completed)

### Smart HVAC v2
- [x] Core automation with outdoor temp-based mode selection
- [x] Hysteresis to prevent mode thrashing (heat <55°F exit 58°F, cool >72°F exit 69°F)
- [x] Day/night comfort targets via input_number helpers
- [x] Humidity-aware target adjustments (+1°F heat if dry, -1.5 to -2.5°F cool if humid)
- [x] Forecast-based preconditioning (precool morning if hot afternoon, skip-heat if warming)
- [x] Multi-level outdoor temp fallback (local sensor → NWS → indoor-based default)
- [x] Override system with auto-clear timer
- [x] Summer night fan circulation automation
- [x] ERV control based on outdoor conditions

**Status:** Automation implemented, awaiting final testing/enable

### BirdNET Pipeline
- [x] Pi Zero 2 W audio capture via ReSpeaker HAT
- [x] RTSP streaming via MediaMTX
- [x] BirdNET-Pi analysis with MQTT output
- [x] HA template sensor `sensor.birdnet_latest_detection`
- [x] Dashboard card with Flickr images

### Bird History System
- [x] SQL sensor querying HA database for unique species
- [x] `sensor.recent_bird_detections` - JSON array of last 20 unique species
- [x] `sensor.recent_birds_display` - Parsed attributes with relative times
  - `bird_1_name`, `bird_1_ago` through `bird_6_name`, `bird_6_ago`

### ESP32-S3-BOX-3B (Current)
- [x] BigBobbas custom ESPHome package
- [x] 6 swipeable pages with touch controls
- [x] Static IP: 192.168.50.189

### Temperature Hold System
- [x] `input_number.hvac_hold_temp` - Target temp during hold (60-85°F)
- [x] `input_number.hvac_override_duration` - Hold duration (1-744 hours)
- [x] `hvac_hold_set_temperature` automation - Sets thermostat when hold activates
- [x] `resume_hvac_after_override` automation - Auto-clears hold after duration

### Septic Pump Monitoring
- [x] ESP32 vibration sensor (`binary_sensor.vibrationsensor1_vibration_sensor`)
- [x] `septic_pump_alarm_alert` automation - Critical mobile notification on alarm
- [x] Bypasses Do Not Disturb on iOS

---

## Planned Enhancements

### 1. ESP32 Display Pages (6 Total)

| Index | Name | Content | Navigation |
|-------|------|---------|------------|
| 0 | `bird_idle_page` | Recent Birds list (6 species + times) | Default/home page |
| 1 | `setpoints_page` | 4 HVAC temp controls with +/- | Swipe from birds |
| 2 | `override_page` | Temperature hold with temp/duration +/- | Swipe from setpoints |
| 3 | `forecast_page` | 3-day weather outlook | Swipe from hold |
| 4 | `energy_page` | Current usage & solar production | Swipe from forecast |
| N/A | `bird_page` | "Bird Detected" - new detection alert | Auto-shows 30s, returns to previous |

#### Page Details

**bird_idle_page** (Recent Birds)
```
      Recent Birds
─────────────────────────
American Crow           2h
American Goldfinch     22h
Dark-eyed Junco        23h
Blue Jay                1d
Northern Cardinal       2d
House Sparrow           3d
```
- 28px line spacing to fit 6 birds
- Bird name uses smaller font (my_font3) for long species names

**energy_page**
```
       Energy
─────────────────────────
  ⚡ Using    1,234 W
  ☀️ Solar    2,100 W
─────────────────────────
  Net: Exporting 866 W
```
- Sensors: `sensor.sense_197666_energy`, `sensor.sense_197666_production`

**forecast_page**
```
      Forecast
─────────────────────────
Today  32/18  Snowy
Tue    28/15  Cloudy
Wed    35/22  Partly Cloudy
```
- Source: `sensor.forecast_display` (trigger-based, uses `weather.get_forecasts` service)
- Compact layout: day name at x=25, temps at x=100, condition at x=175 (left-aligned, 18 chars)

**setpoints_page**
```
    Comfort Targets
─────────────────────────
Heat Day     -  72  +
Heat Night   -  70  +
Cool Day     -  76  +
Cool Night   -  74  +
```
- Touch +/- buttons adjust `input_number.comfort_*` entities
- Step: 1°F per tap
- Enlarged touch zones (60×45px) and larger button font (my_font3) for reliability

**override_page** (Temperature Hold)
```
    Temperature Hold
─────────────────────────
   -       72 F       +
   -       4 hr       +
     [ START HOLD ]
       [ Auto ON ]
```
- Top row: Hold temperature +/- (`input_number.hvac_hold_temp`)
- Second row: Duration +/- (`input_number.hvac_override_duration`)
- START/STOP HOLD button toggles `input_boolean.hvac_override_enabled`
- Auto ON/OFF button enables/disables `automation.smart_hvac_v2`
- Enlarged touch zones (80×50px for +/-, 200×45px for buttons)

#### Swipe Navigation
- Tap right edge: next page (birds → setpoints → hold → forecast → energy → birds)
- Tap left edge: previous page
- Bird detection interrupts any page, shows bird_page for 30s, returns to previous
- ESPHome must have "Allow device to make Home Assistant service calls" enabled for buttons

### 2. TTS Announcements for Rare Birds (Deferred)

**Challenge:** Bird rarity is seasonal in Wisconsin:
- Warblers are rare most of year but common during spring/fall migration
- Some species are year-round residents vs seasonal visitors
- A simple "not seen recently" check doesn't capture true rarity

**Potential Solutions:**
- eBird API integration for regional frequency data (complex)
- Seasonal rare species lists (maintenance burden)
- Machine learning on local detection history (overkill)

**Current Status:** Deferred until a practical rarity data source is identified.

**When Implemented:**
- Trigger: High confidence detection (≥70%)
- Condition: Species is seasonally rare for current date
- Action: TTS announcement via ESP32 speaker (Piper TTS)

### 3. Font Improvements

**Current Limitation:**
BigBobbas package uses limited MDI icon font. Missing icons for:
- Bird (`\U000F0917`)
- Weather conditions
- Temperature/thermometer
- Solar/energy

**Options to Explore:**

| Option | Pros | Cons |
|--------|------|------|
| **A. Custom font file** | Full MDI icon set | Larger firmware, complex setup |
| **B. Material Symbols** | Modern icons, variable weight | Different codepoints than MDI |
| **C. PNG/bitmap icons** | Exact icons wanted | Uses more memory, static size |
| **D. Text substitutes** | No changes needed | Less visual appeal |

**Recommended Approach:**
1. Start with text substitutes (current)
2. Create custom font with just needed icons (~20 glyphs):
   - Bird, thermometer, sun, cloud, snow, rain
   - Plus, minus, power, home
   - Lightning bolt (energy)
3. Use ESPHome `font:` with `glyphs:` to subset

**Font Resources:**
- MDI icons: https://pictogrammers.com/library/mdi/
- ESPHome font docs: https://esphome.io/components/font.html
- Google Fonts (for text): Roboto, Inter, or system fonts

---

## Entity Reference

### Bird Detection
| Entity | Purpose |
|--------|---------|
| `sensor.birdnet_latest_detection` | Current detection (MQTT trigger) |
| `sensor.recent_bird_detections` | SQL: last 20 unique species JSON |
| `sensor.recent_birds_display` | Template: parsed for ESP32 display |

### Energy
| Entity | Purpose |
|--------|---------|
| `sensor.sense_197666_energy` | Current home power usage (W) |
| `sensor.sense_197666_production` | Current solar production (W) |

### Weather
| Entity | Purpose |
|--------|---------|
| `weather.kmsn` | NWS weather entity |
| `sensor.forecast_high_today` | Template: today's high |
| `sensor.forecast_low_today` | Template: today's low |
| `sensor.forecast_display` | Trigger-based: 3-day forecast via `weather.get_forecasts` service |

**Note:** HA 2023.12+ removed forecast attribute from weather entities. Must use `weather.get_forecasts` service via trigger-based template sensors.

### HVAC Controls
| Entity | Purpose |
|--------|---------|
| `input_number.comfort_heating_day` | Heat target daytime (°F) |
| `input_number.comfort_heating_night` | Heat target nighttime (°F) |
| `input_number.comfort_cooling_day` | Cool target daytime (°F) |
| `input_number.comfort_cooling_night` | Cool target nighttime (°F) |
| `input_number.hvac_hold_temp` | Target temp during hold (60-85°F) |
| `input_number.hvac_override_duration` | Hold duration in hours (1-744) |
| `input_boolean.hvac_override_enabled` | Activates temperature hold |
| `automation.smart_hvac_v2` | Main HVAC automation (can be disabled) |

### Septic Monitoring
| Entity | Purpose |
|--------|---------|
| `binary_sensor.vibrationsensor1_vibration_sensor` | ESPHome vibration sensor on septic alarm |

---

## Implementation Checklist

### Phase 1: Core Display Pages ✓
- [x] Bird history SQL sensor
- [x] Recent birds template sensor (6 birds)
- [x] Update bird_idle_page with 6-bird list (28px spacing)
- [x] Add energy_page (usage vs solar, net import/export)
- [x] Add forecast_page (3-day outlook, compact layout)
- [x] Add forecast_display trigger-based template sensor
- [x] Implement swipe navigation (tap left/right edges)
- [x] Reorder pages: birds → setpoints → hold → forecast → energy

### Phase 2: HVAC Controls ✓
- [x] Add setpoints_page with touch +/-
- [x] Add override_page (hold) with temp/duration controls
- [x] Create hold automations (set temp, auto-clear timer)
- [x] Enlarge touch zones on setpoints and hold pages (60×45px buttons)
- [x] Use larger font (my_font3) for buttons
- [x] Deploy ESPHome update & test touch responsiveness

### Phase 3: TTS & Polish ✓
- [x] Create rare bird TTS automation (uses eBird seasonal frequency data)
- [x] Rare bird alerts via Alexa (ESP32 TTS had format issues)
- [ ] Explore custom font options
- [ ] Add icons to pages

### Phase 4: Future Ideas
- [ ] Daily species summary notification
- [ ] Seasonal tracking dashboard
- [x] eBird integration for rarity data (REST sensor + 521 species frequency JSON)

---

## Files Modified

| File | Changes |
|------|---------|
| `/Volumes/config/esphome/esp32-s3-box-3-2e8818.yaml` | 6 pages, swipe nav, touch controls |
| `/Volumes/config/template_sensors.yaml` | recent_birds_display, forecast_display |
| `/Volumes/config/configuration.yaml` | SQL sensor for bird history, python_script integration |
| `/Volumes/config/input_numbers.yaml` | hvac_hold_temp added |
| `/Volumes/config/input_booleans.yaml` | rare_bird_alerts_enabled toggle |
| `/Volumes/config/automations.yaml` | Hold system, rare bird TTS alert, septic alarm |
| `/Volumes/config/esphome/vibration-sensor.yaml` | ESP32 vibration sensor for septic alarm |
| `/Volumes/config/dane_county_frequencies.json` | eBird frequency data (521 species, 48 weeks) |
| `/Volumes/config/scripts/check_rare_bird.py` | Rare bird rarity check script |

---

## Key Details

| Item | Value |
|------|-------|
| Pi hostname | birdmic (192.168.50.42) |
| ESP32-S3-BOX-3B IP | 192.168.50.189 |
| HA timezone | America/Chicago |
| Location | Sun Prairie, Wisconsin |
| Display resolution | 320x240 (S3-BOX-3B) |
| Touch | Capacitive, multi-touch supported |

## Known Limitations

- **Flickr images on ESP32**: HTTP client can't fetch (use HA dashboard instead)
- **BigBobbas font**: Limited MDI icons (bird icon missing)
- **mDNS**: Use IP addresses, not .local hostnames
- **State size limit**: SQL JSON stored in attribute, not state
- **HA 2023.12+ forecast breaking change**: Weather entities no longer have `forecast` attribute; must use `weather.get_forecasts` service via trigger-based template sensors
- **ESPHome service calls**: Must enable "Allow device to make Home Assistant service calls" in ESPHome integration settings for touch buttons to work
