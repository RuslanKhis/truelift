# truelift developer commands. Needs uv (https://docs.astral.sh/uv/); uv provisions Python 3.12.
# Every target runs against uv.lock (--locked fails if pyproject.toml and uv.lock disagree).

UV       ?= uv
NPM      ?= npm
RUN      := $(UV) run --locked
BUILDDIR := build
FRONTEND := frontend

.PHONY: dev check guard lint test client client-check audit dist e2e clean

## dev: install the locked environment, the frontend tooling and the pre-commit hooks
dev: $(FRONTEND)/node_modules
	$(UV) sync --locked
	$(RUN) pre-commit install

## check: everything CI requires (guard, lint, tests, client drift, dependency audits)
check: guard lint test client-check audit

guard:
	$(RUN) python scripts/guard_public.py --tree

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

test:
	$(RUN) pytest

# Node is needed for the generated client only (Node >= 22.18, see frontend/package.json).
$(FRONTEND)/node_modules: $(FRONTEND)/package.json $(FRONTEND)/package-lock.json
	$(NPM) --prefix $(FRONTEND) ci --ignore-scripts --no-audit --no-fund
	@touch $@

## client: dump the OpenAPI document offline and regenerate frontend/src/client (commit both)
client: $(FRONTEND)/node_modules
	$(RUN) python -m truelift.api.openapi_dump openapi.json
	cd $(FRONTEND) && $(NPM) run --silent client

## client-check: regenerate both into build/ and fail if the committed ones differ (offline, C16)
client-check: $(FRONTEND)/node_modules
	@rm -rf $(BUILDDIR)/contract && mkdir -p $(BUILDDIR)/contract
	$(RUN) python -m truelift.api.openapi_dump $(BUILDDIR)/contract/openapi.json
	cd $(FRONTEND) && OPENAPI_INPUT=../$(BUILDDIR)/contract/openapi.json \
		OPENAPI_OUTPUT=../$(BUILDDIR)/contract/client $(NPM) run --silent client
	@diff -u openapi.json $(BUILDDIR)/contract/openapi.json || \
		{ echo "openapi.json drifted from the code: run 'make client' and commit"; exit 1; }
	@diff -ru $(FRONTEND)/src/client $(BUILDDIR)/contract/client || \
		{ echo "frontend/src/client drifted from openapi.json: run 'make client' and commit"; exit 1; }
	@echo "client-check: no drift"

# Named exceptions to the audit (SB15). Each needs a reason and the trigger that removes it.
# CVE-2026-114603 (GHSA-xcq7-p3pf-p88h, medium): unbounded tracestate parsing in
# opentelemetry-api <= 1.45.0. google-adk 2.12.0 caps opentelemetry-api at <= 1.42.1, and the
# ADK pin is a release-unit decision. Not reachable in G02: nothing extracts W3C trace context
# from incoming requests (no OTel instrumentation, ADK's server not mounted, loopback + token).
# Remove when google-adk moves to a release that allows opentelemetry-api >= 1.45.1 (2.14.0+).
PIP_AUDIT_IGNORE := --ignore-vuln CVE-2026-114603

## audit: known-vulnerability scan of every locked package (SB15).
## pip-audit fails on any known vulnerability, which covers "high"; npm audit fails on high
## or critical. Needs network.
audit: $(FRONTEND)/node_modules
	@mkdir -p $(BUILDDIR)
	$(UV) export --locked --format requirements-txt --no-emit-project --quiet -o $(BUILDDIR)/audit-requirements.txt
	$(RUN) pip-audit --disable-pip --require-hashes --progress-spinner off $(PIP_AUDIT_IGNORE) -r $(BUILDDIR)/audit-requirements.txt
	$(NPM) --prefix $(FRONTEND) audit --audit-level=high

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
