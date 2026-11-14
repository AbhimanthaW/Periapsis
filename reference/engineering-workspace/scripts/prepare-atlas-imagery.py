#!/usr/bin/env python3
"""Prepare small offline images from NASA Mars Trek's advertised WMTS tiles."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
import hashlib
import json
import math
import xml.etree.ElementTree as ET

from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[1]
ROOT = WORKSPACE / 'public' / 'atlas'
MISSION_ASSETS = WORKSPACE.parents[1] / 'web' / 'src' / 'mission' / 'assets'
TREK = 'https://trek.nasa.gov/tiles/Mars/EQ'
WORLD = [-180, -90, 180, 90]
PRODUCTS = [
    ('viking','Mars_Viking_MDIM21_ClrMosaic_global_232m', 2, WORLD, 'Viking MDIM 2.1 colorized mosaic',
     'https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m',232,'NASA Ames / Viking / USGS', 'Viking-era imagery; MDIM 2.1 color product cataloged in 2009.', 'Display mosaic. Colorization and illumination are part of the product.'),
    ('mola','Mars_MGS_MOLA_ClrShade_merge_global_463m',2,WORLD,'MOLA shaded relief',
     'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_global_color_shaded_relief_463m',463,'NASA MGS / MOLA Science Team / USGS','MGS-era altimetry; relief product cataloged in 2003.','Rendered topographic context. The color and lighting represent the relief product, and no elevation values are read from it.'),
    ('jezero','JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',11,[77.18,18.2,77.75,18.62],'Jezero CTX detail',
     'https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',6,'NASA / JPL-Caltech / MSSS / USGS','Mars 2020 TRN archive mosaic, cataloged in 2020.','Bounded optical display subset. No elevation, slope, validated pack, or route readiness implied.'),
]

def read(url):
    for attempt in range(3):
        try:
            with urlopen(url,timeout=25) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise

def prepare(record):
    key,layer,level,requested,title,source,native,credit,era,limits = record
    service = f'{TREK}/{layer}/1.0.0/WMTSCapabilities.xml'
    capabilities = read(service)
    xml = ET.fromstring(capabilities)
    layer_info = xml.find('.//{*}Layer')
    resource = layer_info.find('{*}ResourceURL').attrib['template']
    matrix_id = layer_info.findtext('{*}TileMatrixSetLink/{*}TileMatrixSet')
    matrix_set = next(m for m in xml.findall('.//{*}Contents/{*}TileMatrixSet') if m.findtext('{*}Identifier') == matrix_id)
    matrix = next(m for m in matrix_set.findall('{*}TileMatrix') if m.findtext('{*}Identifier') == str(level))
    nx,ny = (int(float(matrix.findtext('{*}'+tag))) for tag in ('MatrixWidth','MatrixHeight'))
    tw,th = (int(matrix.findtext('{*}'+tag)) for tag in ('TileWidth','TileHeight'))
    origin = list(map(float,matrix.findtext('{*}TopLeftCorner').split()))
    assert origin == [-180,90] and nx == ny * 2 and tw == th == 256
    assert matrix_set.findtext('{*}SupportedCRS') == 'urn:ogc:def:crs:EPSG::104905'
    size = 360 / nx
    west,south,east,north = requested
    x0,x1 = math.floor((west+180)/size), math.ceil((east+180)/size)
    y0,y1 = math.floor((90-north)/size), math.ceil((90-south)/size)
    extent = [x0*size-180,90-y1*size,x1*size-180,90-y0*size]
    image = Image.new('RGBA' if key=='jezero' else 'RGB',((x1-x0)*tw,(y1-y0)*th))
    def tile(pair):
        x,y = pair
        url = resource.format(Style='default',TileMatrixSet=matrix_id,TileMatrix=level,TileRow=y,TileCol=x)
        with Image.open(BytesIO(read(url))) as asset:
            assert asset.size == (tw,th)
            return x,y,asset.convert(image.mode)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for x,y,asset in pool.map(tile,[(x,y) for y in range(y0,y1) for x in range(x0,x1)]):
            image.paste(asset,((x-x0)*tw,(y-y0)*th))
    if key == 'jezero':
        assert image.getbbox(), 'regional imagery must contain data'
        image.save(MISSION_ASSETS / 'jezero.webp','WEBP',quality=88,method=6)
    else:
        for zoom in range(level+1):
            scaled = image.resize((tw*2**(zoom+1),th*2**zoom),Image.Resampling.LANCZOS)
            for y in range(2**zoom):
                for x in range(2**(zoom+1)):
                    output = ROOT / key / str(zoom) / str(x) / f'{y}.webp'
                    output.parent.mkdir(parents=True,exist_ok=True)
                    scaled.crop((tw*x,th*y,tw*(x+1),th*(y+1))).save(output,'WEBP',quality=87,method=6)
    return dict(id=key,title=title,source=source,service=service,layer=layer,matrix=matrix_id,level=level,extent=extent,
                width=image.width,height=image.height,sampleDegrees=size/tw,nativeMeters=native,credit=credit,era=era,limits=limits,
                crs='Mars geographic, planetocentric latitude, east-positive longitude',capabilitiesSha256=hashlib.sha256(capabilities).hexdigest())

if __name__ == '__main__':
    ROOT.mkdir(exist_ok=True,parents=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assets = list(pool.map(prepare,PRODUCTS))
    global_assets = [asset for asset in assets if asset['id'] != 'jezero']
    jezero = next(asset for asset in assets if asset['id'] == 'jezero')
    (WORKSPACE / 'src' / 'atlas' / 'imagery.json').write_text(json.dumps(global_assets, indent=2) + '\n')
    (MISSION_ASSETS / 'jezero.json').write_text(json.dumps(jezero, indent=2) + '\n')
    print('Prepared',[(asset['id'],asset['width'],asset['height']) for asset in assets])
