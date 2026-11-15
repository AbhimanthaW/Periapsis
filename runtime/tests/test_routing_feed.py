from itertools import takewhile
import json
from queue import Queue
from threading import Event, Thread

import pytest

from runtime.planning_api import create_server
from runtime.routing_feed import EXAMPLE, FeedError, RoutingClient, main, reports, run
from runtime.tests.test_final_routing import forecast_artifact, reading, utc


@pytest.fixture
def routing_url(forecast_artifact):
    with create_server(0, final_routing_model=forecast_artifact) as server:
        http = Thread(target=server.serve_forever, daemon=True)
        http.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            http.join()


def test_replay_sends_reports_and_weather_expiry_and_resumes(routing_url, tmp_path, capsys):
    lines = EXAMPLE.read_bytes().splitlines(keepends=True)
    log = tmp_path / "mission.jsonl"
    log.write_bytes(lines[0])
    args = [str(log), "--url", routing_url]
    assert main(args) == 0
    initial = json.loads(capsys.readouterr().out)
    assert initial["revision"] == 1
    with log.open("ab") as out:
        out.writelines(lines[1:])
    assert main(args) == 0
    storm, expired_weather, expired_hazard, recovered = map(json.loads, capsys.readouterr().out.splitlines())
    assert [storm["revision"], expired_weather["revision"], expired_hazard["revision"], recovered["revision"]] == [2, 3, 4, 5]
    for platform in ("human", "rover"):
        assert storm[platform]["return_m"] == initial[platform]["return_m"]
        assert expired_hazard[platform]["return_m"] > storm[platform]["return_m"]
        assert recovered[platform]["return_m"] < expired_hazard[platform]["return_m"]
    assert expired_weather["update"] == expired_hazard["update"] == "weather_recheck"
    assert expired_weather["weather_link_lost"]
    assert recovered["position"] == [36, 108] and not recovered["weather_link_lost"]
    latest = RoutingClient(routing_url).plan
    assert latest["spatial_hazards"]["blocked_for_plan"] == []
    assert latest["tradeoff"]["model"]["oxygen_update"]["applied_factors"]["EV1"] > 1.3
    assert latest["rover_charge_wh"] == 15880
    assert main(args) == 0 and capsys.readouterr().out == ""

    log.write_bytes(log.read_bytes().replace(b'"value":8,', b'"value":9,', 1))
    assert main(args) == 2
    assert "does not match" in capsys.readouterr().err
    assert RoutingClient(routing_url).revision == 5


def test_follow_posts_a_new_report_when_the_line_is_complete(routing_url, tmp_path):
    log = tmp_path / "incoming.jsonl"
    log.touch()
    client = RoutingClient(routing_url)
    time = client.site["start_time_utc"]
    updates, stop = Queue(), Event()
    source = takewhile(lambda _: not stop.is_set(), reports(log, follow=True, poll_s=0.02))

    def feed():
        try:
            run(client, source, follow=True, emit=updates.put)
        except (FeedError, OSError) as error:
            updates.put(str(error))

    worker = Thread(target=feed, daemon=True)
    worker.start()
    try:
        now = utc(time, 599.5)
        report = {"time_utc": now, "current_cell": [36, 109], "weather_readings": [
            reading("wind_speed", 8, "m/s", time), reading("dust_optical_depth", 0.72, "1", time),
        ]}
        with log.open("ab") as out:
            out.write(json.dumps(report).encode())
        assert RoutingClient(routing_url).revision == 0
        with log.open("ab") as out:
            out.write(b"\n")
        accepted = json.loads(updates.get(timeout=10))
        assert accepted["revision"] == 1 and not accepted["weather_link_lost"]
        tick = json.loads(updates.get(timeout=10))
        assert tick["revision"] == 2 and tick["update"] == "weather_recheck"
        assert tick["weather_link_lost"] and tick["source_time_utc"] == now
    finally:
        stop.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
