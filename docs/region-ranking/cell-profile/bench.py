import pickle, numpy as np, time, sys
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
D=pickle.load(open(sys.argv[2],'rb')); A=D['A']; NB=pickle.load(open(sys.argv[3],'rb')); N=196608
unit=np.array([u or '' for u in D['unit']])
rng=np.random.default_rng(3)
# concept matrix: 3 real + 29 filler with realistic sparsity
sw=np.fmax(np.fmax(A['swim01'],A['swim15']),A['swim5'])
ice=np.nan_to_num(np.clip(sw/0.5,0,1)); noach=np.array([1.0 if u.lstrip('elm')[:1]=='N' else 0.0 for u in unit]); rocky=np.nan_to_num(np.clip((A['ti']-350)/150,0,1))
M=np.zeros((32,N),np.uint8); M[0]=ice*255; M[1]=noach*255; M[2]=rocky*255
for i in range(3,32): M[i]=(rng.random(N)<rng.uniform(0.005,0.3))*255
np.save('/tmp/M.npy',M);
def T(f,n=200):
    t=time.perf_counter()
    for _ in range(n): r=f()
    return (time.perf_counter()-t)/n*1000, r
Mm=np.load('/tmp/M.npy',mmap_mode='r')
w=np.array([2.36,0.29,3.11],np.float32)/255
def score(): return (w[:,None]*Mm[:3]).sum(0,dtype=np.float32)
ms,s=T(score); print('score 3 concepts float32  %.3f ms'%ms)
wi=np.round(w*255*256).astype(np.uint32)
def score_i(): return wi[0]*Mm[0].astype(np.uint32)+wi[1]*Mm[1]+wi[2]*Mm[2]
ms,si=T(score_i); print('score integer fixed-point  %.3f ms'%ms)
def score8(): return (np.ones(8,np.float32)[:,None]*Mm[:8]).sum(0,dtype=np.float32)
ms,_=T(score8,50); print('score 8 concepts          %.3f ms'%ms)
direct=(Mm[0]>=128)&(Mm[1]>=128)
def topk():
    k=np.argpartition(-si,1000)[:1000]; return k[np.lexsort((k,-si[k].astype(np.int64)))]
ms,_=T(topk); print('top-1000 cells             %.3f ms'%ms)
def tiles():
    t=si.reshape(-1,16); return t.max(1), t.sum(1), direct.reshape(-1,16).sum(1)
ms,(tmax,tsum,tcnt)=T(tiles); print('Nside-32 tile aggregates   %.3f ms (%d tiles)'%(ms,len(tmax)))
def tile_top():
    k=np.argpartition(-tmax.astype(np.int64),50)[:50]; return k
ms,_=T(tile_top); print('top-50 tiles               %.3f ms'%ms)
# pruned scoring: only cells in tiles whose per-concept max bound can reach top
P=Mm[:3].reshape(3,-1,16).max(2)  # precomputed tile pyramid
def pruned():
    ub=wi[0]*P[0].astype(np.uint32)+wi[1]*P[1]+wi[2]*P[2]
    cand=np.flatnonzero(ub>=np.partition(ub,-200)[-200]); cells=(cand[:,None]*16+np.arange(16)).ravel()
    return wi[0]*Mm[0][cells].astype(np.uint32)+wi[1]*Mm[1][cells]+wi[2]*Mm[2][cells]
ms,_=T(pruned); print('pyramid-pruned scoring     %.3f ms'%ms)
# grouping
idx=NB['idx'][:,1:].astype(np.int32); ok=NB['d'][:,1:]<1.75*NB['h']
def group():
    c=np.flatnonzero(direct); nb=idx[c]; m=ok[c]&direct[nb]
    r=np.repeat(c,8)[m.ravel()]; cc=nb.ravel()[m.ravel()]
    g=coo_matrix((np.ones(len(r),np.bool_),(r,cc)),shape=(N,N)); n,lab=connected_components(g,directed=False)
    key=lab[c].astype(np.int64)*12288+(c>>4); u,inv,cnt=np.unique(key,return_inverse=True,return_counts=True)
    return len(u)
ms,na=T(group,20); print('group %d direct cells -> %d areas  %.2f ms'%(direct.sum(),na,ms))
bits=np.packbits(direct); print('bitset bytes',bits.nbytes,'matrix MB',M.nbytes/1e6,'neighbour table MB',idx.nbytes/1e6)
def band(): return np.bitwise_and(bits,bits)
ms,_=T(band,2000); print('bitset AND                 %.4f ms'%ms)
import gzip,json
t=time.perf_counter(); n=0
for line in gzip.open(sys.argv[1],'rt'):
    n+=1
    if n==20000: break
print('ndjson parse rate rows/s', round(20000/(time.perf_counter()-t)))
