PYTHON ?= .venv312/bin/python

.PHONY: up smoke label status clean test down
up:
	k3d cluster create --config cluster/k3d.yaml
	$(PYTHON) scripts/task1.py setup
	$(PYTHON) scripts/task1.py build
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
	$(PYTHON) scripts/task1.py down

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
