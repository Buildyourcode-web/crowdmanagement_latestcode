import ast, sqlite3
from pathlib import Path

# 1. Syntax checks
files = [
    'app/frs_engine/frs_service.py',
    'app/frs_engine/database/repository.py',
    'app/frs_engine/recognition/matcher.py',
]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'  [OK]  {f}')
    except Exception as e:
        print(f'  [ERR] {f}: {e}')

# 2. DB verification
db_path = Path(r'c:\khairatabad_ganesh\backend\data\frs_rnd.db')
if db_path.exists():
    db = sqlite3.connect(str(db_path))
    cur = db.cursor()
    cur.execute('SELECT COUNT(1) FROM people')
    print(f'\nfrs_rnd.db people count    : {cur.fetchone()[0]}')
    cur.execute('SELECT COUNT(1) FROM face_embeddings')
    print(f'frs_rnd.db embeddings count: {cur.fetchone()[0]}')
    cur.execute('SELECT category, COUNT(1) FROM people GROUP BY category')
    for cat, cnt in cur.fetchall():
        print(f'  Category [{cat}]: {cnt} persons')
    db.close()
else:
    print('frs_rnd.db NOT FOUND!')

# 3. FAISS index check
import faiss
idx_path = Path(r'c:\khairatabad_ganesh\backend\data\frs_gallery\gallery_2019.index')
if idx_path.exists():
    idx = faiss.read_index(str(idx_path))
    print(f'\nFAISS index vectors  : {idx.ntotal}')
    print(f'FAISS index dimension: {idx.d}')
else:
    print('FAISS index NOT FOUND')
