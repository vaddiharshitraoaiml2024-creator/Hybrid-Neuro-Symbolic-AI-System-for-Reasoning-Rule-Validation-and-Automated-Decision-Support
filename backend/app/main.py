import io, json, secrets, time, uuid
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from itsdangerous import URLSafeSerializer, BadSignature
from .config import settings
from .db import init_db, save_project, get_project, add_state, consume_state, save_token, get_token
from .generator import generate_code
from .security import sanitize
app=FastAPI(title="AI Project Builder API")
app.add_middleware(__import__("fastapi").middleware.cors.CORSMiddleware,allow_origins=[settings.frontend_url],allow_credentials=True,allow_methods=["GET","POST","OPTIONS"],allow_headers=["*"])
signer=URLSafeSerializer(settings.app_secret,salt="apb-session")
@app.on_event("startup")
def startup(): init_db()
def sid(request):
    try: return signer.loads(request.cookies["apb_session"])["sid"]
    except (KeyError,BadSignature,TypeError): return None
def cookie(response,s):
    response.set_cookie("apb_session",signer.dumps({"sid":s}),httponly=True,secure=settings.cookie_secure,samesite="lax",max_age=604800)
def project_or_404(i):
    p=get_project(i)
    if not p: raise HTTPException(404,"Project not found")
    return p
@app.get("/api/health")
def health(): return {"status":"ok","ai_configured":bool(settings.ai_api_key),"github_configured":bool(settings.github_client_id and settings.github_client_secret)}
@app.post("/api/projects/analyze")
async def analyze(topic:str=Form(""),stack:str=Form("React + Vite, FastAPI + Python"),upload:UploadFile|None=File(None)):
    text=(topic or "").strip()
    if upload:
        raw=await upload.read(settings.max_upload_mb*1024*1024+1)
        if len(raw)>settings.max_upload_mb*1024*1024: raise HTTPException(413,"Upload too large")
        name=(upload.filename or "").lower()
        try:
            if name.endswith(".txt"): extracted=raw.decode("utf-8",errors="replace")
            elif name.endswith(".pdf"):
                from PyPDF2 import PdfReader
                extracted="\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
            elif name.endswith(".docx"):
                from docx import Document
                extracted="\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
            elif name.endswith((".png",".jpg",".jpeg",".webp")): raise HTTPException(422,"OCR is not configured for images. Paste the image text or configure an OCR provider.")
            else: raise HTTPException(415,"Supported files: PDF, DOCX, TXT, PNG, JPG, WEBP")
            text=(text+"\n\n"+extracted).strip()
        except HTTPException: raise
        except Exception as e: raise HTTPException(422,"Document extraction failed: "+str(e))
    if not text: raise HTTPException(400,"Enter a topic or upload a specification")
    if len(text)>100000: raise HTTPException(413,"Specification exceeds 100,000 characters")
    return {"topic":text,"stack":stack,"character_count":len(text)}
class GenerateRequest(BaseModel):
    topic:str=Field(min_length=5,max_length=100000)
    stack:str=Field(default="React + Vite, FastAPI + Python",max_length=200)
@app.post("/api/projects/generate")
async def generate(payload:GenerateRequest):
    try: data,files=await generate_code(payload.topic,payload.stack)
    except RuntimeError as e: raise HTTPException(503,str(e))
    except httpx.HTTPStatusError as e: raise HTTPException(502,f"AI provider HTTP {e.response.status_code}")
    except httpx.RequestError: raise HTTPException(502,"Could not connect to AI provider")
    except (ValueError,KeyError,json.JSONDecodeError) as e: raise HTTPException(502,"Invalid AI project response: "+str(e))
    i=str(uuid.uuid4()); save_project(i,payload.topic,payload.stack,files)
    return {"project_id":i,"project_name":data.get("project_name","Generated Project"),"summary":data.get("summary",""),"files":[{"path":p,"size":len(c.encode())} for p,c in files.items()]}
@app.get("/api/projects/{project_id}/files")
def list_files(project_id:str):
    p=project_or_404(project_id)
    return {"project_id":project_id,"files":[{"path":k,"content":v,"size":len(v.encode())} for k,v in sorted(p["files"].items())]}
@app.get("/api/projects/{project_id}/download")
def download(project_id:str):
    f=sanitize(project_or_404(project_id)["files"]); b=io.BytesIO()
    with ZipFile(b,"w",ZIP_DEFLATED) as z:
        for k,v in f.items(): z.writestr(k,v)
    b.seek(0)
    return StreamingResponse(b,media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="ai-project-{project_id[:8]}.zip"'})
@app.get("/api/github/login")
def github_login(request:Request):
    if not settings.github_client_id or not settings.github_client_secret: raise HTTPException(503,"Configure GitHub OAuth credentials in backend/.env")
    state=secrets.token_urlsafe(32); add_state(state,int(time.time())); s=sid(request) or secrets.token_urlsafe(24)
    url="https://github.com/login/oauth/authorize?"+urlencode({"client_id":settings.github_client_id,"redirect_uri":settings.github_callback_url,"scope":"repo read:user","state":state})
    r=RedirectResponse(url); cookie(r,s); return r
@app.get("/api/github/callback")
async def github_callback(request:Request,code:str="",state:str=""):
    if not code or not consume_state(state,int(time.time())): raise HTTPException(400,"Invalid or expired OAuth state")
    async with httpx.AsyncClient(timeout=30) as c:
        tr=await c.post("https://github.com/login/oauth/access_token",headers={"Accept":"application/json"},json={"client_id":settings.github_client_id,"client_secret":settings.github_client_secret,"code":code,"redirect_uri":settings.github_callback_url})
        if tr.status_code!=200 or not tr.json().get("access_token"): raise HTTPException(401,"GitHub token exchange failed")
        token=tr.json()["access_token"]
        ur=await c.get(settings.github_api_url.rstrip("/")+"/user",headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"})
        if ur.status_code!=200: raise HTTPException(502,"Could not fetch GitHub profile")
    s=sid(request) or secrets.token_urlsafe(24); save_token(s,token,ur.json().get("login",""))
    r=RedirectResponse(settings.frontend_url+"?github=connected"); cookie(r,s); return r
@app.get("/api/github/repositories")
async def repositories(request:Request):
    t=get_token(sid(request)) if sid(request) else None
    if not t: raise HTTPException(401,"Connect GitHub first")
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.get(settings.github_api_url.rstrip("/")+"/user/repos",params={"sort":"updated","per_page":100,"affiliation":"owner,collaborator"},headers={"Authorization":"Bearer "+t["token"],"Accept":"application/vnd.github+json"})
    if r.status_code==401: raise HTTPException(401,"GitHub authorization expired; reconnect")
    if r.status_code==403: raise HTTPException(403,"GitHub rate limit or permission denied")
    if r.status_code!=200: raise HTTPException(502,"Could not list repositories")
    return {"login":t["login"],"repositories":[{"full_name":x["full_name"],"name":x["name"],"private":x["private"],"default_branch":x["default_branch"],"html_url":x["html_url"]} for x in r.json()]}
class Publish(BaseModel):
    project_id:str
    mode:str=Field(pattern="^(create|existing)$")
    repo_name:str=Field(min_length=1,max_length=100)
    description:str=""
    private:bool=True
    branch:str=Field(default="main",min_length=1,max_length=100)
    confirm:bool
    existing_full_name:str|None=None
def gh(token): return {"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
@app.post("/api/github/publish")
async def publish(x:Publish,request:Request):
    if not x.confirm: raise HTTPException(400,"Explicit confirmation required")
    files=sanitize(project_or_404(x.project_id)["files"]); t=get_token(sid(request)) if sid(request) else None
    if not t: raise HTTPException(401,"Connect GitHub before publishing")
    base=settings.github_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60) as c:
        if x.mode=="create":
            r=await c.post(base+"/user/repos",headers=gh(t["token"]),json={"name":x.repo_name,"description":x.description,"private":x.private,"auto_init":True})
            if r.status_code==422: raise HTTPException(409,"Repository name conflict or validation error")
            if r.status_code==403: raise HTTPException(403,"Permission denied or GitHub rate limit")
            if r.status_code!=201: raise HTTPException(502,f"Repository creation failed (HTTP {r.status_code})")
            repo=r.json(); full=repo["full_name"]
        else:
            full=x.existing_full_name or ""
            if "/" not in full: raise HTTPException(400,"Select owner/repository")
            r=await c.get(base+"/repos/"+full,headers=gh(t["token"]))
            if r.status_code==404: raise HTTPException(404,"Repository not found or inaccessible")
            if r.status_code!=200: raise HTTPException(502,"Could not access repository")
            repo=r.json()
        branch=x.branch.strip()
        if any(v in branch for v in (".."," ","~","^",":")): raise HTTPException(400,"Invalid branch name")
        ref=await c.get(f"{base}/repos/{full}/git/ref/heads/{branch}",headers=gh(t["token"]))
        if ref.status_code!=200: raise HTTPException(409,"Target branch does not exist or repository is empty. Initialize the branch on GitHub, then retry.")
        parent=ref.json()["object"]["sha"]
        cr=await c.get(f"{base}/repos/{full}/git/commits/{parent}",headers=gh(t["token"]))
        if cr.status_code!=200: raise HTTPException(502,"Could not read branch commit")
        tree=[]
        for path,content in files.items():
            b=await c.post(f"{base}/repos/{full}/git/blobs",headers=gh(t["token"]),json={"content":content,"encoding":"utf-8"})
            if b.status_code!=201: raise HTTPException(502,"Failed uploading "+path)
            tree.append({"path":path,"mode":"100644","type":"blob","sha":b.json()["sha"]})
        tr=await c.post(f"{base}/repos/{full}/git/trees",headers=gh(t["token"]),json={"base_tree":cr.json()["tree"]["sha"],"tree":tree})
        if tr.status_code!=201: raise HTTPException(502,"Could not create Git tree")
        cm=await c.post(f"{base}/repos/{full}/git/commits",headers=gh(t["token"]),json={"message":"Publish generated project with AI Project Builder","tree":tr.json()["sha"],"parents":[parent]})
        if cm.status_code!=201: raise HTTPException(502,"Could not create commit")
        up=await c.patch(f"{base}/repos/{full}/git/refs/heads/{branch}",headers=gh(t["token"]),json={"sha":cm.json()["sha"],"force":False})
        if up.status_code!=200: raise HTTPException(409,f"Branch update failed (HTTP {up.status_code}); publishing not confirmed")
    return {"success":True,"repository":full,"url":repo.get("html_url","https://github.com/"+full),"branch":branch,"commit":cm.json()["sha"],"files_published":len(files)}
