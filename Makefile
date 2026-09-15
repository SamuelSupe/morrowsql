.PHONY: sources build images check package
PYTHON ?= python3.12

sources:
	$(PYTHON) scripts/fetch-sources.py

build:
	bash scripts/build.sh all

images:
	bash scripts/build.sh images

check:
	bash scripts/check.sh

package:
	$(PYTHON) scripts/package.py binary --arch $(ARCH)
	$(PYTHON) scripts/package.py source
