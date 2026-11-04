PYTHON ?= .venv312/bin/python

.PHONY: up smoke label status clean test down
up:
	PYTHONPATH=. $(PYTHON) scripts/system.py up
smoke:
	$(PYTHON) scripts/task1.py smoke
label:
	$(PYTHON) scripts/task1.py launch
status:
	$(PYTHON) scripts/task1.py status
clean:
	$(PYTHON) scripts/task1.py clean
test:
	$(PYTHON) -m pytest -q
down:
	PYTHONPATH=. $(PYTHON) scripts/system.py down

VERSION ?= v1
.PHONY: train evaluate upload-model package-model
train:
	$(PYTHON) -m training.train --version $(VERSION) $(if $(SUBSET),--subset $(SUBSET),)
evaluate:
	$(PYTHON) -m training.evaluate --model $(MODEL)
upload-model:
	$(PYTHON) -m training.artifacts upload --version $(VERSION)
package-model:
	$(PYTHON) -m training.artifacts package --version $(VERSION)

.PHONY: prepare-student
prepare-student:
	$(PYTHON) scripts/download_student.py

.PHONY: service-build service-test
service-build:
	docker build -t command-parser:task3 -f service/Dockerfile .
service-test:
	$(PYTHON) scripts/test_service_docker.py

.PHONY: app-up app-experiments app-status
app-up:
	$(PYTHON) scripts/task4.py deploy
app-experiments:
	$(PYTHON) scripts/task4.py experiments
app-status:
	$(PYTHON) scripts/task4.py snapshot

.PHONY: app-resume app-report
app-resume:
	$(PYTHON) scripts/task4.py resume
app-report:
	$(PYTHON) scripts/report_task4.py

.PHONY: lint network-check performance-report down-dry-run
lint:
	.venv312/bin/ruff check .
network-check:
	$(PYTHON) tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
performance-report:
	$(PYTHON) scripts/report_task7.py
down-dry-run:
	PYTHONPATH=. $(PYTHON) scripts/system.py down --dry-run
