import pickle, sys, collections, json
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
D=pickle.load(open(sys.argv[1],'rb')); A=D['A']; NB=pickle.load(open(sys.argv[2],'rb')); N=196608
unit=np.array([u or '' for u in D['unit']]); lat=A['lat']; ti=A['ti']; alb=A['albedo']
tim=np.array([s=='archive_noninterpolated' for s in D['ti_status']])
grp=np.array([D['unitinfo'].get(u,('',''))[1] for u in unit])
print('groups',collections.Counter(grp).most_common())
def age(u):
    s=set()
    core=u.lstrip('elm') if u else ''
    for ch in core:
        if ch=='N': s.add('N')
        elif ch=='H': s.add('H')
        elif ch=='A': s.add('A')
        else: break
    return s
ages=[age(u) for u in unit]
C={}
C['age-noachian']=np.array(['N' in a for a in ages]); C['age-noachian-only']=np.array([a=={'N'} for a in ages])
C['age-hesperian']=np.array(['H' in a for a in ages]); C['age-amazonian']=np.array(['A' in a for a in ages]); C['age-amazonian-only']=np.array([a=={'A'} for a in ages])
for g,k in (('Volcanic Units','volcanic'),('Highland Units','highland'),('Lowland Units','lowland'),('Transition Units','transition'),('Basin Units','basin'),('Polar Units','polar-unit'),('Apron Units','apron'),('Impact Unit','impact')): C[k]=grp==g
C['volcanic-edifice']=np.isin(unit,['Ave','Hve','Nve']); C['volcanic-field']=np.isin(unit,['lHvf','lAvf']); C['young-volcanic']=np.isin(unit,['lAv','lAvf','Av','Ave'])
C['outflow']=unit=='Hto'; C['polar-cap']=unit=='lApc'; C['polar-dunes']=unit=='lApd'; C['massif']=np.isin(unit,['eNhm','mNhm'])
for k in ('swim01','swim15','swim5'):
    x=A[k]
    for th in (0.0,0.25,0.5): C[f'{k}>{th}']=x>th
sw=np.nanmax(np.c_[A['swim01'],A['swim15'],A['swim5']],axis=1)
C['ice-any>0.25']=sw>0.25; C['ice-any>0.5']=sw>0.5
C['crism-target']=A['crism_n']>0; C['hirise']=A['hproj']>0; C['hirise-dtm']=A['hdtm_n']>0; C['stereo(any dtm)']=None
del C['stereo(any dtm)']
# thermophysical classes on measured TI
for name,m in (('TI<100',ti<100),('TI>=350',ti>=350),('TI>=500',ti>=500),('alb>=0.23',alb>=0.23),('alb<0.15',alb<0.15)):
    print(name, int((m&tim).sum()), round(100*(m&tim).sum()/tim.sum(),2),'% of measured')
C['dust-mantled (TI<100 & alb>=0.23)']=(ti<100)&(alb>=0.23)&tim
C['rocky/indurated (TI>=350)']=(ti>=350)&tim
C['dark coarse (TI>=200 & alb<0.15)']=(ti>=200)&(alb<0.15)&tim
C['polar-lat>=65']=np.abs(lat)>=65; C['polar-lat>=60']=np.abs(lat)>=60
C['low-elev<-4000']=A['elev']<-4000; C['high-elev>4000']=A['elev']>4000
idx=NB['idx']; d=NB['d']; h=NB['h']; n8=d[:,1:]<1.75*h
r=np.repeat(np.arange(N),8)[n8.ravel()]; c=idx[:,1:].ravel()[n8.ravel()]
def comps(m):
    ok=m[r]&m[c]; g=coo_matrix((np.ones(ok.sum()),(r[ok],c[ok])),shape=(N,N)); nc,lab=connected_components(g,directed=False); sz=np.bincount(lab[m]); sz=sz[sz>0]; return sz
for k,m in C.items():
    sz=comps(m); n=int(m.sum())
    idf=np.log(1+(N-n+0.5)/(n+0.5))
    print(f"{k:36} cells {n:6} {100*n/N:6.2f}% idf {idf:5.2f} areas {len(sz):5} median {int(np.median(sz)) if len(sz) else 0:4} max {int(sz.max()) if len(sz) else 0:6} singles {int((sz==1).sum()):5}")
# SWIM by lat band
for lo,hi in ((0,30),(30,45),(45,60)):
    m=(np.abs(lat)>=lo)&(np.abs(lat)<hi)&~np.isnan(sw); print('swim band',lo,hi,'cells',int(m.sum()),'share>0.25',round(float((sw[m]>0.25).mean()),3),'>0.5',round(float((sw[m]>0.5).mean()),3))
print('swim lat domain', np.nanmin(lat[~np.isnan(sw)]), np.nanmax(lat[~np.isnan(sw)]))
# sparse candidates
geo=unit!=''; swp=~np.isnan(sw); dust=~np.isnan(A['dust'])
L3=geo.astype(int)+tim.astype(int)+swp.astype(int)
print('3 concept layers (geology, measured TI, SWIM) present:',sorted(collections.Counter(L3.tolist()).items()))
print('polar-unit cells missing SWIM', int((C['polar-unit']&~swp).sum()),'of',int(C['polar-unit'].sum()))
sparse=(~geo)|((~tim)&(~swp)); print('sparse rule A (no geology OR (no measured TI AND no SWIM))',int(sparse.sum()),round(100*sparse.mean(),2))
print('  lat dist of sparse A', np.percentile(np.abs(lat[sparse]),[5,25,50,75,95]).round(1))
sparseB=L3<=1; print('rule B (<=1 of 3)',int(sparseB.sum()))
print('no geology & others', collections.Counter(L3[~geo].tolist()))
# no-geology cells: neighbours majority available?
ng=np.where(~geo)[0]; cnt=0
for i in ng:
    nb=idx[i,1:][n8[i]]; cnt+= any(unit[j]!='' for j in nb)
print('no-geology cells with a mapped neighbour',cnt,'of',len(ng))
# high-res targeting tiers
ctx=A['ctx']; print('ctx==0',int((ctx==0).sum()),'ctx<=1',int((ctx<=1).sum()),'ctx>=10',int((ctx>=10).sum()))
tgt=(A['crism_n']>0)|(A['hproj']>0)|(A['hdtm_n']>0); print('any targeted (CRISM/HiRISE/DTM)',int(tgt.sum()),round(100*tgt.mean(),2))
print('untargeted & ctx<=2', int((~tgt&(ctx<=2)).sum()))
# example query: noachian + crism target + low doc
ex=C['age-noachian-only']&C['rocky/indurated (TI>=350)']; sz=comps(ex); print('example noachian-only & rocky',int(ex.sum()),'areas',len(sz),'untargeted',int((ex&~tgt).sum()))
ex=C['ice-any>0.5']&C['apron']; print('ice>0.5 & apron',int(ex.sum()))
print('apron by unit & lat', {u:(int((unit==u).sum()), np.percentile(np.abs(lat[unit==u]),[5,50,95]).round(0).tolist(), np.percentile(A['lon'][unit==u],[5,50,95]).round(0).tolist()) for u in ('Aa','lAa','ANa')})
print('anchors in sparse', sum(1 for i in D['anchors'] if sparse[i]))
