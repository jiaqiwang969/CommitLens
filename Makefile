SHELL := /bin/sh

# Cross-platform venv layout
OS := $(shell uname -s 2>/dev/null || echo Windows_NT)
VENV_DIR ?= .venv
ifeq ($(OS),Windows_NT)
  VENV_BIN := $(VENV_DIR)/Scripts
else
  VENV_BIN := $(VENV_DIR)/bin
endif

# Detect a usable Python interpreter for bootstrapping venv
PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || command -v py 2>/dev/null || echo python3)
VENV_PY := $(VENV_BIN)/python
VENV_PIP := $(VENV_BIN)/pip

.PHONY: help venv deps dev gui mirror gen verify clean distclean

help:
	@echo "Targets:"
	@echo "  make dev      - create venv and install deps"
	@echo "  make gui      - run the GUI (tools/sboxgen_gui.py)"
	@echo "  make mirror   - clone/update bare mirror: REPO=... [MIRROR=.cache/mirrors/repo.git]"
	@echo "  make gen      - generate timeline: MIRROR=... [BRANCH=master OUT=.sboxes_timeline LIMIT=10 STYLE=timeline]"
	@echo "  make verify   - verify generated sboxes: ROOT=.sboxes_timeline"
	@echo "  make clean    - remove smoke/test outputs (.sboxes_* , .artifacts in temp)"
	@echo "  make distclean- remove venv and caches"

# 1) Create venv
$(VENV_DIR)/.created:
	$(PYTHON) -m venv $(VENV_DIR)
	@echo created > $@

# 2) Upgrade tooling and install deps (editable project by default)
$(VENV_DIR)/.deps: requirements.txt | $(VENV_DIR)/.created
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel
	$(VENV_PIP) install -r requirements.txt
	@echo installed > $@

venv: $(VENV_DIR)/.created

deps: $(VENV_DIR)/.deps

dev: deps

# Run GUI without activating shell venv
gui: dev
	TK_SILENCE_DEPRECATION=1 $(VENV_PY) tools/sboxgen_gui.py

# Convenience: ensure mirror exists or update it
REPO ?= https://github.com/Formlabs/foxtrot.git
MIRROR ?= .cache/mirrors/foxtrot.git
mirror: dev
	$(VENV_PY) -m sboxgen.cli mirror --repo "$(REPO)" --dest "$(MIRROR)"

# Generate timeline from a mirror
BRANCH ?= master
OUT ?= .sboxes_timeline
LIMIT ?= 10
STYLE ?= timeline
gen: dev
	$(VENV_PY) -m sboxgen.cli gen --mirror "$(MIRROR)" --branch "$(BRANCH)" --out "$(OUT)" --limit "$(LIMIT)" --overwrite --style "$(STYLE)"

verify: dev
	$(VENV_PY) -m sboxgen.cli verify --root "$(OUT)" --strict

clean:
	@rm -rf .sboxes_timeline_smoke .sboxes_* 2>/dev/null || true
	@echo "Cleaned smoke outputs."

distclean: clean
	@rm -rf $(VENV_DIR) .cache __pycache__ 2>/dev/null || true
	@echo "Removed venv and caches."

