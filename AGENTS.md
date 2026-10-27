# AI Is Not Art Agent Guide

Read `docs/agent-contract.md` before changing the kiosk, hardware, image-generation, or PixCut integration paths.

- Preserve the state-machine and sibling-repository boundary with PixCut-App.
- Never expose `config.toml`, API keys, or local credentials.
- Do not deploy to the Raspberry Pi, alter systemd or firewall state, call the image API, or actuate GPIO or printer hardware unless the user explicitly asks.
- Validate with the canonical `just` recipes and state which hardware paths remain unverified.
