PYTHON ?= python3
RELEASE_ZIP ?= release/INAS-Shipping-Tool.zip

.PHONY: package test help

package:
	$(PYTHON) scripts/build_release.py \
		--output "$(RELEASE_ZIP)"

test:
	$(PYTHON) -m unittest discover -s tests -v

help:
	@echo "  make package - Create the generic portable flasher ZIP"
	@echo "  make test    - Run unit tests"
