import sqlite3, json
from pathlib import Path
from .config import settings
def conn():
    p=Path(settings.database_path); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row; return c
def init_db():
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, topic TEXT, stack TEXT, files_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS states (state TEXT PRIMARY KEY, created INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS tokens (sid TEXT PRIMARY KEY, token TEXT, login TEXT)")
def save_project(i,t,s,f):
    with conn() as c: c.execute("INSERT INTO projects(id,topic,stack,files_json) VALUES(?,?,?,?)",(i,t,s,json.dumps(f)))
def get_project(i):
    with conn() as c: r=c.execute("SELECT * FROM projects WHERE id=?",(i,)).fetchone()
    return {"id":r["id"],"topic":r["topic"],"stack":r["stack"],"files":json.loads(r["files_json"])} if r else None
def add_state(s,n):
    with conn() as c: c.execute("INSERT INTO states VALUES(?,?)",(s,n))
def consume_state(s,n):
    with conn() as c:
        r=c.execute("SELECT created FROM states WHERE state=?",(s,)).fetchone(); c.execute("DELETE FROM states WHERE state=?",(s,))
    return bool(r and n-r["created"]<=600)
def save_token(s,t,l):
    with conn() as c: c.execute("INSERT OR REPLACE INTO tokens VALUES(?,?,?)",(s,t,l))
def get_token(s):
    with conn() as c: r=c.execute("SELECT token,login FROM tokens WHERE sid=?",(s,)).fetchone()
    return dict(r) if r else None
