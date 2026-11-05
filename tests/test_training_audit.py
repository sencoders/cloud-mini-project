"""Audit fixtures prove numeric updates, not merely a dtype/hash change."""
import importlib.metadata

import pytest
import torch
from safetensors.torch import save_file

from scripts.audit_training import compare
from training.common import read_config


def test_dtype_conversion_alone_is_not_a_numeric_training_update(tmp_path):
    a, b = tmp_path/'a.safetensors', tmp_path/'b.safetensors'
    save_file({'weight':torch.tensor([1,2],dtype=torch.float16)},a)
    save_file({'weight':torch.tensor([1,2],dtype=torch.float32)},b)
    with pytest.raises(AssertionError):
        compare(a,b)


def test_audit_counts_actual_parameter_changes(tmp_path):
    a, b = tmp_path/'a.safetensors', tmp_path/'b.safetensors'
    save_file({'weight':torch.tensor([1.,2.])},a)
    save_file({'weight':torch.tensor([1.,3.])},b)
    result=compare(a,b)
    assert result['changed_elements_after_float32_cast']==1
    assert result['compared_elements']==2 and result['max_absolute_delta']==1


@pytest.mark.parametrize('reported',['2.8.0','2.8.0+cpu'])
def test_exact_upstream_and_official_cpu_build_accepted(monkeypatch,reported):
    original=importlib.metadata.version
    monkeypatch.setattr(importlib.metadata,'version',lambda name:reported if name=='torch' else original(name))
    assert read_config()['training']['device']=='cpu'


@pytest.mark.parametrize('reported',['2.8.0+cu128','2.8.1+cpu'])
def test_cuda_and_different_versions_still_rejected(monkeypatch,reported):
    original=importlib.metadata.version
    monkeypatch.setattr(importlib.metadata,'version',lambda name:reported if name=='torch' else original(name))
    with pytest.raises(RuntimeError,match='torch: expected'):
        read_config()


def test_actual_installed_training_environment_is_supported():
    # Runs on native macOS locally and the real official Linux CPU wheel in CI.
    assert read_config()['model']['name'] == 'EleutherAI/pythia-70m'
