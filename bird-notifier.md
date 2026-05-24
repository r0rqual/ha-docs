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
        # repeat for bird_3 through bird_6
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
    it.printf(160, 40, id(font_large), TextAlign::CENTER, "Bird Detected");
    it.printf(160, 100, id(font_medium), TextAlign::CENTER, "%s",
      id(birdnet_detection).state.c_str());
```

**bird_idle_page** — Recent species list (6 birds):
```yaml
- id: bird_idle_page
  lambda: |-
    it.printf(160, 20, id(font_large), TextAlign::CENTER, "Recent Birds");
    // 6 birds with 28px spacing
    it.printf(20, 55, id(font_small), "%s", id(bird_1_name).state.c_str());
    it.printf(300, 55, id(font_small), TextAlign::RIGHT, "%s", id(bird_1_ago).state.c_str());
    // repeat for birds 2-6
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

## 5. Rare Bird Alerts

Audio announcement via Alexa and mobile push notification when a rare bird is detected. "Rare" means < 5% eBird checklist frequency for the current week in Dane County, WI.

### Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ONE-TIME SETUP (annual refresh)                                             │
│                                                                              │
│  ┌─────────────┐      ┌─────────────┐      ┌──────────────────────────────┐  │
│  │ eBird.org   │      │ Python      │      │ /config/dane_county_         │  │
│  │ Bar Chart   │─────▶│ Parser      │─────▶│ frequencies.json             │  │
│  │ (manual DL) │      │ Script      │      │ (521 species × 48 weeks)     │  │
│  └─────────────┘      └─────────────┘      └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  RUNTIME FLOW                                                                │
│                                                                              │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                   │
│  │ BirdNET     │ MQTT │ sensor.     │ trig │ Automation  │                   │
│  │ Detection   │─────▶│ birdnet_    │─────▶│ rare_bird_  │                   │
│  │             │      │ latest_     │      │ tts_alert   │                   │
│  └─────────────┘      │ detection   │      └──────┬──────┘                   │
│                       └─────────────┘             │                          │
│                                                   ▼                          │
│                       ┌─────────────┐      ┌─────────────┐                   │
│                       │ shell_cmd   │      │ Write code  │                   │
│                       │ set_bird_   │◀─────│ to file     │                   │
│                       │ code        │      └─────────────┘                   │
│                       └──────┬──────┘                                        │
│                              │                                               │
│                              ▼                                               │
│                       ┌─────────────┐      ┌─────────────┐                   │
│                       │ sensor.     │      │ Python      │                   │
│                       │ bird_       │◀─────│ script      │                   │
│                       │ rarity_     │      │ (reads JSON │                   │
│                       │ check       │      │ returns %)  │                   │
│                       └──────┬──────┘      └─────────────┘                   │
│                              │                                               │
│                              ▼                                               │
│                       ┌─────────────┐      ┌─────────────┐                   │
│                       │ If freq     │ yes  │ Alexa       │                   │
│                       │ < 5%?       │─────▶│ Announce +  │                   │
│                       └─────────────┘      │ Mobile Push │                   │
│                                            └─────────────┘                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Data Setup

1. **Download eBird bar chart** (requires login):
   - Go to https://ebird.org/barchart?r=US-WI-025
   - Click "Download Histogram Data" at bottom
   - Save to `~/src/homeassistant-local/`

2. **Download eBird taxonomy** (one-time):
   ```bash
   curl -o eBird_taxonomy_v2025.csv \
     "https://www.birds.cornell.edu/clementschecklist/wp-content/uploads/2025/10/eBird_taxonomy_v2025.csv"
   ```

3. **Run parser**:
   ```bash
   python3 parse_ebird_barchart.py \
     ebird_US-WI-025__1900_2026_1_12_barchart.txt \
     eBird_taxonomy_v2025.csv \
     dane_county_frequencies.json
   ```

4. **Copy to HA**:
   ```bash
   cp dane_county_frequencies.json /Volumes/config/
   ```

### Home Assistant Configuration

**Shell Command & Sensor** (`configuration.yaml`):
```yaml
command_line:
  - sensor:
      name: "Bird Rarity Check"
      unique_id: bird_rarity_check
      command: "cat /config/.last_bird_code 2>/dev/null | xargs -I{} python3 /config/scripts/check_rare_bird.py {} || echo 1.0"
      scan_interval: 86400
      value_template: "{{ value | float(1.0) }}"

shell_command:
  set_bird_code: "/bin/bash -c 'echo {{ species_code }} > /config/.last_bird_code'"
```

**Rarity Script** (`scripts/check_rare_bird.py`):
- Reads `/config/dane_county_frequencies.json`
- Calculates week index (0-47) from current date
- Outputs frequency (0.0-1.0), exit 0 if rare, 1 if common

**Toggle** (`input_booleans.yaml`):
```yaml
rare_bird_alerts_enabled:
  name: Rare Bird Alerts
  icon: mdi:bird
```

**Automation** (`automations.yaml`):
- Triggers on `sensor.birdnet_latest_detection` state change
- Conditions: alerts enabled, confidence ≥ 70%
- Writes species code via `shell_command.set_bird_code`
- Updates `sensor.bird_rarity_check`
- If frequency < 0.05:
  - Calls `notify.alexa_media_kitchen_echo_dot` for voice announcement
  - Sends `notify.mobile_app_lucas_iphone` with bird name and confidence %

### Week Index Calculation

eBird uses 4 periods per month (48 total):
```
week_index = (month - 1) * 4 + min((day - 1) // 7, 3)
```

| Month | Week Indices |
|-------|--------------|
| January | 0, 1, 2, 3 |
| February | 4, 5, 6, 7 |
| ... | ... |
| December | 44, 45, 46, 47 |

### Testing

```yaml
# Simulate rare bird in Developer Tools → Actions
action: mqtt.publish
data:
  topic: birdnet
  payload: '{"CommonName":"Snowy Owl","ScientificName":"Bubo scandiacus","Confidence":0.85,"SpeciesCode":"snoowl1","Date":"2026-03-01","Time":"12:00:00"}'
```

### Maintenance

- **Annual:** Re-download eBird bar chart in January and re-run parser
- **Threshold:** Adjust 0.05 (5%) in automation if too many/few alerts
- **Taxonomy:** Update CSV if species aren't matching (eBird releases new taxonomy each fall)

## 6. Pi Networking

The Pi Zero sits on the second floor southwest corner; the router is in the basement center. Direct signal to the main SSID is marginal (-70 to -75 dBm), which causes intermittent dropouts and lost detections.

**Setup:**
- TP-Link RE105 range extender on first floor southwest side, broadcasting `beaumont_EXT`
- Extender DHCP turned **off** (transparent bridging mode)
- Pi connects to `beaumont_EXT` with static IP 192.168.50.42 (via NetworkManager `ipv4.method=manual`)
- Original `beaumont` (NM connection name `preconfigured`) retained as autoconnect fallback
- DHCP reservation on main router maps Pi MAC `2c:cf:67:28:d2:69` → `192.168.50.42` (used by the fallback path)

**NetworkManager connections on the Pi:**
```
preconfigured   beaumont       autoconnect=yes priority=0  (DHCP — fallback)
beaumont_EXT    beaumont_EXT   autoconnect=yes priority=10 (static .42)
```

**Signal monitoring** — cron logs WiFi signal every 5 min, self-trims to ~7 days:
```bash
*/5 * * * * echo "$(date +\%F\ \%T) $(/sbin/iwconfig wlan0 2>/dev/null | grep -o "Signal level=.*")" >> /home/lucas/wifi_signal.log; tail -2016 /home/lucas/wifi_signal.log > /home/lucas/wifi_signal.tmp && mv /home/lucas/wifi_signal.tmp /home/lucas/wifi_signal.log
```

Gaps in the log = WiFi was down. On `beaumont_EXT` signal should be around -50 dBm.

## 7. Troubleshooting

### No bird detections in HA

Check what's actually broken in order:

1. **Is `sensor.birdnet_latest_detection` `unavailable`?** Could be MQTT timeout (no recent detections) or BirdNET pipeline crashed.

2. **Is the Pi reachable?** From the HA host or Mac:
   ```bash
   ping 192.168.50.42
   ```
   Timeout / "No route to host" = WiFi/network issue. Check signal log on the Pi.

3. **Is the RTSP stream up on the Pi?**
   ```bash
   ssh lucas@birdmic 'systemctl is-active mediamtx birdmic'
   ```
   Both should be `active`.

4. **Is BirdNET seeing audio?** Check `/tmp/StreamData/` in the BirdNET container:
   ```bash
   docker exec $(docker ps -qf name=birdnet) sh -c 'ls -la /tmp/StreamData/'
   ```
   Should see fresh `.wav` files with today's date. If only stale `.json`/`.txt` files, the stream isn't connecting.

5. **Check BirdNET-Pi add-on logs** — Settings → Add-ons → BirdNET-Pi → Log. Look for `sox FAIL` errors or `Connection timed out` on the RTSP URL.

### sox trim error — start position after stop position

**Symptom:** Add-on log spams:
```
sox FAIL trim: Position 1 is behind the following position
...trim, '=37.5', '=15'...
```

**Cause:** Bug in BirdNET-Pi `reporting.py` triggered by malformed audio files (typically from RTSP stream interruptions). The unhandled exception kills `birdnet_analysis` and stops MQTT publishing — even for *good* detections that come after.

**Fix:** Clear the corrupted WAV files and restart:
```bash
# From HA Terminal add-on:
docker ps | grep -i bird   # get container ID
docker exec <id> sh -c 'rm -f /tmp/StreamData/*.wav'
# Then restart BirdNET-Pi from HA UI
```

If the stream just dropped (single bad file), the queue will recover after that file is processed. If many days of stale files accumulated, clear them by date prefix:
```bash
docker exec <id> sh -c 'rm -f /tmp/StreamData/2026-05-01*.wav'
```

### WiFi dropping out

Check signal log on the Pi (`cat ~/wifi_signal.log`). Gaps = WiFi was disconnected. If signal is consistently weaker than -70 dBm, the Pi's location is out of reliable range — move the extender closer or improve coverage.

### Pi got the wrong IP

The Pi should always be at .42, either via static IP on `beaumont_EXT` or via DHCP reservation on `beaumont`. If it ends up on a different IP:
- Check which SSID it's on: `iwconfig wlan0 | grep ESSID`
- Check NetworkManager connection: `nmcli connection show --active`
- If on `beaumont_EXT` but not .42: static IP config got changed, re-apply with `nmcli connection modify`
- If on `beaumont` but not .42: DHCP reservation on the router didn't apply, check router admin

### NetworkManager picks the wrong network on boot

Verify priorities:
```bash
nmcli -f connection.id,connection.autoconnect-priority connection show
```
`beaumont_EXT` should be priority 10, `preconfigured` priority 0. If `beaumont_EXT` consistently fails to come up (check `journalctl -u NetworkManager -b 0`), the fallback to `preconfigured` is expected behavior.

