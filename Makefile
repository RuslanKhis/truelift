# truelift developer commands. Needs uv (https://docs.astral.sh/uv/); uv provisions Python 3.12.
# Every target runs against uv.lock (--locked fails if pyproject.toml and uv.lock disagree).

UV       ?= uv
RUN      := $(UV) run --locked
BUILDDIR := build

.PHONY: dev check guard lint test audit dist e2e clean

## dev: install the locked environment and the pre-commit hooks
dev:
	$(UV) sync --locked
	$(RUN) pre-commit install

## check: everything CI requires (guard, lint, tests, dependency audit)
check: guard lint test audit

guard:
	$(RUN) python scripts/guard_public.py --tree

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

test:
	$(RUN) pytest

## audit: known-vulnerability scan of every locked package (SB15).
## pip-audit fails on any known vulnerability, which covers "high". Needs network.
audit:
	@mkdir -p $(BUILDDIR)
	$(UV) export --locked --format requirements-txt --no-emit-project --quiet -o $(BUILDDIR)/audit-requirements.txt
	$(RUN) pip-audit --disable-pip --require-hashes --progress-spinner off -r $(BUILDDIR)/audit-requirements.txt

## dist: build sdist and wheel, then check their contents (C13)
dist:
	rm -rf dist
	$(UV) build --quiet
	$(RUN) python scripts/guard_public.py --dist dist/*.tar.gz dist/*.whl

## e2e: end-to-end journey tests. None exist until G20, so this fails with
## "no tests ran" rather than reporting a pass.
e2e:
	$(RUN) pytest -m e2e

clean:
	rm -rf dist $(BUILDDIR) .pytest_cache .ruff_cache
