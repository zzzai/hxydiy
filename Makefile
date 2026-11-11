.PHONY: test-api test-web test-admin test-all build-all gates

# Fixed entry points. Do not invent another test command for a PR.
test-api:
	cd hxy-server && python -m pytest -q

test-web:
	cd diy-web && npm test

test-admin:
	cd admin-react && npm test

test-all: test-api test-web test-admin

build-all:
	cd diy-web && npm run build
	cd admin-react && npm run build

gates: test-all
	@echo "Quality gates: tests passed. Attach UI screenshots and run release preflight before deploy."
