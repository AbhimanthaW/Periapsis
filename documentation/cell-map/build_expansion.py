"""Build per-cell context from independently identified planetary archives."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gzip
from hashlib import file_digest
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZipFile

import numpy as np
from pyproj import CRS, Transformer
import rasterio
from shapely import STRtree, points
from shapely.geometry import shape
import shapefile

from workspace import build_workspace

ROOT = build_workspace()
SOURCES = ROOT / "expansion-sources"
DESTINATION = ROOT / "expansion"
ODE = "https://ode.rsl.wustl.edu/mars/datafile/derived_products/coverageshapefiles/mars/mro/"
SWIM = "https://swim.psi.edu/output/SWIM4MIM/Global/Composite/"
DUST = "https://atmos.nmsu.edu/PDS/data/PDS4/mgs_tes_atmos_dust-ice/data_IR_Dust_Optical_Depth_Maps/MY25/month_01/"
ALBEDO = ("https://ms-mars.mars.asu.edu/alb32?SERVICE=WMS&REQUEST=GetMap&FORMAT=image/vicar"
          "&WIDTH=1440&HEIGHT=720&SRS=JMARS:4&BBOX=0,-90,360,90&STYLES=&VERSION=1.1.1"
          "&LAYERS=TES_Lambert_Albedo_numeric")


def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def source_receipts(paths):
    return {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in paths}


def mars_reference(crs, radius):
    assert crs.ellipsoid.semi_major_metre == radius
    assert crs.ellipsoid.semi_minor_metre == radius
    assert crs.prime_meridian.longitude == 0


def footprint_catalogue(path, url, target_product, query_points, *, keep_ids=False):
    geometries, ids = [], []
    quarantine = Counter()
    with TemporaryDirectory() as temporary, ZipFile(path) as archive:
        base, = [name.removesuffix(".shp") for name in archive.namelist() if name.endswith(".shp")]
        mars_reference(CRS.from_wkt(archive.read(base + ".prj").decode()), 3396190)
        description = archive.read(base + ".shp.xml").decode()
        assert "All latitudes are planetocentric" in description
        assert "positive east, -180 to 180" in description
        for ext in (".shp", ".shx", ".dbf"):
            # Read only known members. Streaming the DBF keeps peak memory bounded.
            with archive.open(base + ext) as source, (Path(temporary) / ("catalogue" + ext)).open("wb") as out:
                shutil.copyfileobj(source, out)
        with shapefile.Reader(str(Path(temporary) / "catalogue")) as catalogue:
            total = len(catalogue)
            seen = set()
            for item in catalogue.iterShapeRecords(fields=["Target", "ProdType", "ProductId", "ProductLid", "ProdVer"]):
                props = item.record.as_dict()
                assert props["Target"].strip().lower() == "mars"
                assert props["ProdType"].strip().lower() == target_product
                key = (props["ProductLid"].strip() or props["ProductId"].strip()) + "::" + props["ProdVer"].strip()
                if key in seen:
                    quarantine["duplicate_product_key"] += 1
                    continue
                if not item.shape.points:
                    quarantine["empty"] += 1
                    continue
                geom = shape(item.shape.__geo_interface__)
                if geom.is_empty or not geom.is_valid:
                    quarantine["invalid_geometry"] += 1
                    continue
                components = getattr(geom, "geoms", (geom,))
                if any(part.bounds[2] - part.bounds[0] > 180 or
                       not (-180.001 <= part.bounds[0] <= part.bounds[2] <= 180.001 and
                            -90.001 <= part.bounds[1] <= part.bounds[3] <= 90.001)
                       for part in components):
                    quarantine["ambiguous_seam_or_bounds"] += 1
                    continue
                seen.add(key)
                geometries.append(geom)
                ids.append(key)
    counts = np.zeros(len(query_points), dtype=np.int32)
    products = {} if keep_ids else None
    tree = STRtree(geometries)
    for start in range(0, len(query_points), 8192):
        cell, item = tree.query(query_points[start:start + 8192], predicate="covered_by")
        np.add.at(counts, cell + start, 1)
        if products is not None:
            for i, j in zip(cell, item, strict=True):
                products.setdefault(int(i) + start, []).append(ids[j])
    receipt = dict(url=url, files=source_receipts([path]), records=total, imported=len(ids),
                   excluded=dict(quarantine), cells_with_data=int(np.count_nonzero(counts)),
                   method="Centroid containment in published geographic catalogue polygons. Counts are product keys, not unique acquisitions.")
    assert total == len(ids) + sum(quarantine.values())
    print(path.name, total, len(ids), receipt["cells_with_data"], flush=True)
    return counts, products, receipt


def ice(depth, lon, lat):
    path = SOURCES / f"swim-{depth}.tif"
    with rasterio.open(path) as dataset:
        assert dataset.shape == (2400, 7200) and dataset.count == 1
        assert dataset.nodata == -30 and dataset.scales == (1,) and dataset.offsets == (0,)
        crs = CRS.from_wkt(dataset.crs.to_wkt())
        mars_reference(crs, 3396190)
        assert crs.name == "Mars2000_equicylindrical_clon0"
        # Published GeoTIFF WKT specifies a zero-centred grid. Use the TIFF
        # affine rather than the generic 0–360 convention in the web page.
        x, y = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform(lon, lat, errcheck=True)
        col, row = ~dataset.transform * (x, y)
        rows, cols = np.floor(row).astype(int), np.floor(col).astype(int)
        inside = (rows >= 0) & (rows < dataset.height) & (cols >= 0) & (cols < dataset.width)
        grid = dataset.read(1, masked=True)
        assert -1 <= grid.min() <= grid.max() <= 1
        samples = np.full(len(lon), np.nan)
        samples[inside] = grid[rows[inside], cols[inside]].filled(np.nan)
    assert not np.any(np.isfinite(samples[np.abs(lat) >= 60.05]))
    return samples, dict(url=SWIM + f"SWIM4MIM_Ci_{depth}.tif", files=source_receipts([path]),
                         cells_with_data=int(np.isfinite(samples).sum()),
                         method="SWIM depth-specific composite consistency index at centroid. Range −1 to +1. Outside coverage is null.")


def dust(lon, lat):
    dat, label, ancillary = [SOURCES / ("tes-dust." + ext) for ext in ("dat", "xml", "txt")]
    xml = ElementTree.parse(label)
    names = [item.text for item in xml.findall(".//{*}Field_Character/{*}name")]
    assert names[:10] == [
        "East longitude", "Latitude", "Number of averaged CDOD retrievals", "Time window",
        "Reliability value", "CDOD at 9.3 micron and 610 Pa", "Uncertainty in CDOD at 9.3 micron and 610 Pa",
        "RMSD of CDOD at 9.3 micron and 610 Pa", "CDOD at 9.3 micron", "Uncertainty in CDOD at 9.3 micron",
    ]
    grid = np.loadtxt(dat, skiprows=1).reshape(60, 60, 10)
    np.testing.assert_array_equal(grid[0, :, 0], np.arange(-180, 180, 6))
    np.testing.assert_array_equal(grid[:, 0, 1], np.arange(88.5, -90, -3))
    row = np.floor((90 - lat) / 3).astype(int)
    col = np.floor((lon + 183) / 6).astype(int) % 60
    samples = grid[row, col]
    data = {k: np.where(samples[:, 8] >= 0, samples[:, i], np.nan)
            for k, i in (("opacity", 8), ("uncertainty", 9), ("reliability", 4), ("retrieval_count", 2))}
    for k, values in data.items():
        data[k] = np.where(values >= 0, values, np.nan)
    times = ancillary.read_text().splitlines()[1].split()
    assert times[2:] == ["25", "1", "359.93"]
    return data, dict(url=DUST + "TES_CDODMAP_IR_MY25_SOY001.xml",
                      files=source_receipts([dat, label, ancillary]),
                      cells_with_data=int(np.isfinite(data["opacity"]).sum()),
                      mars_year=25, sol_of_year=1, solar_longitude_deg=359.93,
                      retrieval_utc_start=times[0], retrieval_utc_end=times[1],
                      method="Historical MGS TES reconstructed IR column dust optical depth at 9.3 µm, sampled at nearest 6° × 3° bin.")


def albedo(lon, lat):
    path = SOURCES / "tes-albedo-4ppd.vic"
    with path.open("rb") as file:
        label = file.read(5760).decode("ascii")
    for field in ("LBLSIZE=5760", "REALFMT='RIEEE'", "FORMAT='REAL'", "ORG='BSQ'", "NL=720", "NS=1440"):
        assert field in label
    assert path.stat().st_size == 5760 * 721
    grid = np.memmap(path, mode="r", dtype="<f4", offset=5760, shape=(720, 1440))
    rows = np.floor((90 - lat) * 4).astype(int)
    cols = np.floor(np.remainder(lon, 360) * 4).astype(int)
    values = np.asarray(grid[rows, cols])
    values = np.where(np.isfinite(values) & (values > 0) & (values <= 1), values, np.nan)
    return values, dict(url=ALBEDO, files=source_receipts([path]), cells_with_data=int(np.isfinite(values).sum()),
                        method="MGS TES Lambert albedo, ASU/JMARS WMS numerical export at 4 ppd. Dimensionless reflectivity.")


def number(value, decimals=6):
    return round(float(value), decimals) if math.isfinite(value) else None


def main():
    with sqlite3.connect(f"file:{ROOT / 'map/cells.sqlite'}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT nested_index, longitude_deg_east, latitude_deg_planetocentric "
                          "FROM cells ORDER BY nested_index").fetchall()
    assert len(rows) == 196608 and all(i == row[0] for i, row in enumerate(rows))
    angles = np.asarray(rows)[:, 1:]
    lon, lat = (angles[:, 0] + 180) % 360 - 180, angles[:, 1]
    query = points(lon, lat)
    ctx, _, ctx_meta = footprint_catalogue(SOURCES / "mars_mro_ctx_edr_c0a.zip",
        ODE + "ctx/edr/mars_mro_ctx_edr_c0a.zip", "edr", query)
    hirise, _, hirise_meta = footprint_catalogue(SOURCES / "hirise-rdr4.zip",
        ODE + "hirise/rdr4/mars_mro_hirise_rdr4_c0a.zip", "rdr4", query)
    legacy_hirise, _, legacy_meta = footprint_catalogue(SOURCES / "hirise-rdrv11.zip",
        ODE + "hirise/rdrv11/mars_mro_hirise_rdrv11_c0a.zip", "rdrv11", query)
    dtm, dtm_ids, dtm_meta = footprint_catalogue(SOURCES / "hirise-dtm.zip",
        ODE + "hirise/dtm/mars_mro_hirise_dtm_c0a.zip", "dtm", query, keep_ids=True)
    dust_values, dust_meta = dust(lon, lat)
    ice_values, meta = {}, {}
    for depth in ("0_1", "1_5", "5"):
        try:
            ice_values[depth], meta["swim_" + depth] = ice(depth, lon, lat)
        except (OSError, rasterio.errors.RasterioError) as error:
            print(f"SWIM {depth} incomplete: {error}", flush=True)
    surface = None
    try:
        surface, meta["tes_albedo"] = albedo(lon, lat)
    except (OSError, AssertionError) as error:
        print(f"TES albedo unavailable: {error}", flush=True)
    meta.update(ctx=ctx_meta, hirise_rdr4=hirise_meta, hirise_rdrv11=legacy_meta, hirise_dtm=dtm_meta, tes_dust=dust_meta)
    DESTINATION.mkdir(exist_ok=True)
    final = DESTINATION / "cell-expansion.ndjson.gz"
    pending = final.with_suffix(".part")
    with pending.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
        for i in range(len(lon)):
            record = {
                "cell_id": f"HPX128:{i}",
                "ctx_edr_centroid_records": int(ctx[i]),
                "hirise_rdr4_centroid_records": int(hirise[i]),
                "hirise_rdrv11_centroid_records": int(legacy_hirise[i]),
                "hirise_projected_centroid_records": int(hirise[i] + legacy_hirise[i]),
                "hirise_dtm_centroid_product_ids": sorted(dtm_ids.get(i, ())),
                "swim_ice_consistency": {depth: number(values[i]) for depth, values in ice_values.items()},
                "tes_dust_my25_sol001": {key: number(values[i]) for key, values in dust_values.items()},
            }
            if surface is not None:
                record["tes_lambert_albedo"] = number(surface[i])
            stream.write((json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n").encode())
    pending.replace(final)
    manifest = {"cell_count": len(lon), "sources": meta,
                "output_sha256": digest(final),
                "hirise_combined_cells": int(np.count_nonzero(hirise + legacy_hirise)),
                "hirise_count_scope": "Sum of PDS3 and PDS4 catalogue counts. An acquisition may be represented in both.",
                "sampling": "HEALPix cell centroid, not cell area or model eligibility"}
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print({k: item["cells_with_data"] for k, item in meta.items()}, flush=True)


if __name__ == "__main__":
    main()
