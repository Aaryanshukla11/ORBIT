"""
Trajectory Engine for Prototype B.
Generates natural Bezier movement curves and computes adaptive spatial/temporal
deviation envelopes tailored to action categories and DPI scaling.
"""

import math
import time
from typing import List, Tuple, Optional
from app_types import Point, TrajectoryPoint, ActionCategory


class TrajectoryEngine:
    """
    Generates and samples planned trajectories, providing real-time expected
    cursor positions, velocity vectors, and dynamic deviation thresholds.
    """

    def __init__(self, dpi_scale: float = 2.0):
        self.dpi_scale = dpi_scale
        self.active_category: ActionCategory = ActionCategory.IDLE
        self.planned_points: List[TrajectoryPoint] = []
        self.start_time_ns: int = 0
        self.total_duration_ms: float = 0.0
        self.start_pos: Point = Point(0, 0)
        self.target_pos: Point = Point(0, 0)

    def calculate_adaptive_threshold(
        self,
        category: ActionCategory,
        velocity_px_per_ms: float = 0.0,
        distance_to_target_px: float = 0.0,
    ) -> float:
        """
        Computes dynamic spatial deviation threshold in physical pixels.
        Threshold = BaseThreshold(ActionCategory) * DPIScale * VelocityAdjustment
        """
        if category == ActionCategory.PRECISE_CLICK:
            # Tight envelope around the click target (8px * DPI)
            base = 8.0
            velocity_factor = 1.0 + min(1.0, velocity_px_per_ms / 2.0)
            return base * self.dpi_scale * velocity_factor

        elif category == ActionCategory.NORMAL_MOVE:
            # Corridor along the Bezier curve (18px * DPI + velocity component)
            base = 18.0
            velocity_factor = 1.0 + min(1.5, velocity_px_per_ms / 1.5)
            return base * self.dpi_scale * velocity_factor

        elif category == ActionCategory.DRAG_OPERATION:
            # Corridor along the drag vector (24px * DPI)
            base = 24.0
            velocity_factor = 1.0 + min(1.2, velocity_px_per_ms / 1.5)
            return base * self.dpi_scale * velocity_factor

        elif category == ActionCategory.TEXT_INPUT:
            # Zero mouse movement expected during typing; low threshold to detect touch/nudge
            base = 4.0
            return base * self.dpi_scale

        elif category == ActionCategory.IDLE:
            # Idle state: any non-injected input is immediately classified as user input
            return 0.0

        return 20.0 * self.dpi_scale

    def plan_bezier_trajectory(
        self,
        start: Point,
        target: Point,
        category: ActionCategory = ActionCategory.NORMAL_MOVE,
        speed_multiplier: float = 1.0,
    ) -> List[TrajectoryPoint]:
        """
        Plans a cubic Bezier movement trajectory from start to target.
        Calculates control points, sample timestamps, expected velocities, and adaptive corridors.
        """
        self.active_category = category
        self.start_pos = start
        self.target_pos = target
        self.start_time_ns = time.perf_counter_ns()

        distance = start.distance_to(target)
        if distance < 1.0:
            # Near-instant movement
            self.total_duration_ms = 10.0
            p0 = TrajectoryPoint(
                x=target.x,
                y=target.y,
                timestamp_ns=self.start_time_ns,
                expected_velocity=0.0,
                threshold_radius=self.calculate_adaptive_threshold(category),
            )
            self.planned_points = [p0]
            return self.planned_points

        # Calculate natural duration based on Fitts' Law / distance heuristic
        # Duration = base + (distance / velocity) with smoothing
        base_speed = 1.8 * self.dpi_scale * speed_multiplier  # px per ms
        if category == ActionCategory.PRECISE_CLICK:
            duration_ms = max(180.0, min(650.0, 150.0 + (distance / base_speed) * 1.3))
        elif category == ActionCategory.DRAG_OPERATION:
            duration_ms = max(250.0, min(900.0, 200.0 + (distance / (base_speed * 0.75))))
        else:
            duration_ms = max(120.0, min(500.0, 100.0 + (distance / base_speed)))

        self.total_duration_ms = duration_ms

        # Cubic Bezier Control Points (P0=start, P1, P2, P3=target)
        # Add slight natural curvature orthogonal to the direct line
        dx = target.x - start.x
        dy = target.y - start.y
        ortho_x = -dy * 0.15
        ortho_y = dx * 0.15

        p1_x = start.x + dx * 0.25 + ortho_x
        p1_y = start.y + dy * 0.25 + ortho_y
        p2_x = start.x + dx * 0.75 - (ortho_x * 0.5)
        p2_y = start.y + dy * 0.75 - (ortho_y * 0.5)

        # Discretize into 8ms intervals (~125Hz simulation rate)
        step_ms = 8.0
        num_steps = max(2, int(duration_ms / step_ms))

        points: List[TrajectoryPoint] = []
        prev_x, prev_y = start.x, start.y

        for i in range(num_steps + 1):
            t = i / float(num_steps)

            # Ease-in-out polynomial easing: 3t^2 - 2t^3
            t_eased = 3.0 * (t ** 2) - 2.0 * (t ** 3)

            # Cubic Bezier Formula
            inv_t = 1.0 - t_eased
            cur_x = (inv_t ** 3) * start.x + 3 * (inv_t ** 2) * t_eased * p1_x + 3 * inv_t * (t_eased ** 2) * p2_x + (t_eased ** 3) * target.x
            cur_y = (inv_t ** 3) * start.y + 3 * (inv_t ** 2) * t_eased * p1_y + 3 * inv_t * (t_eased ** 2) * p2_y + (t_eased ** 3) * target.y

            step_time_ns = self.start_time_ns + int(t * duration_ms * 1_000_000)

            # Velocity in px/ms
            dist_step = math.sqrt((cur_x - prev_x) ** 2 + (cur_y - prev_y) ** 2)
            vel = dist_step / step_ms

            threshold = self.calculate_adaptive_threshold(
                category=category,
                velocity_px_per_ms=vel,
                distance_to_target_px=math.sqrt((target.x - cur_x) ** 2 + (target.y - cur_y) ** 2),
            )

            points.append(
                TrajectoryPoint(
                    x=int(round(cur_x)),
                    y=int(round(cur_y)),
                    timestamp_ns=step_time_ns,
                    expected_velocity=vel,
                    threshold_radius=threshold,
                )
            )
            prev_x, prev_y = cur_x, cur_y

        self.planned_points = points
        return self.planned_points

    def get_expected_state_at(self, timestamp_ns: int) -> Optional[TrajectoryPoint]:
        """
        Interpolates and returns the expected TrajectoryPoint at the given timestamp.
        """
        if not self.planned_points:
            return None

        if timestamp_ns <= self.planned_points[0].timestamp_ns:
            return self.planned_points[0]

        if timestamp_ns >= self.planned_points[-1].timestamp_ns:
            return self.planned_points[-1]

        # Binary search for closest interval
        for i in range(len(self.planned_points) - 1):
            p1 = self.planned_points[i]
            p2 = self.planned_points[i + 1]
            if p1.timestamp_ns <= timestamp_ns <= p2.timestamp_ns:
                dt_total = p2.timestamp_ns - p1.timestamp_ns
                if dt_total == 0:
                    return p1
                ratio = (timestamp_ns - p1.timestamp_ns) / float(dt_total)
                interp_x = int(round(p1.x + (p2.x - p1.x) * ratio))
                interp_y = int(round(p1.y + (p2.y - p1.y) * ratio))
                interp_vel = p1.expected_velocity + (p2.expected_velocity - p1.expected_velocity) * ratio
                interp_thresh = p1.threshold_radius + (p2.threshold_radius - p1.threshold_radius) * ratio
                return TrajectoryPoint(
                    x=interp_x,
                    y=interp_y,
                    timestamp_ns=timestamp_ns,
                    expected_velocity=interp_vel,
                    threshold_radius=interp_thresh,
                )

        return self.planned_points[-1]
