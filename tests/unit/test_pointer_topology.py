"""Unit tests for pointer display topology validation and pre-dispatch mutation rejection."""

import time
import pytest

from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.movement import (
    MovementDiagnosticReason,
    MovementEvidenceLevel,
    MovementExecutor,
    MovementStatus,
)
from orbit.adapters.pointer.safety import (
    AbiGate,
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
)


def test_topology_identity_matching():
    topo1 = VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1080, monitor_count=1)
    topo2 = VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1080, monitor_count=1)
    assert topo1.matches(topo2) is True


def test_topology_identity_mutations():
    base = VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1080, monitor_count=1)

    # Origin change
    assert base.matches(VirtualDesktopTopologyIdentity(origin_x=-100, origin_y=0, width=1920, height=1080, monitor_count=1)) is False
    # Width change
    assert base.matches(VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=2560, height=1080, monitor_count=1)) is False
    # Height change
    assert base.matches(VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1440, monitor_count=1)) is False
    # Monitor count change
    assert base.matches(VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1080, monitor_count=2)) is False


def test_executor_rejects_topology_mutation_before_dispatch():
    """Verify that if topology mutates between T1 and T6, SendInput is never called."""
    sendinput_calls = []

    def mock_sendinput(n, ptr, sz):
        sendinput_calls.append(n)
        return n

    # Step-based topology generator simulating resolution change between T1 and T6
    calls = [0]
    def changing_topology():
        calls[0] += 1
        if calls[0] == 1:
            return VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=1920, height=1080, monitor_count=1)
        else:
            return VirtualDesktopTopologyIdentity(origin_x=0, origin_y=0, width=2560, height=1440, monitor_count=1)

    counter = ActionCounter()
    executor = MovementExecutor(
        action_counter=counter,
        sendinput_override=mock_sendinput,
        topology_override=changing_topology,
        metrics_override=lambda: VirtualDesktopMetrics(
            x_origin=0, y_origin=0, width=1920, height=1080, is_valid=True, timestamp_ns=time.perf_counter_ns()
        ),
    )

    result = executor.execute_movement(target_x=500, target_y=500)

    assert result.status == MovementStatus.REJECTED_TOPOLOGY_MUTATED
    assert result.diagnostic_reason == MovementDiagnosticReason.TOPOLOGY_MUTATED
    assert result.evidence_level == MovementEvidenceLevel.ABI_VALIDATED
    assert len(sendinput_calls) == 0  # SendInput MUST NOT be called!
    assert counter.sendinput_calls == 0
    assert counter.topology_rejections == 1
    assert counter.rejected_before_dispatch == 1
