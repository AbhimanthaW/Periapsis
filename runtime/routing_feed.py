"""Feed recorded or newly appended mission reports into the routing API."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from math import isfinite
from os import fstat
from pathlib import Path
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from contracts.pack import PackError, decode
from runtime.final_routing import RoutingRequest
from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import MarswalkError

EXAMPLE = Path(__file__).with_name("examples") / "routing-feed-simulated.jsonl"
API_FIELDS = {"schema_version", "request_id", "pack_id", "pack_version", "expected_revision"}
REPORT_FIELDS = RoutingRequest.model_fields.keys() - API_FIELDS
MISSION_FIELDS = ("current_cell", "objective", "confirmed_task_ids", "completed_task_ids")
MAX_REPORT_BYTES = 256_000


class FeedError(RuntimeError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def reports(path, *, follow=False, poll_s=0.25):
    """Yield complete reports from an append-only log, or None when idle."""
    fingerprint = sha256()
    previous_time = None
    number = 0
    with path.open("rb") as source:
        opened = fstat(source.fileno())
        while True:
            offset = source.tell()
            raw = source.readline(MAX_REPORT_BYTES + 1)
            if len(raw) > MAX_REPORT_BYTES:
                raise FeedError(f"line {number + 1} exceeds {MAX_REPORT_BYTES} bytes")
            if not raw or (follow and not raw.endswith(b"\n")):
                if not follow:
                    return
                current = path.stat()
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or current.st_size < offset:
                    raise FeedError("the input log was replaced or truncated; retain the original append-only log")
                source.seek(offset)
                yield None
                sleep(poll_s)
                continue
            number += 1
            if not raw.strip():
                continue
            try:
                item = decode(raw)
                if not isinstance(item, dict) or item.keys() - REPORT_FIELDS or not {"time_utc", "current_cell"} <= item.keys():
                    raise FeedError("expected routing input fields including time_utc and current_cell")
                reported = parse_utc(item["time_utc"])
                if previous_time is not None and reported < previous_time:
                    raise FeedError("source time moved backwards")
                fingerprint.update(_json(item) + b"\n")
            except (FeedError, PackError, MarswalkError, ValueError) as error:
                raise FeedError(f"line {number}: {error}") from error
            previous_time = reported
            yield f"routing-feed-{number}-{fingerprint.hexdigest()[:24]}", item


class RoutingClient:
    def __init__(self, url):
        self.base = url.rstrip("/") + "/api/v1/routing"
        self.site = self.request("site")
        current = self.request("plan")
        self.revision, self.plan = current["revision"], current["plan"]

    def request(self, path, payload=None):
        body = None if payload is None else _json(payload)
        request = Request(f"{self.base}/{path}", data=body, headers={"Content-Type": "application/json"} if body else {})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=15) as response:
                    return json.load(response)
            except HTTPError as error:
                message = error.read(2048).decode("utf-8", errors="replace")
                raise FeedError(f"routing API returned HTTP {error.code}: {message}") from error
            except (OSError, URLError) as error:
                if attempt == 2:
                    raise FeedError(f"routing API could not be reached: {error}") from error
                sleep(0.25 * (attempt + 1))

    def send(self, request_id, observation):
        body = observation | {
            "schema_version": 1,
            "request_id": request_id,
            "pack_id": self.site["pack_id"],
            "pack_version": self.site["pack_version"],
            "expected_revision": self.revision,
        }
        body.setdefault("include_shortest_distance", False)
        self.plan = self.request("plan", body)
        self.revision = self.plan["revision"]
        return self.plan


def summary(plan, kind, source_time):
    result = {"update": kind, "revision": plan["revision"], "time_utc": plan["time_utc"],
              "source_time_utc": source_time, "position": plan["current_cell"],
              "weather_link_lost": plan["observed_weather"]["link_lost"]}
    for platform in ("human", "rover"):
        current = plan[platform]
        result[platform] = {"status": current["status"], "recommendation": current["recommendation"],
                            "return_m": current["direct_return"]["length_m"],
                            "return_s": current["direct_return"]["seconds"]}
    return result


def run(client, source, *, follow=False, rate=0, emit=print):
    """Advance one source in order, using clock-only requests at weather expiry."""
    last = None
    anchor = monotonic()
    outstanding = None if client.plan is None else client.plan["request_id"]

    def publish(token, report, when, kind):
        nonlocal anchor
        plan = client.send(token, report | {"time_utc": when})
        anchor = monotonic()
        emit(json.dumps(summary(plan, kind, last[1]["time_utc"])))

    def next_check():
        return None if client.plan is None else client.plan["weather_recheck_utc"]

    def wait_for(when):
        if rate and client.plan is not None and not follow:
            delta = (parse_utc(when) - parse_utc(client.plan["time_utc"])).total_seconds()
            sleep(max(0, delta / rate - (monotonic() - anchor)))

    def expire(when):
        token, report = last
        # Current position and task state are the last report's. No sensor
        # observations or burn-rate telemetry are invented for a clock tick.
        tick = {key: report[key] for key in MISSION_FIELDS if key in report}
        publish(f"{token}-clock-{client.revision}", tick, when, "weather_recheck")

    for entry in source:
        if entry is None:
            due = next_check()
            if last and due and (monotonic() - anchor >=
                                (parse_utc(due) - parse_utc(client.plan["time_utc"])).total_seconds()):
                expire(due)
            if outstanding is not None:
                raise FeedError("the running plan does not match the input log")
            continue
        token, report = entry
        if outstanding is not None:
            if outstanding == token or outstanding.startswith(token + "-clock-"):
                last, outstanding = entry, None
                anchor = monotonic()
            continue
        source_time = report["time_utc"]
        while last and (due := next_check()) and parse_utc(due) < parse_utc(source_time):
            wait_for(due)
            expire(due)
        when = source_time
        if client.plan is not None and parse_utc(when) < parse_utc(client.plan["time_utc"]):
            when = client.plan["time_utc"]  # A clock tick may already have advanced the planner.
        wait_for(when)
        last = entry
        publish(token, report, when, "source_report")
    if outstanding is not None:
        raise FeedError("the running plan does not match the input log")


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=EXAMPLE, help="append-only JSON Lines mission log")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="planning server base URL")
    parser.add_argument("--follow", action="store_true", help="watch the log for new reports and weather expiries")
    parser.add_argument("--rate", type=float, default=0, help="replay speed multiplier; zero replays immediately")
    parser.add_argument("--poll-s", type=float, default=0.25, help="log polling interval in follow mode")
    args = parser.parse_args(argv)
    if not isfinite(args.rate) or args.rate < 0 or (args.follow and args.rate):
        parser.error("--rate must be finite, nonnegative and used only for replay")
    if not isfinite(args.poll_s) or args.poll_s <= 0:
        parser.error("--poll-s must be finite and positive")
    try:
        client = RoutingClient(args.url)
        run(client, reports(args.source, follow=args.follow, poll_s=args.poll_s),
            follow=args.follow, rate=args.rate, emit=lambda line: print(line, flush=True))
    except (FeedError, OSError, ValueError, MarswalkError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
