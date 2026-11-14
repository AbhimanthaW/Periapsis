import pickle, sys, collections
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
D=pickle.load(open(sys.argv[1],'rb')); A=D['A']; N=196608
def q(name, x):
    v=x[~np.isnan(x)]
    print(f"{name:10} n={v.size:6} null={N-v.size:6} min={v.min():.4g} p1={np.percentile(v,1):.4g} p5={np.percentile(v,5):.4g} p25={np.percentile(v,25):.4g} p50={np.percentile(v,50):.4g} p75={np.percentile(v,75):.4g} p95={np.percentile(v,95):.4g} p99={np.percentile(v,99):.4g} max={v.max():.4g} zeros={int((v==0).sum())}")
for k in ['lat','elev','mola_n','ti','albedo','ctx','hr4','hr11','hproj','hdtm_n','crism_n','swim01','swim15','swim5','dust','dust_unc','dust_rel','dust_n','n_units','n_anchor','t_lo','t_hi','s_lo','s_hi']: q(k,A[k])
print('bounds combos', collections.Counter(zip(A['t_lo'],A['t_hi'],A['s_lo'],A['s_hi'])).most_common(6))
# units
unit=np.array([u or '' for u in D['unit']]); cnt=collections.Counter(unit)
print('units',len(cnt)-('' in cnt), 'none',cnt.get('',0), 'multi',len(D['units_multi']), list(D['units_multi'].items())[:4])
for u,c in cnt.most_common():
    print(f"  {u:6} {c:6} {100*c/N:5.2f}%  {D['unitinfo'].get(u,('','(no unit)'))}")
# science layer presence per cell
layers={'geology':unit!='', 'ti_measured':np.array([s=='archive_noninterpolated' for s in D['ti_status']]),
        'albedo':~np.isnan(A['albedo']),'swim':~np.isnan(A['swim01']),'dust':~np.isnan(A['dust']),
        'crism':A['crism_n']>0,'ctx':A['ctx']>0,'hirise':A['hproj']>0,'hirise_dtm':A['hdtm_n']>0,'mola_obs':A['mola_n']>0}
for k,v in layers.items(): print(f"layer {k:12} {int(v.sum()):6} {100*v.mean():6.2f}%")
core=['geology','ti_measured','albedo','swim','dust']
ncore=sum(layers[k].astype(int) for k in core)
print('core science layers present per cell', collections.Counter(ncore.tolist()))
allc=sum(v.astype(int) for v in layers.values()); print('all 10 layers per cell', sorted(collections.Counter(allc.tolist()).items()))
lat=A['lat']
for k in ['geology','ti_measured','swim','dust']:
    m=~layers[k]; print('missing',k,'n',int(m.sum()),'lat range of missing: p5..p95', np.percentile(lat[m],[0,5,50,95,100]).round(1), 'abs>60 share',float((np.abs(lat[m])>60).mean().round(3)))
print('ti no_positive', collections.Counter(np.array(D['ti_status'])[np.isnan(A['ti'])|(A['ti']<=0)].tolist()))
# neighbours
lon=np.radians(A['lon']); la=np.radians(lat)
xyz=np.c_[np.cos(la)*np.cos(lon),np.cos(la)*np.sin(lon),np.sin(la)]
t=cKDTree(xyz); d,idx=t.query(xyz,k=9)
h=np.sqrt(4*np.pi/N); print('pixel scale rad',h,'km',h*3389.5)
print('neighbour dist/h percentiles k=1..8:', [np.round(np.percentile(d[:,j]/h,[1,50,99]),2).tolist() for j in range(1,9)])
edge=d[:,1:]<1.25*h; print('edge-neigh count dist',collections.Counter(edge.sum(1).tolist()))
n8=d[:,1:]<1.75*h; print('8-neigh count dist',collections.Counter(n8.sum(1).tolist()))
def graph(mask_pairs):
    r=np.repeat(np.arange(N),8)[mask_pairs.ravel()]; c=idx[:,1:].ravel()[mask_pairs.ravel()]
    return r,c
for name,nb in (('4-conn',edge),('8-conn',n8)):
    r,c=graph(nb)
    same=unit[r]==unit[c]
    print(name,'share of neighbour pairs with same geologic unit',same.mean().round(4))
    g=coo_matrix((np.ones(same.sum()),(r[same],c[same])),shape=(N,N))
    nc,lab=connected_components(g,directed=False); sz=np.bincount(lab)
    print(name,'unit patches',nc,'median',np.median(sz),'mean',sz.mean().round(1),'p90',np.percentile(sz,90),'max',sz.max(),'singletons',int((sz==1).sum()),'cells in patches>=4',int(sz[sz>=4].sum()))
    for nm,x in (('elev',A['elev']),('ti',A['ti']),('albedo',A['albedo']),('swim01',A['swim01']),('dust',A['dust']),('ctx',A['ctx'])):
        ok=~np.isnan(x[r])&~np.isnan(x[c]); print('   neighbour corr',nm,np.corrcoef(x[r][ok],x[c][ok])[0,1].round(3))
    # crism clusters
    m=layers['crism']; ok=m[r]&m[c]; g=coo_matrix((np.ones(ok.sum()),(r[ok],c[ok])),shape=(N,N)); nc,lab=connected_components(g,directed=False); sz=np.bincount(lab[m])
    sz=sz[sz>0]; print('   crism cells',int(m.sum()),'clusters',len(sz),'singletons',int((sz==1).sum()),'max',sz.max())
# correlation length: correlation vs ring distance for elev, ti, albedo
rng=np.random.default_rng(1); samp=rng.choice(N,20000,replace=False)
for mult in (1,2,4,8,16,32):
    dd,ii=t.query(xyz[samp],k=1,distance_upper_bound=np.inf) 
    # pick a point at approx mult*h: query ball shell via k large is costly; use k=(2*mult+1)^2 and take the farthest
    k=min((2*mult+1)**2,1200); dd,ii=t.query(xyz[samp],k=k); j=ii[:,-1]
    out=[]
    for nm in ('elev','ti','albedo','swim01'):
        x=A[nm]; ok=~np.isnan(x[samp])&~np.isnan(x[j]); out.append((nm,float(np.corrcoef(x[samp][ok],x[j][ok])[0,1].round(3))))
    out.append(('same_unit',float((unit[samp]==unit[j]).mean().round(3))))
    print('lag ~',round(float(np.median(dd[:,-1])/h),1),'cells',round(float(np.median(dd[:,-1])*3389.5)),'km',out)
print('anchors',[(i,a[0]['name']) for i,a in sorted(D['anchors'].items())][:8], len(D['anchors']))
pickle.dump(dict(idx=idx,d=d,h=h),open(sys.argv[2],'wb'))
