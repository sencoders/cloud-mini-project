from decimal import Decimal

import pytest

from scripts.report_task7 import cost_per_1000, error_budget


def test_cost_uses_replica_limits_and_all_running_replicas():
    result = cost_per_1000(2, 1, 1, 10, '3.50', '0.45')
    assert result['all_replicas_hour'] == Decimal('7.90')
    assert result['requests_per_hour'] == 36000
    assert result['cost_per_1000'] == Decimal('7.90') / 36


def test_slo_whole_request_budget_and_boundary():
    budget = error_budget(378, 4)
    assert budget['whole_failure_budget'] == 3
    assert budget['failures_over_budget'] == 1 and not budget['slo_met']
    assert error_budget(400, 4)['slo_met']


def test_zero_throughput_is_not_a_free_cost():
    with pytest.raises(ValueError):
        cost_per_1000(2, 1, 1, 0, '3.50', '0.45')
