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

## Current State

### Smart HVAC v2
- [x] Core automation with outdoor temp-based mode selection
- [x] Hysteresis to prevent mode thrashing (heat exits at 58°F or indoor > cool target; cool exits at 69°F or indoor < heat target)
- [x] Day/night comfort targets via input_number helpers
- [x] Humidity-aware target adjustments (+1°F heat if dry, -1.5 to -2.5°F cool if humid)
- [x] Forecast-based preconditioning (precool morning if hot afternoon, skip-heat if warming)
- [x] Multi-level outdoor temp fallback (local sensor → NWS → indoor-based default)
- [x] Override system with auto-clear timer
- [x] Summer night fan circulation automation
- [x] ERV control based on outdoor conditions

**Status:** Enabled and running

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

### ESP32-S3-BOX-3B
- [x] BigBobbas custom ESPHome package
- [x] 6 swipeable pages with touch controls
- [x] Static IP: 192.168.50.189

**Display Pages (6 Total):**

| Index | Name | Content | Navigation |
|-------|------|---------|------------|
| 0 | `bird_idle_page` | Recent Birds list (6 species + times) | Default/home page |
| 1 | `setpoints_page` | 4 HVAC temp controls with +/- | Swipe from birds |
| 2 | `override_page` | Temperature hold with temp/duration +/- | Swipe from setpoints |
| 3 | `forecast_page` | 3-day weather outlook | Swipe from forecast |
| 4 | `energy_page` | Current usage & solar production | Swipe from forecast |
| N/A | `bird_page` | "Bird Detected" - new detection alert | Auto-shows 30s, returns to previous |

**Navigation:**
- Tap right edge: next page (birds → setpoints → hold → forecast → energy → birds)
- Tap left edge: previous page
- Bird detection interrupts any page, shows bird_page for 30s, returns to previous
- Enlarged touch zones (60×45px setpoints, 80×50px hold) for reliable button presses
- ESPHome must have "Allow device to make Home Assistant service calls" enabled

### Temperature Hold System
- [x] `input_number.hvac_hold_temp` - Target temp during hold (60-85°F)
- [x] `input_number.hvac_override_duration` - Hold duration (1-744 hours)
- [x] `hvac_hold_set_temperature` automation - Sets thermostat when hold activates
- [x] `resume_hvac_after_override` automation - Auto-clears hold after duration

### Septic Pump Monitoring
- [x] ESP32 vibration sensor (`binary_sensor.vibrationsensor1_vibration_sensor`)
- [x] `septic_pump_alarm_alert` automation - Critical mobile notification on alarm
- [x] Bypasses Do Not Disturb on iOS

### Doorbell Notifications
- [x] Nest Doorbell (Front Door) - `event.front_door_chime`
- [x] `doorbell_chime_announcement` automation - Plays chime + voice announcement
- [x] Volume control - Saves/restores Echo Dot volume (boosts to 80% for doorbell)
- [x] SSML audio - Alexa doorbell sound from sound library
- [x] Mode: restart (handles Nest's built-in cooldown period)

### Rare Bird Alerts
- [x] eBird frequency data integration - 521 species, 48 weekly values
- [x] `rare_bird_tts_alert` automation - Announces and notifies for rare birds (< 5% frequency)
- [x] TTS announcement via Kitchen Echo Dot
- [x] Mobile push notification with bird name and confidence %
- [x] Toggle with `input_boolean.rare_bird_alerts_enabled`
- [x] Minimum 70% confidence threshold to reduce false positives

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

### Doorbell
| Entity | Purpose |
|--------|---------|
| `event.front_door_chime` | Nest Doorbell chime event (fires on button press) |
| `media_player.kitchen_echo_dot` | Echo Dot for doorbell chime/announcement |

---

## Future Ideas
- Daily species summary notification
- Seasonal tracking dashboard

---

## Files Modified

| File | Changes |
|------|---------|
| `/Volumes/config/esphome/esp32-s3-box-3-2e8818.yaml` | 6 pages, swipe nav, touch controls |
| `/Volumes/config/template_sensors.yaml` | recent_birds_display, forecast_display |
| `/Volumes/config/configuration.yaml` | SQL sensor for bird history, python_script integration |
| `/Volumes/config/input_numbers.yaml` | hvac_hold_temp added |
| `/Volumes/config/input_booleans.yaml` | rare_bird_alerts_enabled toggle |
| `/Volumes/config/automations.yaml` | Hold system, rare bird TTS alert, septic alarm, doorbell chime |
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
