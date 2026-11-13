"""Built-in SYNTHETIC demo terrain (not Mars data) for trying the pipeline
without a pack: 800 m x 800 m at 5 m, a scarp with two gentle ramps, boulder
mounds, a coverage gap, and a simulated closure of the north ramp."""
import numpy as np

from .config import HumanProfile, MissionSnapshot, Task
from .environment import EnvironmentalVariable, PowerScenario
from .traversability import ScreenPolicy, TerrainSupport, build_baseline

CELL_M = 5.0
N = 160
NORTH_RAMP_CLOSURE = "north-ramp"


def demo_terrain(seed=0):
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:N, 0:N].astype(float) + 0.5) * CELL_M
    b1 = np.exp(-((y - 205) ** 2) / (2 * 25 ** 2))
    b2 = np.exp(-((y - 560) ** 2) / (2 * 30 ** 2))
    width = 2 + 40 * (b1 + b2)
    z = 25 * np.exp(-((x - 380) ** 2 + (y - 420) ** 2) / (2 * 140 ** 2))
    z += 14.0 / (1 + np.exp(-(x - 0.35 * y - 430) / width))
    for cx, cy in rng.uniform([200, 150], [320, 300], (25, 2)):
        z += 4.0 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * 4.0 ** 2))
    valid = np.ones((N, N), bool)
    valid[124:144, 12:40] = False                                   # coverage gap
    closure = (np.abs(x - 0.35 * y - 430) < 25) & (y > 150) & (y < 260)
    return np.where(valid, z, np.nan), valid, tuple(map(tuple, np.argwhere(closure).tolist()))


DEMO_TIME_UTC = "2021-02-18T20:43:49Z"          # Perseverance landing (spacecraft time), for context only
DEMO_SITE = (18.44, 77.45)                        # declared site coordinates used ONLY for sun geometry


def sep_scenario(time_utc=DEMO_TIME_UTC):
    """Explicit, SIMULATED solar particle event scenario (modelled on the
    kind of event MSL-RAD recorded in September 2017). Not a forecast."""
    return EnvironmentalVariable(
        id="sep-drill", variable="solar_particle_event", mode="explicit_scenario", effect="return_now",
        purpose="rehearse a shelter return", authorized_by="demo operator", provenance="simulated",
        valid_from_utc=time_utc, note="simulated alert; no dose is inferred")


def demo_power():
    """HYPOTHETICAL horizontal solar array; transmittance is a declared dust assumption."""
    return PowerScenario(kind="solar_derived", provenance="assumed", panel_area_m2=6.0,
                         panel_efficiency=0.25, atmospheric_transmittance=0.6)


def demo_inputs(*, closed=False, remaining_s=3600, pace_scenario="nominal", crew_status="ok",
                platform="human", sep_alert=False, with_time=True):
    z, valid, closure_cells = demo_terrain()
    support = TerrainSupport.from_affine((N, N), (CELL_M, 0, 0, 0, -CELL_M, N * CELL_M),
                                         native_spacing_m=CELL_M, vertical_reference="synthetic-demo",
                                         pack_id="marswalk-synthetic-demo", pack_version="demo")
    policy = ScreenPolicy(policy_id="demo-slope-15deg", slope_limit_deg=15.0)
    baseline = build_baseline(support, z, valid, policy=policy)
    tasks = (Task("transect", (30, 102), 15 * 60, 2, "measure bedding across the upper scarp", "scaled bedding transect"),
             Task("photo-set", (65, 62), 8 * 60, 1, "photograph exposed beds", "oriented photo set"))
    snapshot = MissionSnapshot(
        mission_id="demo", revision=2 if closed else 1, pack_id=support.pack_id, pack_version=support.pack_version,
        scenario_id="demo-north-ramp", current_cell=(50, 80), return_cell=(80, 40), tasks=tasks,
        completed_task_ids=(), remaining_s=remaining_s, reserve_s=15 * 60,
        closures=((NORTH_RAMP_CLOSURE, closure_cells),) if closed else (),
        profile=_profile(platform, pace_scenario), crew_status=crew_status,
        provenance=(("terrain", "simulated"), ("closures", "simulated"), ("remaining_s", "crew_input")),
        time_utc=DEMO_TIME_UTC if with_time else None,
        site_lat_deg=DEMO_SITE[0] if with_time else None, site_lon_east_deg=DEMO_SITE[1] if with_time else None,
        environment=(sep_scenario(),) if sep_alert else (),
        power=demo_power() if platform == "rover" else None)
    return baseline, snapshot


def _profile(platform, pace_scenario):
    if platform == "rover":
        from .rover import hypothetical_crew_rover
        return hypothetical_crew_rover()
    return HumanProfile(pace_scenario=pace_scenario)


def plot(result_before, result_after, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    base = result_after.baseline
    rows, cols = base.support.shape
    ext = [0, cols * CELL_M, rows * CELL_M, 0]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.4), constrained_layout=True)
    for ax, res, title in ((axes[0], result_before, "Before closure"), (axes[1], result_after, "After closure")):
        ax.imshow(base.z_m, cmap="Greys_r", extent=ext, alpha=0.8)
        overlay = np.where(base.known_excluded, 1.0, np.where(base.unknown, 2.0, np.nan))
        ax.imshow(overlay, cmap="Set1", extent=ext, alpha=0.55, vmin=1, vmax=9)
        for cid, cells in res.snapshot.closures:
            cr = [c[0] for c in cells]; cc = [c[1] for c in cells]
            ax.scatter(np.array(cc) * CELL_M + 2.5, np.array(cr) * CELL_M + 2.5, s=3, c="black", marker="x")
        colours = {"direct_return": "#1f77b4", "science:transect": "#e67e22", "science:photo-set": "#27ae60"}
        for plan in res.plans:
            for name, leg in plan.legs:
                if leg.ok:
                    rc = np.array(leg.cells)
                    ax.plot(rc[:, 1] * CELL_M + 2.5, rc[:, 0] * CELL_M + 2.5, color=colours.get(plan.id, "purple"),
                            lw=2, ls="-" if name != "return" else "--",
                            label=f"{plan.id} {name}" + (" ✓" if plan.passed else " ✗"))
        snap = res.snapshot
        for cell, label, marker in ((snap.current_cell, "crew", "o"), (snap.return_cell, "shelter", "s")):
            ax.plot(cell[1] * CELL_M + 2.5, cell[0] * CELL_M + 2.5, marker, ms=9, mfc="white", mec="black")
            ax.annotate(label, (cell[1] * CELL_M, cell[0] * CELL_M), xytext=(6, 6), textcoords="offset points")
        for task in snap.tasks:
            ax.plot(task.approach_cell[1] * CELL_M + 2.5, task.approach_cell[0] * CELL_M + 2.5, "*", ms=14,
                    mfc="gold", mec="black")
        ax.set_title(f"{title}: status {res.status}, recommend {res.recommendation}")
        ax.legend(loc="lower right", fontsize=7)
    who = "Rover" if result_after.snapshot.profile.platform == "rover" else "Human"
    fig.suptitle(f"{who} Marswalk pipeline on SYNTHETIC terrain (red = excluded, grey-blue = no data)")
    fig.savefig(path, dpi=100)
