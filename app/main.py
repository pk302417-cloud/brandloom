import io
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS = os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "uploads")

app = FastAPI(title="BrandLoom", version="0.2.0")


@app.on_event("startup")
def _startup():
    db.init()
    os.makedirs(UPLOADS, exist_ok=True)
    if os.environ.get("SEED_DEMO", "1") == "1":
        from .demo import seed_demo
        seed_demo()


# ---------------------------------------------------------------- auth
def current_user(x_user: Optional[str] = Header(None)):
    with db.conn() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (x_user or "",)).fetchone()
    if not u:
        raise HTTPException(401, "Choose a user first (X-User header).")
    return dict(u)


def need_role(user, *roles):
    if user["role"] not in roles:
        raise HTTPException(403, f"This action needs one of these roles: {', '.join(roles)}.")


def log(c, content_id, actor, action, detail=""):
    c.execute("INSERT INTO audit(content_id,actor,action,detail) VALUES(?,?,?,?)", (content_id, actor, action, detail))


# ---------------------------------------------------------- review core
def run_review(c, content_id: int, revision_id: int, body: str):
    """Runs the engine on a revision, stores findings, carries over earlier dismissals."""
    ct = c.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
    lib = db.load_library(c)
    found = engine.review(body, lib, {"fg": ct["fg"], "bg": ct["bg"]})
    if ct["image_path"]:
        with open(ct["image_path"], "rb") as fh:
            found += engine.analyze_image(fh.read(), ct["alt_text"] or "", lib)
    carried = {}
    for r in c.execute("SELECT fingerprint, reason, resolved_by FROM findings WHERE content_id=? AND state='dismissed'", (content_id,)):
        carried[r["fingerprint"]] = (r["reason"], r["resolved_by"])
    c.execute("UPDATE findings SET state='superseded' WHERE content_id=? AND state='open'", (content_id,))
    for f in found:
        st, reason, by = "open", None, None
        if f["fingerprint"] in carried:
            st, (reason, by) = "dismissed", carried[f["fingerprint"]]
        c.execute("""INSERT INTO findings(content_id,revision_id,rule_id,category,severity,rule_title,source_quote,start,"end",
                     text,why,suggestion,fix,confidence,needs_human,scope,fingerprint,state,reason,resolved_by)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (content_id, revision_id, f["rule_id"], f["category"], f["severity"], f["rule_title"], f["source_quote"],
                   f["start"], f["end"], f["text"], f["why"], f["suggestion"], json.dumps(f["fix"]), f["confidence"],
                   int(f["needs_human"]), f["scope"], f["fingerprint"], st, reason, by))
    return len(found)


def new_revision(c, content_id: int, body: str, note: str, author_id: str):
    n = c.execute("SELECT COALESCE(MAX(n),0)+1 FROM revisions WHERE content_id=?", (content_id,)).fetchone()[0]
    cur = c.execute("INSERT INTO revisions(content_id,n,body,note,author_id) VALUES(?,?,?,?,?)",
                    (content_id, n, body, note, author_id))
    c.execute("UPDATE content SET updated_at=datetime('now') WHERE id=?", (content_id,))
    return cur.lastrowid, n


def current_rev(c, content_id):
    return c.execute("SELECT * FROM revisions WHERE content_id=? ORDER BY n DESC LIMIT 1", (content_id,)).fetchone()


def get_content(c, cid):
    ct = c.execute("SELECT * FROM content WHERE id=?", (cid,)).fetchone()
    if not ct:
        raise HTTPException(404, "Content not found.")
    return ct


def editable(ct):
    if ct["status"] not in ("draft", "changes_requested"):
        raise HTTPException(409, f"Content is '{ct['status']}' and cannot be edited now.")


def can_edit(user, ct):
    return user["id"] == ct["author_id"] or user["role"] == "manager"


def need_edit(user, ct):
    if not can_edit(user, ct):
        raise HTTPException(403, "Only the author or a manager can change this content.")
    editable(ct)


def blockers_and_flags(c, cid):
    rows = c.execute("SELECT * FROM findings WHERE content_id=? AND state!='superseded' "
                     "AND revision_id=(SELECT MAX(id) FROM revisions WHERE content_id=?)", (cid, cid)).fetchall()
    open_high = [r for r in rows if r["state"] == "open" and r["severity"] == "high"]
    open_other = [r for r in rows if r["state"] == "open" and r["severity"] != "high"]
    needs_reviewer = [r for r in rows if r["needs_human"] and r["state"] != "accepted"]
    return open_high, open_other, needs_reviewer


# ------------------------------------------------------------- models
class NewContent(BaseModel):
    title: str
    kind: str = "post"
    channel: str = ""
    body: str
    fg: str = ""
    bg: str = ""


class BodyEdit(BaseModel):
    body: str
    note: str = "Edited by author"


class MetaEdit(BaseModel):
    fg: str = ""
    bg: str = ""


class Accept(BaseModel):
    replacement: Optional[str] = None


class Dismiss(BaseModel):
    reason: str


class Decision(BaseModel):
    decision: str
    comment: str = ""


class Comment(BaseModel):
    body: str


# --------------------------------------------------------------- users
@app.get("/api/users")
def users():
    with db.conn() as c:
        return [dict(u) for u in c.execute("SELECT * FROM users")]


# ------------------------------------------------------------- library
def _lib_json(c):
    lib = db.load_library(c)
    return lib


@app.get("/api/library")
def library(user=Depends(current_user)):
    with db.conn() as c:
        return _lib_json(c)


class RuleIn(BaseModel):
    category: str
    title: str
    text: str
    severity: str = "medium"
    kind: str
    config: dict


@app.post("/api/library/rules")
def add_rule(r: RuleIn, user=Depends(current_user)):
    need_role(user, "manager")
    if r.kind not in ("term", "pattern", "require", "competitor"):
        raise HTTPException(400, "Custom rules can be of kind term, pattern, require or competitor.")
    if r.severity not in ("high", "medium", "low"):
        raise HTTPException(400, "Severity must be high, medium or low.")
    try:  # validate regexes early
        for key in ("pattern", "trigger"):
            if key in r.config:
                re.compile(r.config[key])
    except re.error as e:
        raise HTTPException(400, f"Invalid pattern: {e}")
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM rules WHERE id LIKE 'BG-9.%'").fetchone()[0] + 1
        rid = f"BG-9.{n}"
        c.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,1)",
                  (rid, r.category, r.title, r.text, r.severity, r.kind, json.dumps(r.config)))
    return {"id": rid}


@app.patch("/api/library/rules/{rid}")
def toggle_rule(rid: str, active: bool, user=Depends(current_user)):
    need_role(user, "manager")
    with db.conn() as c:
        c.execute("UPDATE rules SET active=? WHERE id=?", (int(active), rid))
    return {"ok": True}


@app.delete("/api/library/rules/{rid}")
def del_rule(rid: str, user=Depends(current_user)):
    need_role(user, "manager")
    if not rid.startswith("BG-9."):
        raise HTTPException(400, "Built-in guideline rules can be switched off but not deleted.")
    with db.conn() as c:
        c.execute("DELETE FROM rules WHERE id=?", (rid,))
    return {"ok": True}


class FactIn(BaseModel):
    statement: str
    keywords: list[str]
    valid_until: Optional[str] = None
    supports: list[str] = []
    owner: str = ""
    source: str = ""


@app.post("/api/library/facts")
def add_fact(f: FactIn, user=Depends(current_user)):
    need_role(user, "manager", "reviewer")
    if not f.keywords:
        raise HTTPException(400, "Add at least one keyword so the fact can be matched.")
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0] + 1
        while c.execute("SELECT 1 FROM facts WHERE id=?", (f"F-{n}",)).fetchone():
            n += 1
        c.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?)",
                  (f"F-{n}", f.statement, json.dumps([k.lower() for k in f.keywords]), f.valid_until or None,
                   json.dumps(f.supports), f.owner, f.source))
    return {"id": f"F-{n}"}


@app.delete("/api/library/facts/{fid}")
def del_fact(fid: str, user=Depends(current_user)):
    need_role(user, "manager", "reviewer")
    with db.conn() as c:
        c.execute("DELETE FROM facts WHERE id=?", (fid,))
    return {"ok": True}


class BrandIn(BaseModel):
    palette: list[dict]
    allowed_caps: list[str]


@app.put("/api/library/brand")
def put_brand(b: BrandIn, user=Depends(current_user)):
    need_role(user, "manager")
    for p in b.palette:
        if engine.hex_to_rgb(p.get("hex", "")) is None:
            raise HTTPException(400, f"“{p.get('hex')}” is not a valid hex colour.")
    with db.conn() as c:
        brand = db.load_library(c)["settings"]
        brand["palette"], brand["allowed_caps"] = b.palette, [x.upper() for x in b.allowed_caps]
        c.execute("UPDATE settings SET value=? WHERE key='brand'", (json.dumps(brand),))
    return {"ok": True}


# ------------------------------------------------------------- content
def create_content(c, user_id, title, kind, channel, body, fg="", bg="", image_path=None, alt_text=None):
    cur = c.execute("INSERT INTO content(title,kind,channel,author_id,status,fg,bg,image_path,alt_text) VALUES(?,?,?,?,?,?,?,?,?)",
                    (title, kind, channel, user_id, "draft", fg, bg, image_path, alt_text))
    cid = cur.lastrowid
    rid, _ = new_revision(c, cid, body, "Initial submission", user_id)
    n = run_review(c, cid, rid, body)
    log(c, cid, user_id, "submitted_for_check", f"{n} findings")
    return cid


@app.post("/api/content")
def post_content(b: NewContent, user=Depends(current_user)):
    if not b.title.strip() or not b.body.strip():
        raise HTTPException(400, "Title and content text are required.")
    if len(b.body) > 50000:
        raise HTTPException(400, "Content is too long (50,000 characters max).")
    for col in (b.fg, b.bg):
        if col and engine.hex_to_rgb(col) is None:
            raise HTTPException(400, f"“{col}” is not a valid hex colour such as #14213D.")
    with db.conn() as c:
        cid = create_content(c, user["id"], b.title.strip(), b.kind, b.channel, b.body, b.fg, b.bg)
    return {"id": cid}


@app.post("/api/content/image")
async def post_image(title: str = Form(...), alt_text: str = Form(""), channel: str = Form(""),
                     file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image is larger than 8 MB.")
    try:
        from PIL import Image
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(400, "This file is not a valid image (PNG, JPG or WebP).")
    path = os.path.join(UPLOADS, uuid.uuid4().hex + ".img")
    with open(path, "wb") as fh:
        fh.write(data)
    with db.conn() as c:
        cid = create_content(c, user["id"], title.strip() or "Untitled image", "image", channel, alt_text,
                             image_path=path, alt_text=alt_text)
    return {"id": cid}


@app.get("/api/content/{cid}/image")
def get_image(cid: int, user=Depends(current_user)):
    with db.conn() as c:
        ct = get_content(c, cid)
    if not ct["image_path"]:
        raise HTTPException(404, "No image.")
    return FileResponse(ct["image_path"])


@app.post("/api/extract")
async def extract(file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read()
    name = (file.filename or "").lower()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "File is larger than 8 MB.")
    try:
        if name.endswith(".docx"):
            import docx
            text = "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        elif name.endswith((".txt", ".md", ".html", ".htm")):
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(400, "Supported files: .txt, .md, .html, .docx, .pdf")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this file. Try pasting the text instead.")
    if not text.strip():
        raise HTTPException(400, "No text was found in this file (scanned PDFs are not supported yet).")
    return {"text": text[:50000], "filename": file.filename}


@app.get("/api/content")
def list_content(status: str = "", user=Depends(current_user)):
    with db.conn() as c:
        q = ("SELECT ct.*, u.name AS author_name, "
             "(SELECT COUNT(*) FROM findings f WHERE f.content_id=ct.id AND f.state='open' AND f.revision_id="
             "(SELECT MAX(id) FROM revisions WHERE content_id=ct.id)) AS open_findings, "
             "(SELECT MAX(n) FROM revisions WHERE content_id=ct.id) AS revisions "
             "FROM content ct JOIN users u ON u.id=ct.author_id")
        args = []
        if status:
            q += " WHERE ct.status=?"
            args.append(status)
        q += " ORDER BY ct.updated_at DESC, ct.id DESC"
        return [dict(r) for r in c.execute(q, args)]


@app.get("/api/content/{cid}")
def content_detail(cid: int, user=Depends(current_user)):
    with db.conn() as c:
        ct = get_content(c, cid)
        rev = current_rev(c, cid)
        findings = []
        for f in c.execute("SELECT * FROM findings WHERE revision_id=? ORDER BY CASE WHEN start IS NULL THEN 1 ELSE 0 END, start, id", (rev["id"],)):
            d = dict(f)
            d["fix"] = json.loads(d["fix"]) if d["fix"] else None
            findings.append(d)
        revisions = [dict(r) for r in c.execute(
            "SELECT r.id,r.n,r.body,r.note,r.created_at,u.name AS author FROM revisions r JOIN users u ON u.id=r.author_id "
            "WHERE content_id=? ORDER BY n", (cid,))]
        comments = [dict(r) for r in c.execute(
            "SELECT m.id,m.body,m.created_at,u.name AS author,u.role FROM comments m JOIN users u ON u.id=m.author_id "
            "WHERE content_id=? ORDER BY m.id", (cid,))]
        audit = [dict(r) for r in c.execute(
            "SELECT a.action,a.detail,a.created_at,COALESCE(u.name,a.actor) AS actor FROM audit a LEFT JOIN users u ON u.id=a.actor "
            "WHERE content_id=? ORDER BY a.id", (cid,))]
        author = c.execute("SELECT name FROM users WHERE id=?", (ct["author_id"],)).fetchone()["name"]
        open_high, open_other, needs_reviewer = blockers_and_flags(c, cid)
    d = dict(ct)
    d["author_name"] = author
    d.pop("image_path", None)
    d["has_image"] = bool(ct["image_path"])
    in_review = ct["status"] == "in_review"
    perms = {
        "can_edit": can_edit(user, ct) and ct["status"] in ("draft", "changes_requested"),
        "can_submit": can_edit(user, ct) and ct["status"] in ("draft", "changes_requested") and not open_high,
        "can_decide": in_review and user["role"] in ("manager", "reviewer") and user["id"] != ct["author_id"],
        "requires_reviewer": bool(needs_reviewer),
        "blockers": [f"{len(open_high)} high-severity finding(s) must be accepted or dismissed with a reason"] if open_high else [],
        "warnings": [f"{len(open_other)} lower-severity finding(s) are still open"] if open_other else [],
    }
    if in_review and perms["requires_reviewer"] and user["role"] != "reviewer":
        perms["can_decide"] = False
        perms["decide_note"] = "This content contains claim or fact findings, so a Compliance Reviewer must make the decision."
    return {"content": d, "revision": dict(rev), "findings": findings, "revisions": revisions,
            "comments": comments, "audit": audit, "perms": perms}


@app.put("/api/content/{cid}/body")
def edit_body(cid: int, b: BodyEdit, user=Depends(current_user)):
    if not b.body.strip():
        raise HTTPException(400, "Content cannot be empty.")
    with db.conn() as c:
        ct = get_content(c, cid)
        need_edit(user, ct)
        cur = current_rev(c, cid)
        if cur["body"] == b.body:
            return {"revision": cur["n"], "unchanged": True}
        if ct["image_path"]:
            c.execute("UPDATE content SET alt_text=? WHERE id=?", (b.body, cid))
        rid, n = new_revision(c, cid, b.body, b.note or "Edited by author", user["id"])
        cnt = run_review(c, cid, rid, b.body)
        log(c, cid, user["id"], "edited", f"revision {n}, {cnt} findings")
    return {"revision": n}


@app.put("/api/content/{cid}/meta")
def edit_meta(cid: int, m: MetaEdit, user=Depends(current_user)):
    for col in (m.fg, m.bg):
        if col and engine.hex_to_rgb(col) is None:
            raise HTTPException(400, f"“{col}” is not a valid hex colour such as #14213D.")
    with db.conn() as c:
        ct = get_content(c, cid)
        need_edit(user, ct)
        c.execute("UPDATE content SET fg=?, bg=? WHERE id=?", (m.fg, m.bg, cid))
        cur = current_rev(c, cid)
        rid, n = new_revision(c, cid, cur["body"], f"Design colours set to {m.fg or '–'} on {m.bg or '–'}", user["id"])
        run_review(c, cid, rid, cur["body"])
        log(c, cid, user["id"], "design_colours_changed", f"{m.fg} on {m.bg}")
    return {"revision": n}


@app.post("/api/content/{cid}/recheck")
def recheck(cid: int, user=Depends(current_user)):
    with db.conn() as c:
        ct = get_content(c, cid)
        need_edit(user, ct)
        cur = current_rev(c, cid)
        rid, n = new_revision(c, cid, cur["body"], "Re-checked against latest library", user["id"])
        run_review(c, cid, rid, cur["body"])
        log(c, cid, user["id"], "rechecked", f"revision {n}")
    return {"revision": n}


# ------------------------------------------------------------ findings
def get_finding(c, fid):
    f = c.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
    if not f:
        raise HTTPException(404, "Finding not found.")
    return f


@app.post("/api/findings/{fid}/accept")
def accept(fid: int, a: Accept, user=Depends(current_user)):
    with db.conn() as c:
        f = get_finding(c, fid)
        ct = get_content(c, f["content_id"])
        need_edit(user, ct)
        cur = current_rev(c, ct["id"])
        if f["revision_id"] != cur["id"] or f["state"] != "open":
            raise HTTPException(409, "This finding is out of date. Refresh the page.")
        fix = json.loads(f["fix"]) if f["fix"] else None
        body = cur["body"]
        if a.replacement is not None and f["start"] is not None:
            fix = {"op": "replace", "start": f["start"], "end": f["end"], "text": a.replacement}
        if not fix:
            raise HTTPException(400, "This finding has no automatic fix. Edit the text yourself or dismiss it with a reason.")
        if fix["op"] == "replace":
            if body[fix["start"]:fix["end"]] != f["text"]:
                raise HTTPException(409, "The text changed since this finding was created. Re-check the content.")
            body = body[:fix["start"]] + fix["text"] + body[fix["end"]:]
        else:
            body = body.rstrip() + fix["text"] if fix["text"].startswith("\n") else body + fix["text"]
        c.execute("UPDATE findings SET state='accepted', resolved_by=?, resolved_at=datetime('now') WHERE id=?", (user["id"], fid))
        if ct["image_path"]:
            c.execute("UPDATE content SET alt_text=? WHERE id=?", (body, ct["id"]))
        rid, n = new_revision(c, ct["id"], body, f"Accepted suggestion for {f['rule_id']}", user["id"])
        run_review(c, ct["id"], rid, body)
        log(c, ct["id"], user["id"], "accepted_suggestion", f"{f['rule_id']}: “{f['text']}” → “{fix['text']}”")
    return {"revision": n}


@app.post("/api/findings/{fid}/dismiss")
def dismiss(fid: int, d: Dismiss, user=Depends(current_user)):
    if len(d.reason.strip()) < 5:
        raise HTTPException(400, "Please give a short reason (at least 5 characters) for dismissing this finding.")
    with db.conn() as c:
        f = get_finding(c, fid)
        ct = get_content(c, f["content_id"])
        need_edit(user, ct)
        if f["state"] != "open":
            raise HTTPException(409, "This finding is already resolved.")
        c.execute("UPDATE findings SET state='dismissed', reason=?, resolved_by=?, resolved_at=datetime('now') WHERE id=?",
                  (d.reason.strip(), user["id"], fid))
        log(c, ct["id"], user["id"], "dismissed_finding", f"{f['rule_id']}: {d.reason.strip()}")
    return {"ok": True}


# ------------------------------------------------------------ workflow
@app.post("/api/content/{cid}/submit")
def submit(cid: int, user=Depends(current_user)):
    with db.conn() as c:
        ct = get_content(c, cid)
        need_edit(user, ct)
        open_high, _, needs_reviewer = blockers_and_flags(c, cid)
        if open_high:
            raise HTTPException(409, f"{len(open_high)} high-severity finding(s) are still open. Accept the fix or dismiss with a reason first.")
        c.execute("UPDATE content SET status='in_review', updated_at=datetime('now') WHERE id=?", (cid,))
        log(c, cid, user["id"], "submitted_for_approval",
            "Compliance Reviewer required" if needs_reviewer else "Manager or Reviewer can approve")
    return {"status": "in_review"}


@app.post("/api/content/{cid}/decision")
def decision(cid: int, d: Decision, user=Depends(current_user)):
    need_role(user, "manager", "reviewer")
    if d.decision not in ("approve", "changes", "reject"):
        raise HTTPException(400, "Decision must be approve, changes or reject.")
    with db.conn() as c:
        ct = get_content(c, cid)
        if ct["status"] != "in_review":
            raise HTTPException(409, "Only content that is in review can be decided.")
        if user["id"] == ct["author_id"]:
            raise HTTPException(403, "You cannot approve your own content.")
        open_high, _, needs_reviewer = blockers_and_flags(c, cid)
        if d.decision == "approve":
            if open_high:
                raise HTTPException(409, "High-severity findings are still open.")
            if needs_reviewer and user["role"] != "reviewer":
                raise HTTPException(403, "Claim or fact findings were overridden or flagged, so a Compliance Reviewer must approve.")
        elif not d.comment.strip():
            raise HTTPException(400, "Please add a comment explaining what needs to change.")
        status = {"approve": "approved", "changes": "changes_requested", "reject": "rejected"}[d.decision]
        c.execute("UPDATE content SET status=?, updated_at=datetime('now') WHERE id=?", (status, cid))
        if d.comment.strip():
            c.execute("INSERT INTO comments(content_id,author_id,body) VALUES(?,?,?)", (cid, user["id"], d.comment.strip()))
        log(c, cid, user["id"], f"decision_{d.decision}", d.comment.strip())
    return {"status": status}


@app.post("/api/content/{cid}/comments")
def add_comment(cid: int, m: Comment, user=Depends(current_user)):
    if not m.body.strip():
        raise HTTPException(400, "Comment is empty.")
    with db.conn() as c:
        get_content(c, cid)
        c.execute("INSERT INTO comments(content_id,author_id,body) VALUES(?,?,?)", (cid, user["id"], m.body.strip()))
        log(c, cid, user["id"], "commented", m.body.strip()[:120])
    return {"ok": True}


# ------------------------------------------------------------ insights
@app.get("/api/insights")
def insights(user=Depends(current_user)):
    with db.conn() as c:
        total = c.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        by_status = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM content GROUP BY status")}
        first = c.execute("SELECT f.*, ct.author_id, u.name AS author FROM findings f JOIN revisions r ON r.id=f.revision_id "
                          "JOIN content ct ON ct.id=f.content_id JOIN users u ON u.id=ct.author_id WHERE r.n=1").fetchall()
        cats = Counter(f["category"] for f in first)
        rules = {}
        for f in first:
            rules.setdefault(f["rule_id"], {"rule_id": f["rule_id"], "title": f["rule_title"], "category": f["category"], "count": 0})
            rules[f["rule_id"]]["count"] += 1
        res = c.execute("SELECT rule_id, state, COUNT(*) n FROM findings WHERE resolved_at IS NOT NULL AND state IN ('accepted','dismissed') GROUP BY rule_id, state").fetchall()
        acc, dis = defaultdict(int), defaultdict(int)
        for r in res:
            (acc if r["state"] == "accepted" else dis)[r["rule_id"]] = r["n"]
        top = []
        for rid, r in rules.items():
            a, d = acc[rid], dis[rid]
            rate = d / (a + d) if (a + d) else None
            r.update(accepted=a, dismissed=d, dismissal_rate=rate, unclear=bool(rate is not None and a + d >= 3 and rate >= 0.4))
            top.append(r)
        top.sort(key=lambda r: -r["count"])
        by_author = defaultdict(lambda: {"pieces": set(), "rules": Counter(), "name": ""})
        for f in first:
            a = by_author[f["author_id"]]
            a["name"] = f["author"]
            a["pieces"].add(f["content_id"])
            a["rules"][(f["rule_id"], f["rule_title"])] += 1
        pieces_by_author = Counter(r["author_id"] for r in c.execute("SELECT author_id FROM content"))
        # a rule is "recurring" for an author if it appears in 2+ different pieces
        rec = []
        per_piece = defaultdict(set)
        for f in first:
            per_piece[(f["author_id"], f["rule_id"], f["rule_title"], f["author"])].add(f["content_id"])
        for (aid, rid, title, name), pieces in per_piece.items():
            if len(pieces) >= 2:
                rec.append({"author": name, "rule_id": rid, "title": title, "pieces": len(pieces)})
        rec.sort(key=lambda r: -r["pieces"])
        avg_first = (len(first) / total) if total else 0
        last = c.execute("SELECT COUNT(*) FROM findings f WHERE f.revision_id=(SELECT MAX(id) FROM revisions WHERE content_id=f.content_id) "
                         "AND f.state='open'").fetchone()[0]
        return {
            "total_content": total, "by_status": by_status, "total_findings_first_pass": len(first),
            "avg_findings_first_pass": round(avg_first, 1), "open_findings_now": last,
            "by_category": dict(cats), "top_rules": top[:12], "recurring": rec[:10],
            "unclear_rules": [r for r in top if r["unclear"]],
            "authors": [{"name": v["name"], "pieces": pieces_by_author[k], "findings": sum(v["rules"].values())} for k, v in by_author.items()],
        }


@app.get("/api/ai-disclosure")
def disclosure():
    return {
        "review_engine": "Rule-based (no AI model). All findings come from the approved library in this workspace.",
        "external_services": [],
        "data_sent_outside": "None. Content is processed and stored on this server only.",
        "note": "Planned for Round 3: optional LLM-assisted checks for tone and claims, with source-citation verification. They will be clearly labelled and can be switched off.",
    }


app.mount("/", StaticFiles(directory=os.path.join(ROOT, "static"), html=True), name="static")
