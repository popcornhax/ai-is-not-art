# Agent Contract

## Stack and layout

- Python Raspberry Pi kiosk: `main.py` owns the event loop and state machine; `hardware.py` owns GPIO/button/LED behavior; `image_gen.py` owns OpenAI image generation; `printer.py` integrates with the sibling PixCut-App checkout.
- `config.py` loads ignored local `config.toml` from the safe `config.example.toml` shape. `prompt_gen.py` owns prompt selection and anti-repeat history.
- `ai-is-not-art.service` and `deploy.sh` are deployment artifacts, not ordinary validation paths.

## Boundaries and hazards

- Never read, print, commit, or overwrite `config.toml`; it contains the OpenAI API key and machine-specific paths.
- The real deployment runs as root for DMA-driven WS2812 access and can change packages, users, udev rules, firewall rules, and systemd services on a Raspberry Pi.
- Image generation can incur external API cost. Printer and GPIO calls have physical effects. Keep those paths mocked or uninvoked during routine checks.
- The PixCut API is imported from a sibling repository. Coordinate cross-repository interface changes and use separate worktrees for concurrent writers.

## Canonical commands

- Bootstrap: `just bootstrap`
- Syntax check: `just build`
- Full safe check: `just check`
- There is no automated test or lint suite; `just test` and `just lint` fail explicitly rather than reporting false success.

## Completion evidence

- Run `just check` for Python syntax coverage of every first-party module.
- For behavior changes, report the mocked or manual scenario exercised. Hardware, OpenAI, PixCut USB, systemd, firewall, and real Pi deployment remain unverified unless the user explicitly authorizes them.
