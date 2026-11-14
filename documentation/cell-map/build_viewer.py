"""Build an offline HTML preview from the verified cell database."""
from base64 import b64encode
import gzip
from hashlib import file_digest
from html import escape
import json
import os
import sqlite3

from marsdoc import Grid
import numpy as np

from workspace import build_workspace

root = build_workspace()
science_mode = os.environ.get("RW_SCIENCE_VIEW") == "1"
science = []
if science_mode:
    with gzip.open(root / "science/cell-science.ndjson.gz", "rt") as stream:
        science = [json.loads(line) for line in stream]
    assert len(science) == 196608
expansion = []
expanded_sources = {}
if os.environ.get("RW_EXPANDED_VIEW") == "1":
    assert science
    with gzip.open(root / "expansion/cell-expansion.ndjson.gz", "rt") as stream:
        expansion = [json.loads(line) for line in stream]
    assert len(expansion) == 196608
    expanded_sources = json.loads((root / "expansion/manifest.json").read_bytes())["sources"]
ranking_layers = {
    "paleolakes": "Published paleolake basins",
    "chlorides": "Published chloride sites",
    "hydrated_mineral_sites": "NASA PDS hydrated-mineral detections",
    "structures": "USGS mapped structures · approximate km",
    "gazetteer": "IAU/USGS named feature centres",
    "gazetteer_approximate_bounds": "IAU/USGS named feature bounds · approximate",
    "dunes": "USGS equatorial and south polar dune sites",
    "cave_candidates": "USGS cave entrance candidates",
    "marsquakes": "InSight event locations · quality A/B",
}
ranking_mode = os.environ.get("RW_RANKING_VIEW") == "1"
ranking = []
feature_index = {}
if ranking_mode:
    if not expansion:
        raise ValueError("RW_RANKING_VIEW requires RW_SCIENCE_VIEW and RW_EXPANDED_VIEW")
    ranking_dir = root / "ranking"
    ranking_manifest = json.loads((ranking_dir / "manifest.json").read_bytes())
    for filename in ("cell-ranking.ndjson.gz", "ranking-features.json.gz"):
        with (ranking_dir / filename).open("rb") as raw:
            if file_digest(raw, "sha256").hexdigest() != ranking_manifest["files"][filename]["sha256"]:
                raise ValueError(f"ranking export does not match manifest: {filename}")
    with gzip.open(ranking_dir / "cell-ranking.ndjson.gz", "rt") as stream:
        ranking = [json.loads(line) for line in stream]
    if len(ranking) != Grid().count:
        raise ValueError("ranking export has an unexpected cell count")
    with gzip.open(ranking_dir / "ranking-features.json.gz", "rt") as stream:
        feature_index = {layer: {item["id"]: item for item in items}
                         for layer, items in json.load(stream).items()}


synthetic_mode = os.environ.get("RW_SYNTHETIC_SCIENCE_VIEW") == "1"
synthetic_layers = {}
synthetic_rows = {}
example_id = "HPX128:96848"
synthetic_bounds = None
fixture_shapes = {}
eva_examples = {}
if synthetic_mode:
    from marsdoc.synthetic_science import FIELDS, METHODS, PREVIEW_BOUNDS, RECIPE

    if not ranking_mode:
        raise ValueError("RW_SYNTHETIC_SCIENCE_VIEW requires the sourced map layers")
    fixture_path = root / "synthetic-science/synthetic-science-context.json"
    fixture = json.loads(fixture_path.read_bytes())
    grid = Grid()
    if (fixture["schema_version"], fixture["data_status"], fixture["recipe_id"], fixture["grid"],
        fixture["grid_cell_count"]) != (1, "synthetic", RECIPE, "HPX128 NESTED", grid.count):
        raise ValueError("unexpected synthetic science fixture identity")
    if fixture["methods"] != METHODS:
        raise ValueError("unexpected synthetic fixture methods")
    example_id = fixture["example_cell_id"]
    synthetic_layers = FIELDS
    synthetic_bounds = PREVIEW_BOUNDS
    for record in fixture["cells"]:
        index = grid.parse_id(record["cell_id"])
        if (index in synthetic_rows or record["data_status"] != "synthetic" or record["recipe_id"] != RECIPE
                or record["fields"].keys() != FIELDS.keys()):
            raise ValueError(f"invalid synthetic fixture cell {index}")
        synthetic_rows[index] = record["fields"]
    if grid.parse_id(example_id) not in synthetic_rows:
        raise ValueError("synthetic fixture lacks its example cell")

    from marsdoc import DocumentationEngine, Package
    from marsdoc.eva_context import CASES, read_data
    from marsdoc.science_context import OLIVINE_THRESHOLD
    from marsdoc.synthetic_science import DEPOSITS, SPECTRAL_TILES, SURVEY_PART, VALLEYS

    def display_path(vertices):
        x, y, z = vertices.T
        return np.column_stack((np.rad2deg(np.arctan2(y, x)),
                                np.rad2deg(np.arctan2(z, np.hypot(x, y))))).tolist()

    fixture_shapes = {
        "survey": [display_path(SURVEY_PART.rings[0])],
        "deltas": [display_path(f.part.rings[0]) for f in DEPOSITS if f.kind == "scarp_fronted_deposit"],
        "alluvial_fans": [display_path(f.part.rings[0]) for f in DEPOSITS if f.kind == "alluvial_fan"],
        "glacial_landforms": [display_path(f.part.rings[0]) for f in DEPOSITS
                              if f.kind in {"lobate_debris_apron", "lineated_valley_fill", "concentric_crater_fill"}],
        "valley_networks": [display_path(f.vertices) for f in VALLEYS],
        "olivine": [display_path(tile.part.rings[0]) for tile in SPECTRAL_TILES
                    if tile.indices is not None and max(tile.indices) > OLIVINE_THRESHOLD],
    }
    package = Package(schema_version=1, package_id="offline-eva-preview", version="1",
                      datasets=(), products=(), footprints=())
    engine = DocumentationEngine(package)
    anchors = {"synthetic": read_data("scenario-v1.json")["site_lon_lat"]}
    anchors.update({key: item["anchor_lon_lat"] for key, item in read_data("historical-v1.json").items()})
    eva_examples = {case: engine.eva_context(engine.grid.cell_at(anchors[case]).id, case=case) for case in CASES}


def layer_label(key, identifier):
    feature = feature_index["gazetteer" if key == "gazetteer_approximate_bounds" else key][identifier]
    if key == "structures":
        return f'{feature["interpretation"]} (SIM 3292 #{identifier})'
    if key == "cave_candidates":
        return f'{identifier} ({feature["candidate_type"]})'
    if key == "dunes":
        return feature["dune_id"]
    if key == "marsquakes":
        return f'{feature["contributor_id"]} ({feature["event_type"]})'
    return feature.get("name", feature.get("label", identifier))


def ranking_display(evidence):
    display = {}
    for key, records in evidence.items():
        values = list(records)
        labels = [layer_label(key, identifier) for identifier in values[:8]]
        if key == "structures":
            value = round(sum(records.values()), 2)
        elif key == "gazetteer_approximate_bounds":
            value = max(records.values())
        else:
            value = len(values)
        if len(values) > len(labels):
            labels.append(f"+{len(values) - len(labels)} more")
        display[key] = [value, ", ".join(labels)]
    return display


width, height = 1440, 720
def map_pixels(bounds):
    west, south, east, north = bounds
    lon, lat = np.meshgrid(west + (np.arange(width) + .5) / width * (east - west),
                           north - (np.arange(height) + .5) / height * (north - south))
    return Grid().indices(np.stack((lon, lat), axis=-1)).astype("<u4")


pixels = map_pixels((-180, -90, 180, 90))
local_pixels = map_pixels(synthetic_bounds) if synthetic_bounds else None
with sqlite3.connect(f"file:{root / 'map/cells.sqlite'}?mode=ro", uri=True) as db:
    data = []
    for i, x, y, z, n, encoded in db.execute(
        "SELECT nested_index, longitude_deg_east, latitude_deg_planetocentric, "
        "mola_elevation_m, mola_observation_count, metadata_json FROM cells ORDER BY nested_index"
    ):
        row = json.loads(encoded)
        terrain = row["modalities"]["stereo_topography"]
        imagery = row["modalities"]["fine_imagery"]
        assert i == len(data)
        local = science[i] if science else {}
        assert not local or local["cell_id"] == f"HPX128:{i}"
        extra = expansion[i] if expansion else {}
        assert not extra or extra["cell_id"] == f"HPX128:{i}"
        sourced = ranking[i] if ranking_mode else {}
        if sourced and sourced["cell_id"] != f"HPX128:{i}":
            raise ValueError(f"ranking cell ID mismatch at {i}")
        ice = extra.get("swim_ice_consistency", {})
        dust = extra.get("tes_dust_my25_sol001", {})
        data.append([x, y, z, n, terrain["observed_fraction"], terrain["usable_fraction"],
                     imagery["observed_fraction"], row["terrain"]["bounds"]["lower"],
                     [item["name"] for item in row["named_feature_anchors"]],
                     [[u["code"], u["name"]] for u in local.get("geologic_units", [])],
                     local.get("tes_night_thermal_inertia"), local.get("tes_night_sample_status"), len(local.get("crism_mtrdr_product_ids", [])),
                     extra.get("ctx_edr_centroid_records"), extra.get("hirise_projected_centroid_records"),
                     len(extra.get("hirise_dtm_centroid_product_ids", [])), ice.get("0_1"), ice.get("1_5"),
                     ice.get("5"), dust.get("opacity"), extra.get("tes_lambert_albedo"),
                     ranking_display(sourced["evidence"]) if sourced else {}])

def pack(data):
    return b64encode(gzip.compress(data, mtime=0)).decode("ascii")

html = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__MAP_TITLE__</title>
<style>
body{background:#161a21;color:#edf0f4;margin:0 auto;max-width:1180px;padding:1.5rem;font:16px system-ui}
p{color:#b5bdc8;line-height:1.5}select,input,button{font:inherit;padding:.35rem;margin:.3rem 0}
canvas{display:block;width:100%;height:auto;background:#252d39;cursor:crosshair;margin-top:1rem}
#eva{margin:1rem 0}#eva table{width:100%;border-collapse:collapse}#eva td,#eva th{text-align:left;padding:.45rem;border-bottom:1px solid #465162}#eva p{margin:.4rem 0}
#details{white-space:pre-wrap;line-height:1.6;padding:1rem;background:#222935}
</style>
<h1>__MAP_TITLE__</h1>
__SYNTHETIC_NOTE__
<p>196,608 cells · Nside 128 · Return Window · East-positive Mars coordinates</p>
<label>Layer <select id="layer">
<option value="elevation">MOLA elevation</option><option value="counts">MOLA observation count</option>
<option value="stereo">Stereo terrain catalogue coverage</option><option value="usable">Verified usable stereo terrain</option>
<option value="imagery">HiRISE imagery · local catalogue search</option>
__SCIENCE_OPTIONS__
</select></label>
<form id="search"><label>Cell ID <input id="cell" value="__EXAMPLE_ID__"></label> <button>Inspect</button></form>
__PREVIEW_CONTROLS__
<canvas width="1440" height="720" id="map" aria-label="Mars evidence map. Use the cell ID input for keyboard inspection."></canvas>
<p id="legend"></p><section id="details" aria-live="polite">Loading local evidence…</section>
<p>MOLA values sample the native pixel at the cell centre. Catalogue coverage reflects imported outlines.
Dark areas on catalogue layers have no imported coverage and remain unknown. Sparse catalogue layers use a bright marker for every cell with a positive imported fraction. Verified stereo terrain is limited to the Jezero window in this release.
__SCIENCE_NOTE__</p>
<script>
const view = document.querySelector('#map'), ctx = view.getContext('2d');
const layer = document.querySelector('#layer'), details = document.querySelector('#details');
const field = document.querySelector('#cell'), legend = document.querySelector('#legend');
const palettes = {elevation:[2,-8200,22000,[26,46,86],[255,209,153],'Elevation · dark blue −8,200 m to pale orange +22,000 m'],
counts:[3,0,1,[22,35,52],[253,207,114],'Observation count · dark to bright on a logarithmic scale'],
stereo:[4,0,1,[34,42,55],[255,167,97],'Stereo catalogue coverage · 0 to 100%'],
usable:[5,0,1,[34,42,55],[111,227,200],'Verified stereo terrain support · 0 to 100%'],
imagery:[6,0,1,[34,42,55],[159,194,255],'HiRISE image catalogue coverage · 0 to 100%'],
crism:[12,0,1,[34,42,55],[255,135,194],'CRISM MTRDR · catalogue footprints containing cell centre'],
geology:[9,0,1,[34,42,55],[210,158,110],'USGS SIM 3292 · colours distinguish mapped geologic units'],
thermal:[10,0,800,[29,48,106],[255,212,112],'Nightside TES thermal inertia · 0 to 800 J m⁻² K⁻¹ s⁻¹ᐟ²; interpolated samples dimmed'],
ctxcat:[13,0,2,[34,42,55],[120,225,195],'CTX acquisition records at cell centre · logarithmic scale'],
hirisecat:[14,0,2,[34,42,55],[159,194,255],'HiRISE projected-image catalogue records at cell centre · logarithmic scale'],
hirstereo:[15,0,1,[34,42,55],[255,167,97],'ODE HiRISE DTM catalogue records at cell centre'],
ice01:[16,-1,1,[211,132,84],[117,211,246],'SWIM 0–1 m ice consistency · −1 to +1; grey is outside coverage'],
ice15:[17,-1,1,[211,132,84],[117,211,246],'SWIM 1–5 m ice consistency · −1 to +1; grey is outside coverage'],
ice5:[18,-1,1,[211,132,84],[117,211,246],'SWIM >5 m ice consistency · −1 to +1; grey is outside coverage'],
dust:[19,0,1,[33,56,101],[252,170,84],'TES historical column dust optical depth · MY25 sol 001 · 9.3 µm'],
albedo:[20,0,.5,[38,42,55],[252,219,157],'TES Lambert albedo · dimensionless; display range 0–0.5']};
const sourcedLayers = __RANKING_LAYERS__;
const syntheticLayers = __SYNTHETIC_LAYERS__;
const syntheticRows = __SYNTHETIC_ROWS__;
const fixtureShapes = __FIXTURE_SHAPES__;
const evaExamples = __EVA_EXAMPLES__;
const cellColors = document.querySelector('#cell-colors');
const syntheticStyle = (key,id) => {
  const record = syntheticRows[id]?.[key];
  if (record == null) return [34,42,55];
  const value = record[syntheticLayers[key][1]];
  return value > 0 ? [232,154,255] : [95,65,110];
};
const sparse = new Set(['stereo','usable','imagery','crism','hirisecat','hirstereo']);
async function unpack(value) {
  const bytes = Uint8Array.from(atob(value), char => char.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}
const syntheticBounds = __SYNTHETIC_BOUNDS__;
const localRaster = syntheticBounds ? unpack('__LOCAL_PIXELS__') : null;
Promise.all([unpack('__PIXELS__'),unpack('__DATA__'),localRaster]).then(([bytes, records, local]) => {
  const ids = new Uint32Array(bytes), data = JSON.parse(new TextDecoder().decode(records));
  const localIds = local ? new Uint32Array(local) : null;
  let selected = Number(field.value.split(':')[1]), background, displayedIds = ids;
  function renderLayer() {
    const syntheticLayer = Object.hasOwn(syntheticLayers, layer.value);
    const shapeMode = syntheticLayer && Object.hasOwn(fixtureShapes, layer.value) && !cellColors.checked;
    if (cellColors) cellColors.disabled = !syntheticLayer || !Object.hasOwn(fixtureShapes, layer.value);
    const sourcedLayer = Object.hasOwn(sourcedLayers, layer.value);
    const sourcedPalette = [21,0,1,[34,42,55],[126,227,194],
      sourcedLayers[layer.value] + ' · bright cells contain imported records'];
    const [index,low,high,start,end,label] = sourcedLayer ? sourcedPalette : palettes[layer.value] ?? [];
    legend.textContent = syntheticLayer
      ? syntheticLayers[layer.value][0] + (shapeMode
        ? ' · synthetic input geometry near 0° E · dashed line is the fixture survey boundary'
        : ' · HEALPix cell summaries · bright is positive, dim is zero, grey has no fixture value')
      : label;
    const colors = data.map((row,id) => {
      if (syntheticLayer) return shapeMode ? [34,42,55] : syntheticStyle(layer.value,id);
      if (sourcedLayer) return Object.hasOwn(row[index], layer.value) ? end : start;
      if (layer.value === 'geology') {
        const code = row[9][0]?.[0];
        if (!code) return start;
        let hash = 5381;
        for (const letter of code) hash = (33 * hash + letter.charCodeAt(0)) >>> 0;
        return [65 + (hash & 127),75 + ((hash >>> 8) & 127),78 + ((hash >>> 16) & 127)];
      }
      if (row[index] === null) return [34,42,55];
      const raw = layer.value === 'counts' ? Math.log10(1 + row[index]) / 5 : ['ctxcat','hirisecat'].includes(layer.value) ? Math.log10(1 + row[index]) : row[index];
      let scale = Math.max(0,Math.min(1,(raw-low)/(high-low)));
      if (sparse.has(layer.value) && raw > 0) scale = .6 + .4 * scale;
      if (layer.value === 'thermal' && row[11] === 'archive_interpolated') scale *= .58;
      return start.map((value,j) => Math.round(value + scale*(end[j]-value)));
    });
    displayedIds = syntheticLayer ? localIds : ids;
    background = ctx.createImageData(view.width,view.height);
    for (let i=0;i<displayedIds.length;i++) {
      background.data.set(colors[displayedIds[i]],i*4);
      background.data[i*4+3] = 255;
    }
    if (shapeMode) {
      ctx.putImageData(background,0,0);
      const [west,south,east,north] = syntheticBounds;
      function draw(paths, color, fill, dash) {
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.lineWidth = 3;
        ctx.setLineDash(dash);
        for (const path of paths) {
          ctx.beginPath();
          for (const [lon,lat] of path) {
            ctx.lineTo((lon-west)*view.width/(east-west),(north-lat)*view.height/(north-south));
          }
          if (fill) ctx.fill();
          ctx.stroke();
        }
        ctx.setLineDash([]);
      }
      draw(fixtureShapes.survey,'#aeb9c9',false,[8,6]);
      draw(fixtureShapes[layer.value],'#e89aff',layer.value !== 'valley_networks',[]);
      background = ctx.getImageData(0,0,view.width,view.height);
    }
    if (sparse.has(layer.value)) {
      for (const row of data) {
        if (row[index] <= 0) continue;
        const signed = (row[0]+180)%360-180;
        for (let y = Math.max(0, Math.floor((90-row[1])*4)-1); y <= Math.min(719, Math.floor((90-row[1])*4)+1); y++) {
          for (let x = -1; x <= 1; x++) {
            const p = (Math.floor((signed+180)*4)+x+1440)%1440;
            background.data.set(end,(y*1440+p)*4);
          }
        }
      }
    }
    inspect(selected);
  }
  function inspect(id) {
    selected=id;
    const [x,y,z,n,stereo,usable,imagery,lower,names,geology,thermal,thermalStatus,crism,ctxCount,hiriseCount,dtmCount,ice01,ice15,ice5,dust,albedo,sourced] = data[id];
    field.value = 'HPX128:' + id;
    const lon = (x+180)%360-180;
    ctx.putImageData(background,0,0);
    const [west,south,east,north] = displayedIds === ids ? [-180,-90,180,90] : syntheticBounds;
    if (lon >= west && lon <= east && y >= south && y <= north) {
      ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.beginPath();
      ctx.arc((lon-west)*view.width/(east-west),(north-y)*view.height/(north-south),6,0,2*Math.PI);
      ctx.stroke();
    }
    const pct = fraction => (100*fraction).toFixed(2) + '%';
    if (Object.hasOwn(syntheticLayers, layer.value)) {
      const [title, metric] = syntheticLayers[layer.value];
      const record = syntheticRows[id]?.[layer.value];
      const unit = metric === 'magnitude_nt' ? ' nT' : metric === 'length_km' ? ' km' : '';
      const value = record == null ? 'No synthetic result for this cell.'
        : metric.includes('fraction')
          ? pct(record[metric]) + ' of cell' : record[metric].toFixed(2) + unit;
      details.textContent = [field.value + ' · Synthetic test data', title + ' · ' + value,
        record?.surveyed_fraction != null ? 'Fixture survey overlap · ' + pct(record.surveyed_fraction) : '',
        record?.valid_spectral_fraction != null ? 'Valid synthetic spectra · ' + pct(record.valid_spectral_fraction) : '',
        record?.feature_ids?.length ? 'Fixture IDs · ' + record.feature_ids.join(', ') : ''
      ].filter(Boolean).join('\\n');
      return;
    }
    details.textContent = [
      field.value + ' · ' + x.toFixed(4) + '° E, ' + y.toFixed(4) + '° latitude',
      'MOLA elevation ' + z.toLocaleString() + ' m · ' + n.toLocaleString() + ' observations in the native sample',
      'Stereo catalogue coverage ' + pct(stereo) + ' · Verified usable stereo support ' + pct(usable),
      'HiRISE imagery catalogue coverage ' + pct(imagery),
      geology.length ? 'Mapped geology at centroid · ' + geology.map(unit => unit.join(' · ')).join('; ') : '',
      thermal !== null ? 'TES nighttime thermal inertia · ' + thermal + ' J m⁻² K⁻¹ s⁻¹ᐟ² · ' + thermalStatus.replace('archive_', '') : '',
      crism ? 'CRISM targeted spectral records at centroid · ' + crism : '',
      ctxCount !== null ? 'CTX acquisition records at centroid · ' + ctxCount : '',
      hiriseCount !== null ? 'HiRISE projected-image catalogue records at centroid · ' + hiriseCount : '',
      ctxCount !== null ? 'ODE HiRISE DTM records at centroid · ' + dtmCount : '',
      [[ice01,'0–1 m'],[ice15,'1–5 m'],[ice5,'>5 m']].filter(([v])=>v!==null)
        .map(([v,depth])=>'SWIM ice consistency ' + depth + ' · ' + v.toFixed(3)).join('\\n'),
      dust !== null ? 'TES historical dust opacity · ' + dust.toFixed(3) + ' · MY25 sol 001' : '',
      albedo !== null ? 'TES Lambert albedo · ' + albedo.toFixed(3) : '',
      ...Object.entries(sourcedLayers).filter(([key]) => Object.hasOwn(sourced,key)).map(([key,title]) => {
        const [value,labels] = sourced[key];
        const amount = key === 'gazetteer_approximate_bounds' ? pct(value) + ' largest sampled bounds overlap'
          : key === 'structures' ? value + ' km' : String(value);
        return title + ' · ' + amount + ' · ' + labels;
      }),
      Object.hasOwn(sourcedLayers, layer.value) && !Object.hasOwn(sourced, layer.value)
        ? 'No imported records for the selected layer in this cell. Survey coverage is unknown.' : '',
      'Terrain documentation '   + lower.toFixed(2) + '–100 · Unclassified',
      names.length ? 'Named feature anchors ' + names.join(', ') : ''
    ].filter(Boolean).join('\\n');
  }
  layer.addEventListener('change',renderLayer);
  cellColors?.addEventListener('change',renderLayer);
  const evaCase = document.querySelector('#eva-case');
  if (evaCase) {
    const names = {
      co2_accumulation_removal_load:'CO₂ accumulation / removal load',
      remaining_eva_duration:'Remaining EVA duration',
    };
    const section = document.querySelector('#eva-fields');
    const scope = document.querySelector('#eva-scope');
    function showEva() {
      const example = evaExamples[evaCase.value];
      scope.textContent = example.cell_id + ' · ' + (example.source_scope || 'Synthetic EVA scenario')
        + ' Crew and suit values are synthetic. The example is independent of the selected map cell.';
      section.replaceChildren();
      for (const [key,item] of Object.entries(example.fields)) {
        const tr = section.insertRow();
        const name = names[key] || key.replaceAll('_',' ').replace(/^./, c => c.toUpperCase());
        const value = item.value == null ? 'Unavailable' : typeof item.value === 'number'
          ? item.value.toLocaleString(undefined,{maximumFractionDigits:5}) + ' ' + item.unit
          : item.value.replaceAll('_',' ');
        for (const text of [name,value,item.data_status.replaceAll('_',' ')]) tr.insertCell().textContent = text;
        if (item.source) {
          const link = document.createElement('a');
          link.href = item.source;
          link.textContent = 'Source';
          link.style.color = '#a8d4ff';
          tr.cells[2].append(' · ', link);
        }
        if (item.scope) tr.cells[2].title = item.scope;
      }
    }
    evaCase.addEventListener('change',showEva);
    document.querySelector('#eva-locate').addEventListener('click',() => {
      layer.value = 'elevation';
      selected = Number(evaExamples[evaCase.value].cell_id.split(':')[1]);
      renderLayer();
    });
    showEva();
  }
  view.addEventListener('click',event => {
    const rect=view.getBoundingClientRect();
    const x=Math.min(1439,Math.max(0,Math.floor((event.clientX-rect.left)*1440/rect.width)));
    const y=Math.min(719,Math.max(0,Math.floor((event.clientY-rect.top)*720/rect.height)));
    inspect(displayedIds[y*1440+x]);
  });
  document.querySelector('#search').addEventListener('submit',event => {
    event.preventDefault();
    const match=field.value.trim().match(/^(?:HPX128:)?(\\d+)$/);
    if (match && Number(match[1])<data.length) inspect(Number(match[1]));
    else details.textContent='Enter HPX128:0 through HPX128:196607.';
  });
  if (Object.keys(syntheticLayers).length) layer.value = 'deltas';
  renderLayer();
}).catch(error => { details.textContent = 'Could not open map data: ' + error.message; });
</script></html>
"""
options = ('<option value="geology">USGS mapped geologic unit</option>'
           '<option value="thermal">TES nighttime thermal inertia</option>'
           '<option value="crism">CRISM spectral catalogue at centroid</option>') if science else ""
note = ("Geology and TES are centroid samples. Thermal inertia describes surface properties and is separate from current weather."
        if science else "")
if expansion:
    options += ('<option value="ctxcat">CTX acquisition catalogue at centroid</option>'
                '<option value="hirisecat">HiRISE projected images at centroid</option>'
                '<option value="hirstereo">ODE HiRISE DTM catalogue at centroid</option>'
                '<option value="dust">TES historical atmospheric dust</option>')
    for key, value, title in (
        ("swim_0_1", "ice01", "SWIM ice consistency · 0–1 m"),
        ("swim_1_5", "ice15", "SWIM ice consistency · 1–5 m"),
        ("swim_5", "ice5", "SWIM ice consistency · deeper than 5 m"),
        ("tes_albedo", "albedo", "TES surface albedo"),
    ):
        if key in expanded_sources:
            options += f'<option value="{value}">{title}</option>'
    note += (" SWIM shows agreement among ice indicators. The TES dust snapshot is historical. "
             "Catalogue counts and raster samples describe the cell centre. "
             "See EXPANDED-LAYERS.md for source and scale details.")
if ranking_mode:
    options += "".join(f'<option value="{key}">{escape(title)}</option>'
                       for key, title in ranking_layers.items())
    note += (" Named feature bounds are approximate. Cave locations are candidates. "
             "InSight locations are estimates. Empty cells indicate unknown survey coverage.")
title = "Mars HEALPix evidence map"
banner = ""
controls = ""
if synthetic_mode:
    options += '<optgroup label="Synthetic test layers">' + "".join(
        f'<option value="{key}">{escape(title)}</option>' for key, (title, _) in synthetic_layers.items()
    ) + "</optgroup>"
    title = "Mars HEALPix synthetic science preview"
    controls = """
<details id="eva"><summary>EVA context · 28 fields</summary>
<label>Example <select id="eva-case"><option value="synthetic">Synthetic EVA</option>
<option value="jezero-sol36">Jezero sol 36</option><option value="gale-rad">Gale radiation</option>
</select></label>
<button type="button" id="eva-locate">Locate example</button>
<p id="eva-scope"></p><table><thead><tr><th>Field</th><th>Value</th><th>Data status</th></tr></thead>
<tbody id="eva-fields"></tbody></table>
</details>
<label><input type="checkbox" id="cell-colors"> Show HEALPix cell summaries</label>
"""
    banner = ('<p><strong>Synthetic test layers contain invented values.</strong> '
              'They are for software demonstration. Source catalogue layers retain their published data.</p>')
name = ("mars-cell-map-synthetic-science.html" if synthetic_mode else
        "mars-cell-map-sourced.html" if ranking_mode else "mars-cell-map-expanded.html" if expansion else
        "mars-cell-map-science.html" if science else "mars-cell-map.html")
(root / name).write_text(html.replace("__PIXELS__", pack(pixels.tobytes())).replace(
    "__DATA__", pack(json.dumps(data, separators=(",", ":")).encode())).replace(
    "__SCIENCE_OPTIONS__", options).replace("__SCIENCE_NOTE__", note).replace(
    "__RANKING_LAYERS__", json.dumps(ranking_layers if ranking_mode else {})).replace(
    "__SYNTHETIC_LAYERS__", json.dumps(synthetic_layers)).replace(
    "__SYNTHETIC_ROWS__", json.dumps(synthetic_rows, separators=(",", ":"), allow_nan=False)).replace(
    "__SYNTHETIC_BOUNDS__", json.dumps(synthetic_bounds)).replace(
    "__LOCAL_PIXELS__", pack(local_pixels.tobytes()) if synthetic_mode else "").replace(
    "__FIXTURE_SHAPES__", json.dumps(fixture_shapes)).replace(
    "__EVA_EXAMPLES__", json.dumps(eva_examples, allow_nan=False)).replace(
    "__PREVIEW_CONTROLS__", controls).replace("__EXAMPLE_ID__", example_id).replace("__MAP_TITLE__", title).replace("__SYNTHETIC_NOTE__", banner))
