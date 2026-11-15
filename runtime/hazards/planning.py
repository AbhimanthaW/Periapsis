"""Normalize spatial input revisions and compute a conservative planning mask."""
from dataclasses import replace
from datetime import timedelta
from math import hypot

import numpy as np

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import MarswalkError

from .live import LivePolicy, _cell_centres, feed_from_dict, hazard_state, storm_at

POLICY = LivePolicy()


def update_feed(previous, raw, support, now):
    if raw is None:
        return previous
    incoming = feed_from_dict(raw, support)
    if incoming.provenance != "simulated" or any(item.provenance != "simulated"
            for item in (*incoming.storms, *incoming.layers, *incoming.alerts)):
        raise MarswalkError("INVALID_HAZARD", "the integrated drill accepts simulated spatial data")
    if previous is not None and previous.feed_id != incoming.feed_id:
        raise MarswalkError("INVALID_HAZARD", "spatial feed identity changed in a running drill")
    for storm in incoming.storms:
        if (max(map(abs, storm.centre_m)) > 1e7 or storm.radius_m > 1e7
                or hypot(*storm.velocity_mps) > 100 or storm.wind_mps > 100 or storm.dust_tau > 15):
            raise MarswalkError("INVALID_HAZARD", "storm position, radius, wind, motion or opacity is outside the drill range")
    for layer in incoming.layers:
        limit = 100 if layer.variable == "wind_speed" else 15
        if np.isinf(layer.values).any() or (layer.values > limit).any():
            raise MarswalkError("INVALID_HAZARD", f"invalid values in {layer.variable} raster")

    def latest(old, updates, key):
        records = {key(item): item for item in old}
        for item in sorted(updates, key=lambda value: parse_utc(value.observed_utc)):
            stamp = parse_utc(item.observed_utc)
            if stamp > now:
                raise MarswalkError("INVALID_HAZARD", "spatial observation is in the future")
            previous_item = records.get(key(item))
            if previous_item is not None:
                prior_stamp = parse_utc(previous_item.observed_utc)
                if stamp < prior_stamp:
                    continue
                if stamp == prior_stamp:
                    if _same_observation(item, previous_item):
                        continue
                    raise MarswalkError("STALE_HAZARD", "conflicting spatial observations at the same timestamp")
            records[key(item)] = item
        if len(records) > 64:
            raise MarswalkError("INVALID_HAZARD", "the drill supports at most 64 active entries per input family")
        return tuple(records.values())

    old = previous or replace(incoming, storms=(), layers=(), alerts=())
    return replace(incoming,
                   storms=latest(old.storms, incoming.storms, lambda item: (item.storm_id, item.kind)),
                   layers=latest(old.layers, incoming.layers, lambda item: (item.variable, item.kind)),
                   alerts=latest(old.alerts, incoming.alerts, lambda item: (item.alert_id, item.kind)))


def _same_observation(a, b):
    if hasattr(a, "values"):
        return (np.array_equal(a.values, b.values, equal_nan=True)
                and replace(a, values=b.values) == b)
    return a == b


def planning_mask(feed, support, now, duration_s):
    """Include every cell that can intersect an observed storm during the plan."""
    # Evaluate observed and forecast layers separately so a forecast of the same
    # storm cannot replace its observation in the original mapper's ID lookup.
    actual = replace(feed, storms=tuple(s for s in feed.storms if s.kind == "observed"),
                     layers=tuple(l for l in feed.layers if l.kind == "observed"),
                     alerts=tuple(a for a in feed.alerts if a.kind == "observed"))
    forecast = replace(feed, storms=tuple(s for s in feed.storms if s.kind == "forecast"),
                       layers=tuple(l for l in feed.layers if l.kind == "forecast"), alerts=())
    now_utc = now.isoformat()
    current = hazard_state(actual, support, now_utc, POLICY)
    advisory = hazard_state(forecast, support, now_utc, POLICY)
    blocked = current.blocked.copy()
    finish = now + timedelta(seconds=duration_s)
    east, north = _cell_centres(support)
    buffer_m = hypot(support.cell_dx_m, support.cell_dy_m) / 2
    for storm in actual.storms:
        if storm.wind_mps < POLICY.wind_block_mps and storm.dust_tau < POLICY.dust_block_tau:
            continue
        observed = parse_utc(storm.observed_utc)
        stale = (now - observed).total_seconds() > POLICY.max_age_s
        start = observed if stale else now
        end = max(finish, observed + timedelta(seconds=POLICY.extrapolate_max_s)) if stale else finish
        x0, y0 = storm_at(storm, start, POLICY)
        x1, y1 = storm_at(storm, end, POLICY)
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        fraction = 0 if length_sq == 0 else np.clip(((east - x0) * dx + (north - y0) * dy) / length_sq, 0, 1)
        blocked |= np.hypot(east - x0 - fraction * dx, north - y0 - fraction * dy) <= storm.radius_m + buffer_m
    radiation = any(parse_utc(alert.start_utc) <= finish and
                    (alert.end_utc is None or parse_utc(alert.end_utc) > now) for alert in actual.alerts)
    no_solar = (np.any(current.dust_tau >= POLICY.dust_block_tau)
                or any(storm.dust_tau >= POLICY.dust_block_tau for storm in actual.storms))
    return current, blocked, (current.caution | advisory.caution) & ~blocked, radiation, bool(no_solar)
