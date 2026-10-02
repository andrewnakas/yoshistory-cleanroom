import numpy as np, struct, json, sys
sys.path.insert(0,'.')
from games.yoshistory import texscan
rom=open('D:/n64work/yoshistory/baserom.us.z64','rb').read()
tex,tl,ovl=texscan.scan(rom)
cov=np.zeros(len(rom),np.uint8)
for o,e in tex.items(): cov[o:o+e['size']]=1
for o,n in tl.items(): cov[o:o+2*n]=2
rows=[]
for r0,r1,v0,v1 in ovl:
    off=struct.unpack_from('>I',rom,r1-4)[0]; h=r1-off
    if h<=r0 or off>r1-r0: continue
    t,d,ro,bss,n=struct.unpack_from('>5I',rom,h)
    if t+d>r1-r0: continue
    D=r0+t
    for p in range(D,D+d-7,8):
        if cov[p]: continue
        if rom[p] in (0xE7,0xB8,0xB9,0xBA,0xBB,0xFC,0xF5,0xF2,0xF3,0xFD,0xE6,0xF0,0xBF,0xB1,0x04,0x06,0xB6,0xB7,0xE8,0xFB,0xFA,0xB5,0x01,0x03,0xBC,0xBD):
            cov[p:p+8]=3
    un=(cov[D:D+d]==0)
    hi=0; segs=[]
    for p in range(D,D+d-255,256):
        if (cov[p:p+256]==0).mean()>0.9:
            blk=np.frombuffer(rom[p:p+256],np.uint8)
            if len(np.unique(blk))>24 and (blk==0).mean()<0.25:
                hi+=256
                if segs and segs[-1][1]==p: segs[-1][1]=p+256
                else: segs.append([p,p+256])
    rows.append((hi,r0,d,int(un.sum()),segs))
print("total hi-unexplained", sum(r[0] for r in rows))
for hi,r0,d,un,segs in sorted(rows,reverse=True)[:30]: print("%x data %x unexplained %x hi %x"%(r0,d,un,hi), ["%x+%x"%(a,b-a) for a,b in segs[:4]])
