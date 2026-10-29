import re
from pathlib import PurePosixPath
BLOCKED_PARTS={".git","node_modules","__pycache__",".venv","venv","dist","build",".pytest_cache"}
def safe_path(value):
    if not isinstance(value,str) or not value or len(value)>240: raise ValueError("Invalid file path")
    value=value.replace("\\\\","/")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ("","..",".") for x in p.parts): raise ValueError("Unsafe file path")
    if any(x.lower() in BLOCKED_PARTS for x in p.parts): raise ValueError("Blocked path")
    name=p.name.lower()
    if name==".env" or name.startswith(".env.") or name.endswith((".pem",".key",".p12",".pfx")) or re.search(r"(secret|credential|private[-_]?key|token)",name):
        raise ValueError("Environment and credential files cannot be included")
    return str(p)
def sanitize(files):
    if not isinstance(files,dict) or not files: raise ValueError("No generated files")
    if len(files)>150: raise ValueError("Too many generated files")
    out={}; total=0
    for name,content in files.items():
        path=safe_path(name)
        if not isinstance(content,str): raise ValueError("File content must be text")
        total+=len(content.encode())
        if total>5_000_000: raise ValueError("Generated project exceeds 5 MB")
        out[path]=content
    return out
