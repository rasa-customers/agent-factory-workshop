.PHONY: setup up doctor test
setup: ; ./setup.sh
up: ; uv run workshop up
doctor: ; uv run workshop doctor
test: ; uv run pytest -q
