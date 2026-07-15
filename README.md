# AI Is Not Art — Sticker Printer

A Raspberry Pi kiosk that generates stickers with OpenAI's image API and prints them on a PixCut S1 vinyl cutter. Press a physical button → three stickers are generated in parallel → laid out and cut by PixCut-App → LED flashes green.

Runs as a systemd service alongside [PixCut-App](../PixCut-App/).

---

## How It Works

```
Button press → WORKING (LED hue-fades)
    ↓
Generate 3 sticker PNGs in parallel via OpenAI API
    ↓
Autocrop + binarize alpha + resize each PNG
    ↓
PixCut-App layout (nesting on sheet) + print + cut
    ↓
SUCCESS (3× green flash) or ERROR (5× red flash)
    ↓
IDLE (dim white)
```

All image files are cleaned up after each run. Logs go to `run-logs/` and `app.log`.

---

## Hardware

### Button — ChromaTek WS2812 illuminated momentary push button

| Button Pin | Pi Pin | BCM |
|------------|--------|-----|
| NO (normally open) | GPIO | 17 |
| C (common) | GND | — |
| DIN (LED data) | GPIO | 18 |
| VDD (LED power) | 5V | — |
| GND (LED ground) | GND | — |

- DOUT (LED chain-out) — leave unconnected (single LED, no chain)
- GPIO 18 is used for the WS2812 because it supports DMA-driven PWM; GPIO 12 also works
- The button input uses gpiozero with internal pull-up (NO contact pulls pin low on press)

### Why the service runs as root

`rpi_ws281x` uses DMA-driven PWM on GPIO 18, which requires kernel-level access. On a dedicated kiosk device this is the simplest approach.

---

## Directory Layout

```
ai-is-not-art/
├── main.py               # event loop, state machine
├── config.py             # TOML config loader + dataclass defaults
├── config.example.toml   # safe configuration template
├── config.toml           # local configuration (ignored by Git)
├── hardware.py           # button (gpiozero) + WS2812 LED (rpi_ws281x)
├── prompt_gen.py         # prompt pool sampling with cross-run anti-repeat
├── image_gen.py          # parallel OpenAI image generation (asyncio)
├── printer.py            # PixCut-App layout + print integration
├── requirements.txt
├── ai-is-not-art.service # systemd unit (runs as root)
└── deploy.sh             # one-command deploy to Raspberry Pi
```

PixCut-App lives in a sibling directory (`../PixCut-App/`). This app imports its Python API directly via `sys.path` — no changes to PixCut-App needed.

---

## Configuration — config.toml

Copy `config.example.toml` to `config.toml` before deploying, then set `openai.api_key` locally. `config.toml` is ignored by Git and must never be committed.

### [openai]

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | `""` | Your OpenAI API key; keep it only in ignored `config.toml` |
| `model` | `"gpt-image-1"` | Image generation model |
| `size` | `"1024x1024"` | Output image size |
| `timeout_s` | `120` | Per-request timeout in seconds |
| `retry_count` | `2` | Retry attempts on failure |
| `stickers_per_run` | `3` | Images to generate per button press |
| `min_stickers_to_print` | `1` | Minimum successes required before printing (0 = require all) |

### [gpio]

| Key | Default | Description |
|-----|---------|-------------|
| `button_pin` | `17` | BCM pin for button NO contact |
| `led_pin` | `18` | BCM pin for WS2812 DIN — must be GPIO 18 or 12 |
| `led_brightness` | `255` | LED brightness 0–255 |

### [pixcut]

| Key | Default | Description |
|-----|---------|-------------|
| `app_path` | `"/home/<pi-user>/pixcut-app"` | Path to PixCut-App directory |
| `log_dir` | `"/home/<pi-user>/ai-is-not-art/run-logs"` | Where PixCut session logs go |
| `dpi` | `300` | Print/cut resolution |
| `margin_mm` | `1.0` | Margin between stickers and sheet edge (mm) |
| `padding_mm` | `3.0` | Padding between stickers (mm) |
| `left_margin_mm` | `2.0` | Extra left margin for media leader (mm) |
| `kp` | `35` | Knife pressure (42 = default, 35 = Oracal vinyl) |
| `sticker_max_mm` | `63.5` | Maximum sticker dimension after resize (mm) |
| `alpha_threshold` | `128` | Alpha pixels below this become fully transparent (removes drop shadows) |
| `bg_image_path` | `""` | Absolute path to background image (printed but not cut); empty = white |

### [app]

| Key | Default | Description |
|-----|---------|-------------|
| `tmp_dir` | `"/dev/shm/ai-is-not-art"` | Temp directory for generated PNGs and layout files (tmpfs) |
| `log_file` | `"/home/<pi-user>/ai-is-not-art/app.log"` | Application log file |
| `prompt_history_window` | `25` | How many recent runs to track for anti-repeat sampling |
| `debug_mode` | `false` | `true` = load stickers into PixCut kiosk canvas instead of printing |
| `kiosk_url` | `"http://localhost:8000"` | PixCut kiosk API base URL (debug mode only) |

---

## Debug Mode

Set `debug_mode = true` in `config.toml` to run without printing:

- Generated PNGs are copied into the PixCut-App stickers directory
- They are loaded onto the kiosk canvas via the REST API
- Open `http://localhost:8000` (or `http://<pi-ip>:8000`) in a browser to preview the layout
- You can trigger a manual print from the browser
- Nothing is physically printed or cut

This is useful for:
- Testing API key and prompt output
- Verifying layout before committing to vinyl
- Running on a non-Pi machine (hardware falls back to mock implementations)

---

## Knife Pressure (kp)

Set `[pixcut] kp` in `config.toml`. The value is embedded in the PLT cut file sent to the printer — it is not a PixCut-App API parameter.

Typical values:
- `42` — PixCut default
- `35` — Oracal 651 vinyl (recommended starting point)

Adjust up if cuts are not going through, down if the blade is dragging or tearing.

---

## LED Behavior

| State | Pattern |
|-------|---------|
| IDLE | Dim white, steady (10% brightness) |
| WORKING | Smooth full-spectrum RGB hue cycle |
| SUCCESS | 3× fast green flashes |
| ERROR | 5× fast red flashes |

After SUCCESS or ERROR, the LED returns to IDLE automatically.

---

## Deploying to Raspberry Pi

The `deploy.sh` script handles everything in one command. Run it from this directory on your Mac.

**Prerequisites on Mac:**
- `rsync` (included with macOS)
- `sshpass` (optional, avoids repeated password prompts): `brew install sshpass`

**Prerequisites on Pi:**
- SSH enabled, Pi reachable on the network
- `pi` or custom user with sudo access

### Basic deploy (conference / secure mode)

```bash
./deploy.sh
```

Set `PI_HOST` and `PI_USER` for your Pi. `SECURE=true` is the default. Use SSH keys when possible; if password authentication is required, provide `PI_PASS` through your local environment and never commit it.

### LAN mode (home / development)

```bash
SECURE=false ./deploy.sh
```

### Custom Pi address or credentials

```bash
PI_HOST=192.168.1.50 PI_USER=pi ./deploy.sh
```

With `sshpass` installed, a password can be supplied locally with `export PI_PASS='your-password'`; do not place it in this README or in the script.

### What deploy.sh does

1. Rsyncs PixCut-App and ai-is-not-art to the Pi (skips `.venv/`, `__pycache__/`, `.git/`)
2. Installs system packages (`python3-venv`, `libusb-1.0-0`, `python3-lgpio`, `ufw`)
3. Adds `sticker` to the `plugdev` group for USB access
4. Installs udev rules for the PixCut printer
5. Creates/updates both Python venvs with dependencies
6. Configures and enables the `pixcut-kiosk` systemd service
7. Configures ufw firewall (see Network Security below)
8. Configures and enables the `ai-is-not-art` systemd service
9. Verifies the kiosk API is responding

### After first deploy

Edit `config.toml` to set your OpenAI API key, then redeploy:

```bash
./deploy.sh
```

---

## Network Security

### SECURE=true (conference/public Wi-Fi — default)

- PixCut kiosk binds to `127.0.0.1` only (not reachable from LAN)
- ufw blocks port 8000 from the network
- SSH (port 22) remains open
- Loopback interface (`lo`) is allowed (needed for ai-is-not-art debug mode)
- Outbound connections unrestricted (OpenAI API calls work fine)

### SECURE=false (home/development)

- PixCut kiosk binds to `0.0.0.0` (reachable from LAN)
- ufw allows port 8000 from any source
- Use this when you want to access the kiosk UI from another device on the network

### Accessing the kiosk UI from your Mac in secure mode

Use an SSH tunnel:

```bash
ssh -L 8000:localhost:8000 <pi-user>@<pi-host>
```

Then open `http://localhost:8000` in your browser on Mac.

---

## Service Management

```bash
# View live logs
ssh <pi-user>@<pi-host> 'journalctl -u ai-is-not-art -f'
ssh <pi-user>@<pi-host> 'journalctl -u pixcut-kiosk -f'

# Restart services
ssh <pi-user>@<pi-host> 'sudo systemctl restart ai-is-not-art'
ssh <pi-user>@<pi-host> 'sudo systemctl restart pixcut-kiosk'

# Check status
ssh <pi-user>@<pi-host> 'sudo systemctl status ai-is-not-art'
ssh <pi-user>@<pi-host> 'sudo systemctl status pixcut-kiosk'

# View app log file
ssh <pi-user>@<pi-host> 'tail -f /home/<pi-user>/ai-is-not-art/app.log'
```

The `ai-is-not-art` service starts after `pixcut-kiosk` (for debug mode). Both restart automatically on failure.

---

## Troubleshooting

**LED not working**
- Service must run as root (`User=root` in the service file) — rpi_ws281x requires DMA access
- GPIO 18 or 12 only — these are the DMA-capable PWM pins on the Pi

**Button not registering**
- Wire NO contact to GPIO 17, C to GND — do not use NC
- Check `journalctl -u ai-is-not-art` for `gpiozero` errors

**OpenAI errors / no images generated**
- Check `api_key` in `config.toml`
- `timeout_s = 120` is conservative; `gpt-image-1` can be slow at peak times
- The service will proceed and print if `min_stickers_to_print` successes were achieved

**PixCut not found / USB errors**
- Printer must be on and USB-connected before the service starts
- Check udev rules: `ls /etc/udev/rules.d/99-pixcut.rules`
- Check plugdev group: `groups sticker` (must include `plugdev`)
- The service runs as root, which bypasses USB permission issues regardless

**svgelements / shapely import errors**
- The ai-is-not-art venv needs PixCut-App's dependencies too
- Re-run `./deploy.sh` — it installs `requirements.txt` from both projects into the ai-is-not-art venv

**Background not printing**
- Set `bg_image_path` to an absolute path in `config.toml`
- The file must exist on the Pi (not just your Mac)
- Background is composited at print time — it does not appear in debug mode canvas preview

**Knife not cutting through / tearing**
- Adjust `kp` in `config.toml` — higher cuts deeper, lower is lighter
- Oracal 651: start at 35, increase by 3 if not cutting through
- Re-run `./deploy.sh` to push the updated config

---

## Prompt System

Prompts are assembled by sampling from pools defined in `config.toml` under `[prompts]`. Each run samples from: `styles`, `compositions`, `tones`, `concepts`, `sticker_shapes`, `wildcards`, `materialities`, `eras`, `render_modes`, `text_treatments`, `tensions`, `anti_defaults`, and `political_modes`.

The sampler tracks the last `prompt_history_window` selections per pool to reduce cross-run repetition. All pools can be edited in `config.toml` — add, remove, or replace entries to tune the output.

Every prompt includes a fixed suffix requiring the text "AI is not art" and "AI generated image" with a transparent background and printable sticker silhouette constraints.

---

## Background Images

Place a JPEG or PNG at the path specified in `[pixcut] bg_image_path`. The background is:

- Resized to fit the full print sheet
- Composited behind all stickers at print time
- **Not cut** — only the sticker silhouettes are cut
- Not visible in the PixCut kiosk canvas preview (debug mode shows stickers only)

The PixCut-App backgrounds folder is a good place to store it: `/home/<pi-user>/pixcut-app/backgrounds/`.
