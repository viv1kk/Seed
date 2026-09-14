# Thin wrapper over tasks.py, which does the actual work and runs on machines
# without make. `make check` and `python tasks.py check` are the same thing.
#
# `demo` arrives in phase 2, when main.py mounts the built frontend and there is
# something to serve from one process. Until then, run `api` and `web` side by
# side.

PYTHON ?= python

.PHONY: install types check api web

install:
	$(PYTHON) tasks.py install

types:
	$(PYTHON) tasks.py types

check:
	$(PYTHON) tasks.py check

api:
	$(PYTHON) tasks.py api

web:
	$(PYTHON) tasks.py web
