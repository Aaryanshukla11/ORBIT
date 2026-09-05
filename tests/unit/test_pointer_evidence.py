"""Unit tests for pointer SendInput evidence levels, readback verification, and diagnostic reasons."""

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


def _create_mock_executor(
    sendinput_return: int = 1,
    cursorpos_return: tuple[int, int] = (500, 500),
    is_abi_valid: bool = True,
):
    counter = ActionCounter()
    gate = AbiGate()
    if not is_abi_valid:
        from orbit.adapters.pointer.safety import AbiValidationResult, AbiValidationStatus
        gate._result = AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system="win32",
            machine_arch="AMD64",
            pointer_width_bytes=8,
            sizeof_mouseinput=48,
            sizeof_input=56,
            offset_dx=0,
            offset_dwflags=12,
            offset_dwextrainfo=24,
            offset_input_union=8,
            is_pointer_sized_extrainfo=True,
            error_message="Simulated MOUSEINPUT size mismatch",
        )

    executor = MovementExecutor(
        abi_gate=gate,
        action_counter=counter,
        sendinput_override=lambda n, ptr, sz: sendinput_return,
        cursorpos_override=lambda: cursorpos_return,
        topology_override=lambda: VirtualDesktopTopologyIdentity(0, 0, 1920, 1080, 1),
        metrics_override=lambda: VirtualDesktopMetrics(
            x_origin=0, y_origin=0, width=1920, height=1080, is_valid=True, timestamp_ns=time.perf_counter_ns()
        ),
    )
    return executor, counter


def test_destination_verified_evidence():
    executor, counter = _create_mock_executor(sendinput_return=1, cursorpos_return=(500, 500))
    result = executor.execute_movement(target_x=500, target_y=500, tolerance_px=1)

    assert result.status == MovementStatus.MOVEMENT_VERIFIED
    assert result.diagnostic_reason == MovementDiagnosticReason.NONE
    assert result.evidence_level == MovementEvidenceLevel.DESTINATION_VERIFIED
    assert result.observed_x == 500
    assert result.observed_y == 500
    assert result.delta_x == 0
    assert result.delta_y == 0
    assert counter.sendinput_calls == 1
    assert counter.accepted_packets == 1
    assert counter.verified_movements == 1


def test_cursor_readback_mismatch_evidence():
    # Target is (500, 500), but observed cursor position is (550, 500)
    executor, counter = _create_mock_executor(sendinput_return=1, cursorpos_return=(550, 500))
    result = executor.execute_movement(target_x=500, target_y=500, tolerance_px=1)

    assert result.status == MovementStatus.CURSOR_READBACK_MISMATCH
    assert result.diagnostic_reason == MovementDiagnosticReason.EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE
    assert result.evidence_level == MovementEvidenceLevel.CURSOR_READBACK_OBSERVED
    assert result.observed_x == 550
    assert result.observed_y == 500
    assert result.delta_x == 50
    assert result.delta_y == 0
    assert counter.sendinput_calls == 1
    assert counter.readback_mismatches == 1


def test_sendinput_dispatch_zero_evidence():
    executor, counter = _create_mock_executor(sendinput_return=0)
    result = executor.execute_movement(target_x=500, target_y=500)

    assert result.status == MovementStatus.DISPATCH_ZERO
    assert result.diagnostic_reason == MovementDiagnosticReason.SENDINPUT_FAILED
    assert result.evidence_level == MovementEvidenceLevel.DISPATCH_FAILED
    assert result.accepted_packets == 0
    assert counter.sendinput_calls == 1
    assert counter.failed_dispatches == 1


def test_abi_invalid_evidence():
    executor, counter = _create_mock_executor(is_abi_valid=False)
    result = executor.execute_movement(target_x=500, target_y=500)

    assert result.status == MovementStatus.ABI_INVALID
    assert result.diagnostic_reason == MovementDiagnosticReason.ABI_MISMATCH
    assert result.evidence_level == MovementEvidenceLevel.REQUEST_ACCEPTED_BY_ORBIT
    assert counter.sendinput_calls == 0
    assert counter.rejected_before_dispatch == 1
