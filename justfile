set shell := ["zsh", "-cu"]

default: check

bootstrap:
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt

build:
    python3 -m py_compile config.py hardware.py image_gen.py main.py printer.py prompt_gen.py

test:
    @echo "No automated test suite is configured for ai-is-not-art." >&2; exit 1

lint:
    @echo "No lint command is configured for ai-is-not-art." >&2; exit 1

check: build
