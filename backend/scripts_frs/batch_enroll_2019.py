import re, sys, json, time, sqlite3, logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)-7s  %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('enroll-2019')

ROOT_IMAGES = Path(r'C:\Users\HP\OneDrive\Documents\2019 -ALL TILL COIVD\2019 -ALL TILL COIVD')
BACKEND_DIR = Path(r'c:\khairatabad_ganesh\backend')
GALLERY_DIR = BACKEND_DIR / 'data' / 'frs_gallery'
DB_PATH     = BACKEND_DIR / 'data' / 'frs' / 'embeddings.db'
INDEX_PATH  = GALLERY_DIR / 'gallery_2019.index'
REPORT_PATH = GALLERY_DIR / 'enrollment_report.json'

GALLERY_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

try:
    import faiss
    FAISS_OK = True
    log.info('FAISS available')
except ImportError:
    FAISS_OK = False
    log.warning('FAISS not installed')

log.info('Loading InsightFace...')
from insightface.app import FaceAnalysis
face_app = FaceAnalysis(name='buffalo_l', providers=['CUDAExecutionProvider','CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_size=(640, 640))
log.info('InsightFace OK')

conn = sqlite3.connect(str(DB_PATH))
conn.execute('''CREATE TABLE IF NOT EXISTS face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
    person_name TEXT NOT NULL, category TEXT DEFAULT 'general',
    source_file TEXT, month_folder TEXT, embedding BLOB NOT NULL, enrolled_at TEXT NOT NULL
)''')
conn.execute('CREATE INDEX IF NOT EXISTS idx_person_id ON face_embeddings(person_id)')
conn.commit()

_SEQ = re.compile(r'^(.+?)\s*\(\d+\)$')
def pid(stem): m = _SEQ.match(stem.strip()); return m.group(1).strip() if m else stem.strip()
def norm(v): n = np.linalg.norm(v); return (v/n).astype(np.float32) if n>1e-9 else v.astype(np.float32)

def proc(img_path):
    try:
        img = cv2.imread(str(img_path))
        if img is None: return []
        h,w = img.shape[:2]
        if max(h,w)>1920:
            s=1920/max(h,w); img=cv2.resize(img,(int(w*s),int(h*s)))
        faces = face_app.get(img)
        return [norm(np.array(f.embedding,dtype=np.float32)) for f in faces if f.embedding is not None and f.det_score>=0.45]
    except: return []

subfolders = sorted([d for d in ROOT_IMAGES.iterdir() if d.is_dir()])
log.info(f'Found {len(subfolders)} folders')

all_embs,all_pids,all_names=[],[],[]
person_count=defaultdict(int)
stats={'total_images':0,'total_faces':0,'total_persons':0,'by_folder':{},'no_face':[],'started_at':datetime.now(timezone.utc).isoformat()}
t0=time.time()

for folder in subfolders:
    cat='pickpocket_watchlist' if 'pick' in folder.name.lower() else 'general'
    imgs=sorted(list(folder.rglob('*.[jJ][pP][gG]'))+list(folder.rglob('*.[jJ][pP][eE][gG]'))+list(folder.rglob('*.[pP][nN][gG]'))+list(folder.rglob('*.[bB][mM][pP]')))
    log.info(f'--- {folder.name} ({len(imgs)} images, cat={cat}) ---')
    fdone,funiq=0,set()
    for i,p in enumerate(imgs):
        embs=proc(p)
        person_id=pid(p.stem)
        if not embs:
            stats['no_face'].append(str(p.name))
            continue
        emb=embs[0]
        conn.execute('INSERT INTO face_embeddings(person_id,person_name,category,source_file,month_folder,embedding,enrolled_at) VALUES(?,?,?,?,?,?,?)',
            (person_id,person_id,cat,str(p),folder.name,emb.astype(np.float32).tobytes(),datetime.now(timezone.utc).isoformat()))
        person_count[person_id]+=1; all_embs.append(emb); all_pids.append(person_id); all_names.append(person_id)
        fdone+=1; funiq.add(person_id); stats['total_faces']+=1
        if i%100==0: log.info(f'  [{i+1}/{len(imgs)}] faces={fdone} persons={len(funiq)} rate={stats["total_faces"]/(time.time()-t0):.1f}/s')
    conn.commit()
    log.info(f'  DONE {folder.name}: {fdone} embeddings, {len(funiq)} unique persons')
    stats['by_folder'][folder.name]={'images':len(imgs),'faces':fdone,'persons':len(funiq)}
    stats['total_images']+=len(imgs)

stats['total_persons']=len(person_count)
log.info(f'Building FAISS index for {len(all_embs)} embeddings...')
if FAISS_OK and all_embs:
    mat=np.vstack(all_embs).astype(np.float32)
    bi=faiss.IndexFlatIP(mat.shape[1]); fi=faiss.IndexIDMap2(bi)
    ids=np.arange(len(all_embs),dtype=np.int64)
    meta={str(i):[p,n] for i,(p,n) in enumerate(zip(all_pids,all_names))}
    fi.add_with_ids(mat,ids)
    faiss.write_index(fi,str(INDEX_PATH))
    with open(str(INDEX_PATH)+'.meta.json','w') as f: json.dump(meta,f)
    log.info(f'FAISS saved: {fi.ntotal} vectors -> {INDEX_PATH}')
    stats['faiss_vectors']=int(fi.ntotal); stats['faiss_path']=str(INDEX_PATH)

stats['completed_at']=datetime.now(timezone.utc).isoformat()
stats['duration_s']=round(time.time()-t0,1)
with open(REPORT_PATH,'w') as f: json.dump(stats,f,indent=2,default=str)
conn.close()

print(f'''
========================================
ENROLLMENT COMPLETE!
========================================
Images processed : {stats['total_images']}
Faces detected   : {stats['total_faces']}
Unique persons   : {stats['total_persons']}
No-face skipped  : {len(stats['no_face'])}
Duration         : {stats['duration_s']}s
FAISS index      : {INDEX_PATH}
SQLite DB        : {DB_PATH}
Report           : {REPORT_PATH}
========================================''')
