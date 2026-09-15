# Thin wrapper over tasks.py, which does the actual work and runs on machines
# without make. `make check` and `python tasks.py check` are the same thing.
#
# `make demo` is the one that matters: it builds the frontend and serves
# everything from one process on 8000, which is how the client sees it. Test on
# that path rather than on the Vite dev server.

PYTHON ?= python

.PHONY: install types data check demo api web

install:
	$(PYTHON) tasks.py install

types:
	$(PYTHON) tasks.py types

data:
	$(PYTHON) tasks.py data

check:
	$(PYTHON) tasks.py check

demo:
	$(PYTHON) tasks.py demo

api:
	$(PYTHON) tasks.py api

web:
	$(PYTHON) tasks.py web
