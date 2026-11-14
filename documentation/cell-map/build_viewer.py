"""Build an offline HTML preview from the verified cell database."""
from base64 import b64encode
import gzip
import json
from pathlib import Path
import sqlite3

from marsdoc import Grid
import numpy as np

from workspace import build_workspace

root = build_workspace()
import os
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
width, height = 1440, 720
lon, lat = np.meshgrid((np.arange(width) + .5) / width * 360 - 180,
                       90 - (np.arange(height) + .5) / height * 180)
pixels = Grid().indices(np.stack((lon, lat), axis=-1)).astype("<u4")
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
        ice = extra.get("swim_ice_consistency", {})
        dust = extra.get("tes_dust_my25_sol001", {})
        data.append([x, y, z, n, terrain["observed_fraction"], terrain["usable_fraction"],
                     imagery["observed_fraction"], row["terrain"]["bounds"]["lower"],
                     [item["name"] for item in row["named_feature_anchors"]],
                     [[u["code"], u["name"]] for u in local.get("geologic_units", [])],
                     local.get("tes_night_thermal_inertia"), local.get("tes_night_sample_status"), len(local.get("crism_mtrdr_product_ids", [])),
                     extra.get("ctx_edr_centroid_records"), extra.get("hirise_projected_centroid_records"),
                     len(extra.get("hirise_dtm_centroid_product_ids", [])), ice.get("0_1"), ice.get("1_5"),
                     ice.get("5"), dust.get("opacity"), extra.get("tes_lambert_albedo")])

def pack(data):
    return b64encode(gzip.compress(data, mtime=0)).decode("ascii")

html = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mars HEALPix evidence map</title>
<style>
body{background:#161a21;color:#edf0f4;margin:0 auto;max-width:1180px;padding:1.5rem;font:16px system-ui}
p{color:#b5bdc8;line-height:1.5}select,input,button{font:inherit;padding:.35rem;margin:.3rem 0}
canvas{display:block;width:100%;height:auto;background:#252d39;cursor:crosshair;margin-top:1rem}
#details{white-space:pre-wrap;line-height:1.6;padding:1rem;background:#222935}
</style>
<h1>Mars HEALPix evidence map</h1>
<p>196,608 cells · Nside 128 · Return Window · East-positive Mars coordinates</p>
<label>Layer <select id="layer">
<option value="elevation">MOLA elevation</option><option value="counts">MOLA observation count</option>
<option value="stereo">Stereo terrain catalogue coverage</option><option value="usable">Verified usable stereo terrain</option>
<option value="imagery">HiRISE imagery · local catalogue search</option>
__SCIENCE_OPTIONS__
</select></label>
<form id="search"><label>Cell ID <input id="cell" value="HPX128:96848"></label> <button>Inspect</button></form>
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
const sparse = new Set(['stereo','usable','imagery','crism','hirisecat','hirstereo']);
async function unpack(value) {
  const bytes = Uint8Array.from(atob(value), char => char.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}
Promise.all([unpack('__PIXELS__'),unpack('__DATA__')]).then(([bytes, records]) => {
  const ids = new Uint32Array(bytes), data = JSON.parse(new TextDecoder().decode(records));
  let selected = 96848, background;
  function renderLayer() {
    const [index,low,high,start,end,label] = palettes[layer.value];
    legend.textContent = label;
    const colors = data.map(row => {
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
    background = ctx.createImageData(view.width,view.height);
    for (let i=0;i<ids.length;i++) {
      background.data.set(colors[ids[i]],i*4);
      background.data[i*4+3] = 255;
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
    const [x,y,z,n,stereo,usable,imagery,lower,names,geology,thermal,thermalStatus,crism,ctxCount,hiriseCount,dtmCount,ice01,ice15,ice5,dust,albedo] = data[id];
    field.value = 'HPX128:' + id;
    const lon = (x+180)%360-180;
    ctx.putImageData(background,0,0);
    ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc((lon+180)*4,(90-y)*4,6,0,2*Math.PI); ctx.stroke();
    const pct = fraction => (100*fraction).toFixed(2) + '%';
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
      'Terrain documentation '  + lower.toFixed(2) + '–100 · Unclassified',
      names.length ? 'Named feature anchors ' + names.join(', ') : ''
    ].filter(Boolean).join('\\n');
  }
  layer.addEventListener('change',renderLayer);
  view.addEventListener('click',event => {
    const rect=view.getBoundingClientRect();
    const x=Math.min(1439,Math.max(0,Math.floor((event.clientX-rect.left)*1440/rect.width)));
    const y=Math.min(719,Math.max(0,Math.floor((event.clientY-rect.top)*720/rect.height)));
    inspect(ids[y*1440+x]);
  });
  document.querySelector('#search').addEventListener('submit',event => {
    event.preventDefault();
    const match=field.value.trim().match(/^(?:HPX128:)?(\\d+)$/);
    if (match && Number(match[1])<data.length) inspect(Number(match[1]));
    else details.textContent='Enter HPX128:0 through HPX128:196607.';
  });
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
name = ("mars-cell-map-expanded.html" if expansion else
        "mars-cell-map-science.html" if science else "mars-cell-map.html")
(root / name).write_text(html.replace("__PIXELS__", pack(pixels.tobytes())).replace(
    "__DATA__", pack(json.dumps(data, separators=(",", ":")).encode())).replace(
    "__SCIENCE_OPTIONS__", options).replace("__SCIENCE_NOTE__", note))
