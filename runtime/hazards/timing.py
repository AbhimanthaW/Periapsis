"""Check continuous edge occupation and dwell against moving storm footprints."""
from dataclasses import replace
from math import hypot

import numpy as np

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import FAIL, PASS, UNKNOWN

from .live import storm_at
from .planning import POLICY, planning_mask
from .route import route_timeline


def timed_hazards(feed, support, now, duration_s, state):
    """Use time checks only for fresh, observed storm motion."""
    if state.link_lost:
        return None, None
    moving = tuple(storm for storm in feed.storms if storm.kind == "observed" and any(storm.velocity_mps)
                   and (storm.wind_mps >= POLICY.wind_block_mps or storm.dust_tau >= POLICY.dust_block_tau))
    if not moving:
        return None, None
    stationary = replace(feed, storms=tuple(storm for storm in feed.storms if storm not in moving))
    _, blocked, _, _, _ = planning_mask(stationary, support, now, duration_s)
    return StormTiming(support, now, moving), blocked


class StormTiming:
    def __init__(self, support, now, storms):
        self.support = support
        self.cell_padding = hypot(support.cell_dx_m, support.cell_dy_m) / 2
        self.storms = []
        for storm in storms:
            velocity = np.asarray(storm.velocity_mps)
            initial = np.asarray(storm_at(storm, now, POLICY))
            horizon = max(0.0, POLICY.extrapolate_max_s - (now - parse_utc(storm.observed_utc)).total_seconds())
            self.storms.append((initial, velocity, horizon, storm.radius_m))

    def clear(self, cells, seconds):
        # Include a zero-duration segment when there is only one occupied cell.
        if len(cells) == 1:
            cells = (*cells, cells[0])
            seconds = (*seconds, seconds[0])
        rc = np.asarray(cells)
        a, _, x0, _, e, y0 = self.support.affine
        xy = np.column_stack((x0 + a * (rc[:, 1] + .5), y0 + e * (rc[:, 0] + .5)))
        t0, t1 = np.asarray(seconds[:-1]), np.asarray(seconds[1:])
        duration = t1 - t0
        travel_velocity = (xy[1:] - xy[:-1]) / np.where(duration > 0, duration, 1)[:, None]
        for initial, velocity, horizon, radius in self.storms:
            allowance = np.maximum(POLICY.eta_buffer_s, POLICY.eta_buffer_fraction * t1)
            # Once timing extends beyond the supported motion projection, hold
            # the whole projected swath for that edge. Half the edge length
            # is enough to cover the interior from its two endpoints.
            uncertain = t1 + allowance > horizon
            if uncertain.any():
                segment = velocity * horizon
                length_sq = float(segment @ segment)
                edge_padding = self.cell_padding + np.linalg.norm(xy[1:] - xy[:-1], axis=1) / 2
                for endpoints in (xy[:-1], xy[1:]):
                    offset = endpoints[uncertain] - initial
                    fraction = np.clip(offset @ segment / length_sq, 0, 1) if length_sq else np.zeros(len(offset))
                    if np.any(np.linalg.norm(offset - fraction[:, None] * segment, axis=1)
                              <= radius + edge_padding[uncertain]):
                        return False
            active = ~uncertain
            if active.any():
                delta = xy[:-1][active] - initial - t0[active, None] * velocity
                relative = travel_velocity[active] - velocity
                speed_sq = np.sum(relative * relative, axis=1)
                closest = np.clip(-np.sum(delta * relative, axis=1) / np.where(speed_sq > 0, speed_sq, 1),
                                  0, duration[active])
                padding = self.cell_padding + np.linalg.norm(velocity) * allowance[active]
                if np.any(np.linalg.norm(delta + closest[:, None] * relative, axis=1) <= radius + padding):
                    return False
        return True

    def rule(self, candidate, router):
        timeline = route_timeline(candidate, router)
        if not timeline:
            return UNKNOWN, "route times are unavailable"
        cells, seconds, _ = zip(*timeline)
        if not self.clear(cells, seconds):
            return FAIL, "a storm overlaps the route during traversal or science dwell"
        return PASS, "route and dwell clear the projected storm windows"

    def clear_leg(self, leg, router, elapsed_s):
        edges = np.asarray(leg.edge_ids, dtype=int)
        times = elapsed_s + np.r_[0, np.cumsum(router.graph.times.seconds[edges])]
        return self.clear(leg.cells, times)
