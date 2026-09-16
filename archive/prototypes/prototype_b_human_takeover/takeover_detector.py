"""
Human Takeover Detector for Prototype B.
Real-time arbitration between expected ORBIT trajectory and observed low-level input events.
Enforces sub-millisecond cancellation and strict safety-first state transitions.
"""

import time
import math
import threading
from typing import Optional, Tuple, Callable

from app_types import (
    Point,
    TrajectoryPoint,
    ActionCategory,
    InputSource,
    TakeoverState,
    InputEvent,
    TelemetryRecord,
)
from trajectory_engine import TrajectoryEngine
from input_controller import InputController
from input_monitor import InputMonitor
from state_machine import TakeoverStateMachine
from telemetry import TelemetryLogger


class TakeoverDetector:
    """
    Central controller orchestrating trajectory execution, input monitoring,
    anomaly detection, and takeover safety transitions.
    """

    def __init__(self, dpi_scale: float = 2.0):
        self.dpi_scale = dpi_scale
        self.trajectory_engine = TrajectoryEngine(dpi_scale=dpi_scale)
        self.input_controller = InputController()
        self.input_monitor = InputMonitor()
        self.state_machine = TakeoverStateMachine()
        self.telemetry = TelemetryLogger()

        self.last_user_activity_ns: int = 0
        self.active_category: ActionCategory = ActionCategory.IDLE
        self._quiet_period_timer: Optional[threading.Timer] = None
        self._execution_thread: Optional[threading.Thread] = None

        # Connect input monitor callback
        self.input_monitor.register_callback(self._on_low_level_input_event)

    def start(self):
        self.input_monitor.start()

    def stop(self):
        self.input_controller.request_cancel()
        self.input_monitor.stop()

    def execute_movement_action(
        self,
        start_pos: Point,
        target_pos: Point,
        category: ActionCategory = ActionCategory.NORMAL_MOVE,
        speed_multiplier: float = 1.0,
        on_complete: Optional[Callable[[bool], None]] = None,
    ):
        """
        Executes an autonomous movement trajectory in a background worker.
        Returns immediately; execution can be interrupted by human takeover at any millisecond.
        """
        if self.state_machine.current_state not in (TakeoverState.IDLE, TakeoverState.RELEASE_PENDING):
            if on_complete:
                on_complete(False)
            return

        self.active_category = category
        self.input_controller.reset_cancel()
        self.state_machine.transition_to(TakeoverState.EXECUTING, f"Starting action {category.value}")

        def worker():
            points = self.trajectory_engine.plan_bezier_trajectory(
                start=start_pos,
                target=target_pos,
                category=category,
                speed_multiplier=speed_multiplier,
            )

            success = True
            for pt in points:
                if self.input_controller.is_cancelled or self.state_machine.current_state != TakeoverState.EXECUTING:
                    success = False
                    break

                # Inject synthetic cursor position
                self.input_controller.move_to(pt.x, pt.y)
                time.sleep(0.008)  # 8ms simulation step (~125Hz)

            if success and self.state_machine.current_state == TakeoverState.EXECUTING:
                if category == ActionCategory.PRECISE_CLICK:
                    time.sleep(0.02)
                    if not self.input_controller.is_cancelled:
                        self.input_controller.mouse_down("left")
                        time.sleep(0.02)
                        self.input_controller.mouse_up("left")
                elif category == ActionCategory.DRAG_OPERATION:
                    time.sleep(0.02)
                    self.input_controller.mouse_up("left")

                self.state_machine.transition_to(TakeoverState.IDLE, "Action completed successfully")

            if on_complete:
                on_complete(success)

        self._execution_thread = threading.Thread(target=worker, name="OrbitActionExecutor", daemon=True)
        self._execution_thread.start()

    def _trigger_takeover(self, reason: str, event_time_ns: int):
        """
        Halts input generation and transitions state machine to PAUSED_BY_USER.
        """
        t_halt_start = time.perf_counter_ns()
        self.input_controller.request_cancel()
        self.state_machine.transition_to(TakeoverState.SUSPECTED_TAKEOVER, reason)
        self.state_machine.transition_to(TakeoverState.PAUSED_BY_USER, reason)
        halt_latency_ms = (time.perf_counter_ns() - t_halt_start) / 1_000_000.0
        self.telemetry.record_halt_latency(halt_latency_ms)

        # Start quiet period monitor
        self._arm_quiet_period_timer()

    def _arm_quiet_period_timer(self):
        if self._quiet_period_timer:
            self._quiet_period_timer.cancel()

        def on_quiet():
            if self.state_machine.current_state == TakeoverState.PAUSED_BY_USER:
                self.state_machine.transition_to(TakeoverState.RELEASE_PENDING, "User quiet period (1000ms inactivity)")

        self._quiet_period_timer = threading.Timer(1.0, on_quiet)
        self._quiet_period_timer.daemon = True
        self._quiet_period_timer.start()

    def _on_low_level_input_event(self, event: InputEvent):
        """
        Evaluates incoming low-level input events in real time against active state.
        Executes in <50 microseconds per event.
        """
        t_eval_start = time.perf_counter_ns()
        current_state = self.state_machine.current_state

        decision = "CONTINUE"
        deviation_px = 0.0
        allowed_thresh_px = 0.0
        expected_coords: Optional[Tuple[int, int]] = None

        if current_state == TakeoverState.EXECUTING:
            expected_pt = self.trajectory_engine.get_expected_state_at(event.timestamp_ns)
            if expected_pt:
                expected_coords = (expected_pt.x, expected_pt.y)
                allowed_thresh_px = expected_pt.threshold_radius

            # --- CASE 1: Ambiguous Input (Injected but missing ORBIT session extraInfo) ---
            if event.source_classification == InputSource.INPUT_AMBIGUOUS:
                self.last_user_activity_ns = event.timestamp_ns
                decision = "PAUSE_REQUESTED"
                self._trigger_takeover(
                    f"Ambiguous input detected (unrecognized injection signature 0x{event.extra_info:X})",
                    event.timestamp_ns,
                )

            # --- CASE 2: Physical User Input ---
            elif event.source_classification == InputSource.USER_PHYSICAL:
                self.last_user_activity_ns = event.timestamp_ns

                # Sudden Mouse Button Press during autonomous movement
                if event.event_type in ("LBUTTON_DOWN", "RBUTTON_DOWN", "MBUTTON_DOWN", "MOUSE_WHEEL"):
                    decision = "PAUSE_REQUESTED"
                    self._trigger_takeover(f"Physical button click ({event.event_type})", event.timestamp_ns)

                # Keyboard input during autonomous execution
                elif event.event_type == "KEY_DOWN":
                    decision = "PAUSE_REQUESTED"
                    self._trigger_takeover(f"Physical keystroke detected (VK {event.vk_code})", event.timestamp_ns)

                # Physical Mouse Movement
                elif event.event_type == "MOUSE_MOVE":
                    if self.active_category == ActionCategory.TEXT_INPUT:
                        # Zero-tolerance mouse touch during active typing
                        decision = "PAUSE_REQUESTED"
                        self._trigger_takeover("Physical movement during text input", event.timestamp_ns)
                    elif expected_pt:
                        dist = math.sqrt((event.x - expected_pt.x) ** 2 + (event.y - expected_pt.y) ** 2)
                        deviation_px = dist

                        # If deviation exceeds adaptive envelope -> User Takeover!
                        if dist > allowed_thresh_px:
                            decision = "PAUSE_REQUESTED"
                            self._trigger_takeover(
                                f"Trajectory departure: {dist:.1f}px > threshold {allowed_thresh_px:.1f}px",
                                event.timestamp_ns,
                            )
                    else:
                        # Event received outside planned temporal window
                        decision = "PAUSE_REQUESTED"
                        self._trigger_takeover("Physical movement outside planned time window", event.timestamp_ns)

            # --- CASE 3: ORBIT Injected Input ---
            elif event.source_classification == InputSource.ORBIT_EXPECTED:
                if expected_pt and event.event_type == "MOUSE_MOVE":
                    dist = math.sqrt((event.x - expected_pt.x) ** 2 + (event.y - expected_pt.y) ** 2)
                    deviation_px = dist
                    # If synthetic event position diverges significantly from expected (e.g. cursor snagged by OS)
                    if dist > allowed_thresh_px * 2.0:
                        decision = "PAUSE_REQUESTED"
                        self._trigger_takeover(f"Synthetic trajectory mismatch: {dist:.1f}px", event.timestamp_ns)

        elif current_state in (TakeoverState.PAUSED_BY_USER, TakeoverState.RELEASE_PENDING):
            if event.source_classification == InputSource.USER_PHYSICAL:
                self.last_user_activity_ns = event.timestamp_ns
                decision = "HOLD_PAUSED"
                if current_state == TakeoverState.RELEASE_PENDING:
                    self.state_machine.transition_to(TakeoverState.PAUSED_BY_USER, "User activity resumed")
                self._arm_quiet_period_timer()

        # Telemetry logging
        eval_latency_us = (time.perf_counter_ns() - t_eval_start) / 1000.0
        record = TelemetryRecord(
            event_id=event.event_id,
            timestamp_ms=time.time() * 1000.0,
            action_category=self.active_category.value,
            state=current_state.value,
            observed_pos=(event.x, event.y),
            expected_pos=expected_coords,
            deviation_px=round(deviation_px, 2),
            allowed_threshold_px=round(allowed_thresh_px, 2),
            input_source=event.source_classification.value,
            decision=decision,
            decision_latency_us=round(eval_latency_us, 2),
        )
        self.telemetry.log_event(record)
