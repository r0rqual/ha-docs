# Bird Notifier

Automated bird identification using a Pi Zero 2 W, BirdNET ML, and Home Assistant with ESP32 display.

## Architecture

```
┌─────────────────┐    RTSP    ┌─────────────────┐    MQTT    ┌─────────────┐
│ Pi Zero 2 W     │───────────▶│ BirdNET-Pi      │───────────▶│ Home        │
│ + ReSpeaker HAT │   audio    │ (HA add-on)     │ detections │ Assistant   │
└─────────────────┘            └─────────────────┘            └─────────────┘
                                                                     │
                                                                     ▼
                                                              ┌─────────────┐
                                                              │ ESP32-S3-BOX│
                                                              │ Display     │
                                                              └─────────────┘
```

## Hardware

| Component | Purpose |
|-----------|---------|
| Raspberry Pi Zero 2 W | Audio capture node |
| ReSpeaker 2-Mic HAT | I2S microphone array (uses WM8960 codec) |
| ESP32-S3-BOX-3B | Touchscreen display (optional) |

## 1. Pi Zero Audio Capture

### OS Setup

Flash Raspberry Pi OS Lite (64-bit) to SD card. Enable SSH and configure WiFi in Imager.

### WM8960 Driver

The ReSpeaker 2-Mic HAT uses the WM8960 codec. The Waveshare driver works well:

```bash
sudo apt-get update && sudo apt-get full-upgrade -y
sudo apt-get install -y git
git clone https://github.com/waveshare/WM8960-Audio-HAT.git
cd WM8960-Audio-HAT
sudo ./install.sh
sudo reboot
```

Verify with `arecord -l` — should show `wm8960-soundcard`.

### MediaMTX (RTSP Server)

Download from https://github.com/bluenviron/mediamtx/releases

```bash
wget https://github.com/bluenviron/mediamtx/releases/download/v1.9.3/mediamtx_v1.9.3_linux_arm64v8.tar.gz
tar -xzf mediamtx_v1.9.3_linux_arm64v8.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo mv mediamtx.yml /usr/local/etc/
```

Create `/etc/systemd/system/mediamtx.service`:
```ini
[Unit]
Description=MediaMTX RTSP Server
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/mediamtx /usr/local/etc/mediamtx.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Audio Stream Service

Create `/etc/systemd/system/birdmic.service`:
```ini
[Unit]
Description=Bird Mic RTSP Stream
After=mediamtx.service sound.target
Requires=mediamtx.service

[Service]
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/ffmpeg -nostdin -f alsa -ac 1 -ar 48000 -i hw:0,0 -c:a pcm_s16be -f rtsp rtsp://localhost:8554/birdmic
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable mediamtx birdmic
sudo systemctl start mediamtx birdmic
```

Test stream: `ffplay rtsp://<pi-ip>:8554/birdmic`

## 2. BirdNET-Pi Add-on

### Install

In Home Assistant: Settings → Add-ons → Add-on Store → ⋮ → Repositories

Add: `https://github.com/alexbelgium/hassio-addons`

Install "BirdNET-Pi" from the list.

### Configure

In the add-on configuration:
```yaml
RTSP_STREAM: "rtsp://<pi-ip>:8554/birdmic"
LATITUDE: <your-lat>
LONGITUDE: <your-lon>
CONFIDENCE: 0.7
MQTT_HOST: core-mosquitto
MQTT_PORT: 1883
MQTT_TOPIC: birdnet
```

Requires Mosquitto MQTT broker add-on running.

## 3. Home Assistant Sensors

### MQTT Trigger Sensor

`configuration.yaml`:
```yaml
mqtt:
  sensor:
    - name: "BirdNET Latest Detection"
      state_topic: "birdnet"
      value_template: "{{ value_json.CommonName }}"
      json_attributes_topic: "birdnet"
      json_attributes_template: "{{ value_json | tojson }}"
```

### SQL Sensor (Bird History)

Queries HA's database for recent unique detections:

```yaml
sensor:
  - platform: sql
    db_url: sqlite:////config/home-assistant_v2.db
    queries:
      - name: Recent Bird Detections
        query: >
          SELECT json_group_array(json_object(
            'name', CommonName,
            'time', detection_time
          )) as detections
          FROM (
            SELECT
              json_extract(attributes, '$.CommonName') as CommonName,
              MAX(last_updated_ts) as detection_time
            FROM states
            WHERE entity_id = 'sensor.birdnet_latest_detection'
              AND json_extract(attributes, '$.CommonName') IS NOT NULL
            GROUP BY CommonName
            ORDER BY detection_time DESC
            LIMIT 20
          )
        column: detections
```

### Template Sensor (Display Formatting)

`template_sensors.yaml`:
```yaml
- sensor:
    - name: "Recent Birds Display"
      state: "{{ now().isoformat() }}"
      attributes:
        bird_1_name: >
          {% set d = state_attr('sensor.recent_bird_detections', 'detections') | from_json %}
          {{ d[0].name if d | length > 0 else '' }}
        bird_1_ago: >
          {% set d = state_attr('sensor.recent_bird_detections', 'detections') | from_json %}
          {% if d | length > 0 %}
            {% set delta = now().timestamp() - d[0].time %}
            {% if delta < 3600 %}{{ (delta / 60) | int }}m
            {% elif delta < 86400 %}{{ (delta / 3600) | int }}h
            {% else %}{{ (delta / 86400) | int }}d{% endif %}
          {% endif %}
        bird_2_name: "..."
        bird_2_ago: "..."
        # repeat for bird_3, bird_4
```

## 4. ESP32 Display (Optional)

### ESPHome Base

Uses BigBobbas ESP32-S3-BOX-3 package: https://github.com/BigBobbas/esphome_firmware

### Display Pages

Two bird pages in the ESPHome config:

**bird_page** — Alert on new detection:
```yaml
- id: bird_page
  lambda: |-
    it.printf(160, 40, id(font_large), TextAlign::CENTER, "Now Singing");
    it.printf(160, 100, id(font_medium), TextAlign::CENTER, "%s",
      id(birdnet_detection).state.c_str());
```

**bird_idle_page** — Recent species list:
```yaml
- id: bird_idle_page
  lambda: |-
    it.printf(160, 20, id(font_large), TextAlign::CENTER, "Recent Birds");
    it.printf(20, 60, id(font_small), "%s", id(bird_1_name).state.c_str());
    it.printf(300, 60, id(font_small), TextAlign::RIGHT, "%s", id(bird_1_ago).state.c_str());
    // repeat for birds 2-4
```

### Auto-Display on Detection

```yaml
on_value:
  then:
    - display.page.show: bird_page
    - delay: 30s
    - display.page.show: bird_idle_page
```

## MQTT Payload Reference

```json
{
  "CommonName": "Red-tailed Hawk",
  "ScientificName": "Buteo jamaicensis",
  "Confidence": 0.8452,
  "Date": "2026-02-22",
  "Time": "09:33:27",
  "SpeciesCode": "rethaw",
  "FlickrImage": "https://live.staticflickr.com/..."
}
```

