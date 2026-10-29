import json, re, httpx
from .config import settings
from .security import sanitize
SYSTEM='''You are a senior engineer. Return ONLY valid JSON: {"project_name":"kebab-case","summary":"summary","files":{"relative/path":"complete file content"}}. Generate a runnable, internally consistent project matching requirements and stack. Include README.md, .gitignore, .env.example placeholders and dependency manifests. No real secrets, absolute paths, parent traversal, or markdown fences.'''
async def generate_code(topic,stack):
    if not settings.ai_api_key: raise RuntimeError("AI provider is not configured. Set AI_API_KEY in backend/.env.")
    async with httpx.AsyncClient(timeout=180) as c:
        r=await c.post(settings.ai_base_url.rstrip("/")+"/chat/completions",headers={"Authorization":"Bearer "+settings.ai_api_key},json={"model":settings.ai_model,"temperature":0.2,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":f"Requirements:\n{topic}\nPreferred stack: {stack}"}]})
        r.raise_for_status(); body=r.json()
    raw=re.sub(r"^```(?:json)?\s*|\s*```$","",body["choices"][0]["message"]["content"].strip(),flags=re.I)
    data=json.loads(raw); f=sanitize(data.get("files",{}))
    f.setdefault("README.md","# "+data.get("project_name","Generated Project")+"\n\n"+data.get("summary",topic))
    f.setdefault(".gitignore",".env\nnode_modules/\n.venv/\n__pycache__/\ndist/\n")
    f.setdefault(".env.example","# Local placeholders only; never commit .env")
    return data,f
