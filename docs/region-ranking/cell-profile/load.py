"""Flatten the enriched NDJSON into numpy arrays + categorical tables (cache)."""
import gzip, json, sys, pickle, collections
import numpy as np
src, out = sys.argv[1], sys.argv[2]
N=196608
f8=lambda: np.full(N, np.nan)
A=dict(lon=f8(),lat=f8(),elev=f8(),mola_n=f8(),ti=f8(),albedo=f8(),ctx=f8(),hr4=f8(),hr11=f8(),hproj=f8(),
       swim01=f8(),swim15=f8(),swim5=f8(),dust=f8(),dust_unc=f8(),dust_rel=f8(),dust_n=f8(),
       crism_n=f8(),hdtm_n=f8(),n_units=f8(),n_anchor=f8(),t_lo=f8(),t_hi=f8(),s_lo=f8(),s_hi=f8())
unit=[None]*N; units_multi={}; ti_status=[None]*N; anchors={}; keysets=collections.Counter()
mod_status=collections.Counter(); tiers=collections.Counter(); anchor_keys=collections.Counter()
unitinfo={}
for line in gzip.open(src,'rt'):
    r=json.loads(line); i=r['nested_index']
    assert r['cell_id']==f'HPX128:{i}'
    keysets[tuple(sorted(r))]+=1
    A['lon'][i]=r['longitude_deg_east']; A['lat'][i]=r['latitude_deg_planetocentric']
    for k,src_k in (('elev','mola_elevation_m'),('mola_n','mola_observation_count')):
        if r.get(src_k) is not None: A[k][i]=r[src_k]
    A['t_lo'][i]=r['terrain']['bounds']['lower']; A['t_hi'][i]=r['terrain']['bounds']['upper']
    A['s_lo'][i]=r['science_environment']['bounds']['lower']; A['s_hi'][i]=r['science_environment']['bounds']['upper']
    tiers[('terrain',r['terrain']['tier'],r['terrain']['reason'])]+=1
    tiers[('sci',r['science_environment']['tier'],r['science_environment']['reason'])]+=1
    for m,v in r['modalities'].items(): mod_status[(m,v['status'],v['observed_fraction']>0,v['usable_fraction']>0)]+=1
    s=r.get('science_at_centroid') or {}
    gu=s.get('geologic_units') or []
    A['n_units'][i]=len(gu)
    if gu:
        unit[i]=gu[0]['code']
        for g in gu: unitinfo[g['code']]=(g['name'],g['group'])
        if len(gu)>1: units_multi[i]=[g['code'] for g in gu]
    A['crism_n'][i]=len(s.get('crism_mtrdr_product_ids') or [])
    if s.get('tes_night_thermal_inertia') is not None: A['ti'][i]=s['tes_night_thermal_inertia']
    ti_status[i]=s.get('tes_night_sample_status')
    c=r.get('additional_context_at_centroid') or {}
    for k,ck in (('ctx','ctx_edr_centroid_records'),('hr4','hirise_rdr4_centroid_records'),('hr11','hirise_rdrv11_centroid_records'),('hproj','hirise_projected_centroid_records'),('albedo','tes_lambert_albedo')):
        if c.get(ck) is not None: A[k][i]=c[ck]
    A['hdtm_n'][i]=len(c.get('hirise_dtm_centroid_product_ids') or [])
    sw=c.get('swim_ice_consistency') or {}
    for k,ck in (('swim01','0_1'),('swim15','1_5'),('swim5','5')):
        if sw.get(ck) is not None: A[k][i]=sw[ck]
    d=c.get('tes_dust_my25_sol001') or {}
    for k,ck in (('dust','opacity'),('dust_unc','uncertainty'),('dust_rel','reliability'),('dust_n','retrieval_count')):
        if d.get(ck) is not None: A[k][i]=d[ck]
    na=r.get('named_feature_anchors') or []
    A['n_anchor'][i]=len(na)
    if na:
        anchors[i]=na
        for a in na: anchor_keys[tuple(sorted(a))]+=1
pickle.dump(dict(A=A,unit=unit,units_multi=units_multi,ti_status=ti_status,anchors=anchors,unitinfo=unitinfo),open(out,'wb'))
print('keysets',keysets)
print('tiers',tiers)
for k,v in sorted(mod_status.items()): print('mod',k,v)
print('anchor_keys',anchor_keys); print(list(anchors.items())[:3])
print('ti_status',collections.Counter(ti_status))
