#!/usr/bin/env python3
"""Regenerate the atlas registry from the supplied survey and official Mars KMZ."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REGION = re.compile(r'^## \*\*Region (\d+) — (.*)\*\*$|^Next region: (Mawrth Vallis) \(Region (47)\\\)',re.M)
LINK = re.compile(r'\[([^\]\n]+)\]\((https?://(?:\\[()]|[^)\s])+)\)')
ALIASES = {'Jezero Crater':'Jezero','Gale Crater':'Gale','Gusev Crater':'Gusev','Holden Crater':'Holden',
           'Elysium Mons and the Elysium volcanic rise':'Elysium Mons','Medusae Fossae Formation (MFF)':'Medusae Fossae'}
DISPLAY = {'Elysium Mons and the Elysium volcanic rise':'Elysium Mons and volcanic rise','Medusae Fossae Formation (MFF)':'Medusae Fossae Formation'}
RELATIONS = [('43','14','Northwestern basin margin'),('38','07','Elysium geological context'),
             ('51','33','Related canyon system'),('52','33','Related canyon system'),('50','33','Western canyon system'),
             ('41','45','Valley outlet and crater basin')]
LEVELS = {'very low':1,'low':2,'moderate':3,'high':4,'very high':5}
LEVEL_RE = r'very low|very high|moderate|low|high'
TERRAIN_FACTOR = re.compile(r'slope|roughness|traction|sinkage|dune|crater|scarp|frost|bedrock|surface|fracture|debris|dust|terrain',re.I)

def plain(s):
    s = LINK.sub(r'\1',s)
    return re.sub(r'[\\`*]','',s).strip()

def row_entries(lines):
    for line in lines:
        if line.startswith('|'):
            cells = [plain(cell) for cell in line.strip().strip('|').split('|')]
            if len(cells)>1 and not re.match(r'^[- :]+$',cells[0]):
                yield cells

def normalized(s):
    return re.sub(r'\s+',' ',s.strip().lower())

def rating(text):
    start = re.match(r'^('+LEVEL_RE+r')\b',text,re.I)
    values = {normalized(v) for v in re.findall(r'\b('+LEVEL_RE+r')\b',text,re.I)}
    mixed = (len(values)>1 or bool(re.search(r'\bextreme\b',text,re.I))) and bool(re.search(r'\bto\b|[–—;/-]|\bbut\b',text,re.I))
    return LEVELS[normalized(start[0])] if start and not mixed else None

def assess(rows,keys,body):
    match = next((cells for cells in rows if normalized(cells[0]) in keys),None)
    text = match[1] if match else ''
    if not text or not re.search(r'\b('+LEVEL_RE+r')\b',text,re.I):
        lines=[plain(line) for line in body.splitlines() if line.strip()]
        explicit = next((lines[i+1] for i,line in enumerate(lines[:-1])
                         if normalized(line) in keys and re.match(r'^('+LEVEL_RE+r')\b',lines[i+1],re.I)),None)
        if explicit:
            text = explicit
    return {'rating':rating(text),'original':text,'kind':'Provisional survey assessment','note':match[2] if match and len(match)>2 else ''}

def excerpts(text, n=3):
    body = '\n'.join(line for line in text.splitlines() if not LINK.fullmatch(line.strip().removeprefix('!')))
    blocks = []
    for para in re.split(r'\n\s*\n',body):
        lines = [line for line in para.splitlines() if not line.strip().startswith(('#','|','>','*','-'))]
        content = plain(' '.join(lines))
        if len(content)>=95 and not content.lower().startswith(('next region','the next step','for our project','for the website','we will evaluate')):
            blocks.append(content)
    return list(dict.fromkeys(blocks))[:n]

def keys_for(title):
    name = normalized(plain(title))
    if re.search(r'classification|colour scale|comparison|regional record|research metadata|references|sources',name):
        return None
    if re.search(r'document|dataset|data quality|data availab|observation coverage',name):
        return 'data'
    if re.search(r'scientific interest|scientific (?:value|significance|opportunit)|science opportunit|points of interest|target[s]? and',name):
        return 'science'
    if re.search(r'operational|traversal|mobility|hazard|avoidance',name):
        return 'operations'
    if re.search(r'geology|geologic|subregion|terrain|major landform',name):
        return 'terrain'
    return None

def sources(body):
    found={}
    for match in LINK.finditer(body):
        original=match[2].replace('\\','')
        parts=urlsplit(original)
        hostname=parts.hostname or ''
        url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode([(k,v) for k,v in parse_qsl(parts.query) if not k.startswith('utm_')]),parts.fragment))
        kind='Media proxy' if hostname=='images.openai.com' else 'Agency or archive host' if hostname.endswith(('.gov','esa.int','dlr.de','nmsu.edu','wustl.edu','uahirise.org','lpl.arizona.edu')) else 'Survey citation'
        found.setdefault(url,{'title':plain(match[1]),'url':url,'kind':kind})
    return list(found.values())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('research',type=Path)
    parser.add_argument('gazetteer',type=Path)
    args=parser.parse_args()
    original=args.research.read_bytes()
    text=args.research.read_text(encoding='utf-8')
    matches=list(REGION.finditer(text))
    assert sorted(int(m[1] or m[4]) for m in matches)==list(range(1,57)), 'Require every stable ID exactly once'
    with ZipFile(args.gazetteer) as archive:
        names=ET.fromstring(archive.read('MARS_nomenclature_center_pts.kml'))
        stamp=archive.getinfo('MARS_nomenclature_center_pts.kml').date_time[:3]
    approved={}
    for place in names.findall('.//{*}Placemark'):
        fields={e.attrib['name']:e.text for e in place.findall('.//{*}SimpleData')}
        if fields.get('approval')=='Adopted by IAU':
            approved[place.findtext('{*}name')]=(place,fields)
    registry=[]
    for i,m in enumerate(matches):
        rid,raw=m[1] or m[4],m[2] or m[3]
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        first,last=text.count('\n',0,m.start())+1,text.count('\n',0,end)+(0 if i+1<len(matches) else 1)
        body=text[m.end():end]
        headings=list(re.finditer(r'^(#{2,3})\s+(.*)$',body,re.M))
        sections={key:[] for key in ('terrain','science','data','operations')}
        tables={key:[] for key in sections}
        fields={}
        for j,h in enumerate(headings):
            next_heading=headings[j+1].start() if j+1<len(headings) else len(body)
            section=body[h.end():next_heading]
            title=plain(h[2])
            if re.search(r'regional (?:information )?record|record for the future react website|information to retain for the react website',title,re.I):
                fields.update((normalized(c[0]),c[1]) for c in row_entries(section.splitlines()) if normalized(c[0])!='field')
            key=keys_for(title)
            if not key and h[1]=='###':
                parent=next((x for x in reversed(headings[:j]) if x[1]=='##'),None)
                key=keys_for(parent[2]) if parent else None
            if key:
                sections[key].extend(excerpts(section))
                section_rows=list(row_entries(section.splitlines()))
                if len(section_rows)>1: tables[key].append({'title':title,'head':section_rows[0],'rows':section_rows[1:]})
        rows=list(row_entries(body.splitlines()))
        def field(*keys):
            return next((fields[key] for key in keys if key in fields),'')
        def first_factor(pattern):
            return next((' — '.join(c[:3]) for c in rows if re.search(pattern,c[0],re.I) and len(c)>=3),'')
        assessments={
            'traversal':assess(rows,{'traversal cost','traversal difficulty','preliminary traversal cost','regional traversal cost','overall traversal cost'},body),
            'science':assess(rows,{'scientific interest','scientific value','science interest','scientific / mission interest'},body),
        }
        # Accept only explicit classification-table rows for ordinal colors. A field
        # with prose, mixed levels or missing evidence is preserved without a bin.
        refname=ALIASES.get(raw,raw.replace('’',"'"))
        place,attrs=approved[refname]
        x,y=map(float,place.findtext('.//{*}coordinates').split(',')[:2])
        assert abs((float(attrs['center_lon'])-x+180)%360-180)<1e-6
        assert abs(float(attrs['center_lat'])-y)<1e-6
        geometry={'center':[round(x,6),round(y,6)],'status':'Representative anchor' if rid in ('36','37') else 'Gazetteer center',
                  'gazetteerName':refname,'gazetteerUrl':attrs['link'].replace('http://','https://'),
                  'note':('The named mountain anchors the broader volcanic rise.' if rid=='36' else
                          'The named fossae anchor the broader, discontinuous geological formation.' if rid=='37' else
                          'Approved feature center. The point does not define the research area boundary.')}
        overview=excerpts(body[:headings[0].start()] if headings else body)
        if not overview: overview=excerpts(body,2)
        location=next((plain(l) for l in body.splitlines() if re.match(r'^\*{0,2}Location\s*:',l,re.I)),'')
        for table in tables['operations']:
            if normalized(table['head'][0])!='cost factor':
                continue
            physical_rows=[row for row in table['rows'] if TERRAIN_FACTOR.search(row[0])]
            if physical_rows:
                tables['terrain'].append({'title':'Physical terrain factors from the traversal survey','head':table['head'],'rows':physical_rows})
            break
        registry.append({
            'id':rid,'name':DISPLAY.get(raw,raw),'sourceName':raw,'featureType':attrs['type'].split(',')[0],
            'geography':geometry,'location':location,'startLine':first,'endLine':last,'overview':overview,
            'assessments':assessments,'sections':{k:list(dict.fromkeys(v))[:8] for k,v in sections.items()},
            'tables':{k:v[:4] for k,v in tables.items()},'fields':fields,'sources':sources(body),
            'concern':field('main operational concern','main operational concerns','primary operational concerns','primary operational concern','main traversal concern','major operational concern','major cost factors','major potential hazard') or first_factor(r'^(?:terrain slope|slope)$'),
            'opportunity':field('primary scientific opportunity','main scientific opportunity','principal scientific opportunity','scientific opportunity','major scientific opportunity','primary scientific value') or (sections['science'][0] if sections['science'] else ''),
            'documentationNote':field('documentation','data documentation','data availability','documentation status'),
            'uncertainty':field('key uncertainty','primary uncertainty','main uncertainty','operational uncertainty','known limitation') or next((c[1] for c in rows if normalized(c[0]) in {'operational uncertainty','key uncertainty','primary uncertainty'}),''),
            'related':[{'id':b if rid==a else a,'relation':tag} for a,b,tag in RELATIONS if rid in (a,b)],
        })
    archive=ROOT/'public/atlas/MARS_REGIONAL_RESEARCH.md'
    archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(original)
    manifest={'researchSha256':hashlib.sha256(original).hexdigest(),'gazetteerDate':'%04d-%02d-%02d'%stamp,
              'gazetteerSource':'https://planetarynames.wr.usgs.gov/GIS_Downloads',
              'gazetteerArchive':'https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.kmz',
              'gazetteerSha256':hashlib.sha256(args.gazetteer.read_bytes()).hexdigest(),'regions':registry}
    (ROOT/'src/atlas/regions.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
    for key in ('traversal','science'):
        print(key,Counter(str(r['assessments'][key]['rating']) for r in registry))
    print('Regions',len(registry),'links',sum(len(r['sources']) for r in registry))

if __name__=='__main__':
    main()
