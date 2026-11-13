"""Deterministic brand-review engine.

Every finding is grounded in an approved source (a guideline rule or an approved
fact) and carries: the rule id, the quoted source passage, the flagged span,
a plain-language reason, a suggested fix and a confidence value.

Nothing here edits content. A fix is only a *suggestion* that a human accepts.
Claims and fact conflicts are marked `needs_human` so a reviewer must sign off.
"""
from __future__ import annotations

import datetime as dt
import io
import re

CATEGORY_LABELS = {
    "terminology": "Terminology", "tone": "Tone", "claims": "Claims", "facts": "Facts",
    "messaging": "Messaging", "accessibility": "Accessibility", "visual": "Visual",
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


# ----------------------------------------------------------------- helpers
def _match_case(src: str, repl: str) -> str:
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper() and repl[:1].islower():
        return repl[:1].upper() + repl[1:]
    return repl


def sentences(body: str):
    out, pos = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+|\n+", body):
        seg = body[pos:m.start()]
        if seg.strip():
            s = pos + (len(seg) - len(seg.lstrip()))
            out.append((s, pos + len(seg.rstrip())))
        pos = m.end()
    seg = body[pos:]
    if seg.strip():
        s = pos + (len(seg) - len(seg.lstrip()))
        out.append((s, pos + len(seg.rstrip())))
    return out


def hex_to_rgb(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _is_neutral(rgb, tol=18):
    return max(rgb) - min(rgb) <= tol


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _nearest(rgb, palette):
    best = None
    for p in palette:
        prgb = hex_to_rgb(p["hex"])
        if prgb is None:
            continue
        d = _dist(rgb, prgb)
        if best is None or d < best[0]:
            best = (d, p)
    return best


class _Ctx:
    def __init__(self, body, lib, today):
        self.body, self.lib, self.today = body, lib, today
        self.out = []

    def add(self, rule, start, end, why, suggestion, fix=None, confidence=0.95, needs_human=False,
            category=None, rule_id=None, title=None, quote=None, severity=None, scope="text", text=None):
        t = text if text is not None else (self.body[start:end] if start is not None else "")
        self.out.append(dict(
            rule_id=rule_id or rule["id"], category=category or rule["category"],
            severity=severity or rule["severity"], rule_title=title or rule["title"],
            source_quote=quote or rule["text"], start=start, end=end, text=t, why=why,
            suggestion=suggestion, fix=fix, confidence=confidence, needs_human=needs_human, scope=scope,
            fingerprint=f"{rule_id or rule['id']}|{t.lower().strip()}",
        ))


def _word_re(words, case_sensitive=False):
    alts = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(r"(?<![\w/@.\-])(?:" + alts + r")(?![\w]|\.\w)", 0 if case_sensitive else re.I)


# ------------------------------------------------------------------ checks
def _term(ctx, rule):
    cfg = rule["config"]
    rx = _word_re(cfg["banned"], cfg.get("case_sensitive", False))
    mp = {k.lower(): v for k, v in cfg.get("map", {}).items()}
    for m in rx.finditer(ctx.body):
        s = m.group(0)
        if s == cfg.get("preferred"):
            continue
        repl = mp.get(s.lower())
        fix = {"op": "replace", "start": m.start(), "end": m.end(), "text": _match_case(s, repl)} if repl else None
        ctx.add(rule, m.start(), m.end(),
                f"“{s}” is not approved terminology. Use “{cfg.get('preferred')}” instead.",
                f"Replace “{s}” with “{_match_case(s, repl) if repl else cfg.get('preferred')}”.", fix, 0.97)


def _pattern(ctx, rule):
    cfg = rule["config"]
    rx = re.compile(cfg["pattern"], re.I)
    mp = {k.lower(): v for k, v in cfg.get("map", {}).items()}
    for m in rx.finditer(ctx.body):
        s = m.group(0)
        repl = mp.get(s.lower())
        fix = {"op": "replace", "start": m.start(), "end": m.end(), "text": _match_case(s, repl)} if repl else None
        sug = f"Replace with “{_match_case(s, repl)}”." if repl else cfg.get("suggestion", "Reword this phrase.")
        ctx.add(rule, m.start(), m.end(), f"“{s}” goes against this guideline.", sug, fix, 0.9 if repl else 0.85)


def _exclaim(ctx, rule):
    mx = rule["config"].get("max", 1)
    marks = [m.start() for m in re.finditer(r"!(?!\[)", ctx.body)]
    for i, pos in enumerate(marks):
        if i >= mx:
            ctx.add(rule, pos, pos + 1,
                    f"This is exclamation mark number {i + 1}; the guideline allows {mx}.",
                    "Use a full stop instead.", {"op": "replace", "start": pos, "end": pos + 1, "text": "."}, 0.98)


def _caps(ctx, rule):
    allowed = {a.upper() for a in ctx.lib["settings"].get("allowed_caps", [])}
    for m in re.finditer(r"(?<![\w])[A-Z]{4,}(?![\w])", ctx.body):
        w = m.group(0)
        if w in allowed:
            continue
        ctx.add(rule, m.start(), m.end(), f"“{w}” is written in capitals, which reads as shouting.",
                f"Write “{w.capitalize()}”.", {"op": "replace", "start": m.start(), "end": m.end(), "text": w.capitalize()}, 0.9)


SUPERLATIVE = (r"(?<![\w#])(?:best|#1|no\.? ?1|number one|leading|world'?s (?:first|best|leading)|revolutionary|"
               r"unmatched|unbeatable|perfect|flawless|ultimate|top[- ]rated|highly rated|well[- ]rated|award[- ]winning)(?![\w])")
SUPER_MAP = {"best": "great", "#1": "popular", "no. 1": "popular", "no 1": "popular", "number one": "popular",
             "leading": "established", "revolutionary": "new", "unmatched": "distinctive",
             "unbeatable": "great-value", "perfect": "well-suited", "flawless": "reliable", "ultimate": "complete"}
ABSOLUTE = (r"(?<![\w])(?:guarantee[ds]?|100\s?%|always|never fails?|risk[- ]free|zero (?:risk|defects)|"
            r"clinically proven|scientifically proven|proven to)(?![\w%])")
ABS_MAP = {"always": "typically"}
HEALTH = (r"\b(?:cures?|cured|heals?|therapeutic|treats? (?:insomnia|depression|anxiety|migraines?|headaches?)|"
          r"prevents? (?:disease|illness|migraines?|myopia|headaches?)|improves? sleep|reduces? (?:anxiety|stress|eye strain))\b")


def _claim(ctx, rule):
    mode = rule["config"]["mode"]
    rx = re.compile({"superlative": SUPERLATIVE, "absolute": ABSOLUTE, "health": HEALTH}[mode], re.I)
    supported = [p.lower() for f in ctx.lib["facts"] for p in f.get("supports", [])]
    for m in rx.finditer(ctx.body):
        s = m.group(0)
        if mode == "superlative" and s.lower() in supported:
            continue
        mp = SUPER_MAP if mode == "superlative" else ABS_MAP if mode == "absolute" else {}
        repl = mp.get(re.sub(r"\s+", " ", s.lower()))
        fix = {"op": "replace", "start": m.start(), "end": m.end(), "text": _match_case(s, repl)} if repl else None
        if mode == "health":
            sug = "Remove the health claim. Describe what the product does (e.g. adjustable warm light) without medical outcomes."
        elif repl:
            sug = f"No approved fact supports “{s}”. Safer wording: “{_match_case(s, repl)}”, or ask Legal to add an approved fact."
        else:
            sug = f"No approved fact supports “{s}”. Remove it, or ask Legal to add approved wording to the Facts library."
        ctx.add(rule, m.start(), m.end(), f"“{s}” is a claim with no approved source behind it.", sug, fix,
                0.75, needs_human=True)


def _competitor(ctx, rule):
    rx = _word_re(rule["config"]["names"], True)
    for m in rx.finditer(ctx.body):
        ctx.add(rule, m.start(), m.end(), f"“{m.group(0)}” is a competitor name.",
                "Remove the comparison and describe Lumora's own benefit instead.", None, 0.9, needs_human=True)


def _require(ctx, rule):
    cfg = rule["config"]
    m = re.search(cfg["trigger"], ctx.body, re.I)
    if m and cfg["required"].lower() not in ctx.body.lower():
        sep = "" if ctx.body.endswith("\n") or not ctx.body else "\n\n"
        ctx.add(rule, m.start(), m.end(),
                f"This content mentions a promotion (“{m.group(0)}”) but does not include “{cfg['required']}”.",
                f"Add “{cfg['append']}” at the end.", {"op": "append", "text": sep + cfg["append"]}, 0.96)


def _link(ctx, rule):
    bad = {b.lower() for b in rule["config"]["bad"]}
    used = []
    for rx, grp in ((re.compile(r"(?<!!)\[([^\]]*)\]\([^)]*\)"), 1), (re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S), 1)):
        for m in rx.finditer(ctx.body):
            if m.group(grp).strip().lower() in bad:
                used.append((m.start(), m.end()))
                ctx.add(rule, m.start(grp), m.end(grp), f"The link text “{m.group(grp).strip()}” does not say where the link goes.",
                        "Describe the destination, e.g. “View the Lumora Hub setup guide”.", None, 0.92)
    for m in re.finditer(r"\b(click here|read more)\b", ctx.body, re.I):
        if any(a <= m.start() < b for a, b in used):
            continue
        ctx.add(rule, m.start(), m.end(), f"“{m.group(0)}” is a vague call to action for screen-reader users.",
                "Describe the destination instead.", None, 0.8)


def _alt(ctx, rule):
    for m in re.finditer(r"!\[([^\]]*)\]\([^)]*\)", ctx.body):
        if not m.group(1).strip():
            ctx.add(rule, m.start(), m.end(), "This image has no alt text.",
                    "Add a short description of what the image shows.", None, 0.98)
    for m in re.finditer(r"<img\b[^>]*>", ctx.body, re.I):
        am = re.search(r"\balt\s*=\s*([\"'])(.*?)\1", m.group(0), re.I | re.S)
        if not am or not am.group(2).strip():
            ctx.add(rule, m.start(), m.end(), "This image tag has no alt text.",
                    "Add alt=\"…\" describing the image.", None, 0.98)


def _longsentence(ctx, rule):
    mx = rule["config"].get("max_words", 30)
    for s, e in sentences(ctx.body):
        n = len(re.findall(r"\S+", ctx.body[s:e]))
        if n > mx:
            ctx.add(rule, s, e, f"This sentence has {n} words (limit {mx}).",
                    "Split it into two shorter sentences.", None, 0.9)


def _contrast(ctx, rule, meta):
    fg, bg = hex_to_rgb(meta.get("fg") or ""), hex_to_rgb(meta.get("bg") or "")
    if not fg or not bg:
        return
    ratio = contrast_ratio(fg, bg)
    if ratio >= rule["config"].get("min", 4.5):
        return
    best = None
    pal = ctx.lib["settings"]["palette"]
    for a in pal:
        for b in pal:
            ra, rb = hex_to_rgb(a["hex"]), hex_to_rgb(b["hex"])
            r = contrast_ratio(ra, rb)
            if r >= 7 and (best is None or r > best[0]):
                best = (r, a, b)
    sug = "Choose a darker text colour or lighter background."
    if best:
        sug = f"Try {best[1]['name']} ({best[1]['hex']}) text on {best[2]['name']} ({best[2]['hex']}): contrast {best[0]:.1f}:1."
    ctx.add(rule, None, None, f"Text {meta['fg']} on {meta['bg']} has contrast {ratio:.2f}:1, below 4.5:1.",
            sug, None, 0.99, scope="design", text=f"{meta['fg']} on {meta['bg']}")


def _palette(ctx, rule, meta):
    pal = ctx.lib["settings"]["palette"]
    tol = rule["config"].get("tolerance", 60)
    for label, key in (("Text", "fg"), ("Background", "bg")):
        rgb = hex_to_rgb(meta.get(key) or "")
        if not rgb or _is_neutral(rgb):
            continue
        d, p = _nearest(rgb, pal)
        if d > tol:
            ctx.add(rule, None, None, f"{label} colour {meta[key]} is not in the approved palette.",
                    f"Nearest approved colour: {p['name']} ({p['hex']}).", None, 0.9, scope="design", text=meta[key])


def _facts(ctx):
    num = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

    def kind(tok): return "pct" if tok.endswith("%") else "usd" if tok.startswith("$") else "num"
    def val(tok): return tok.replace("$", "").replace(",", "").rstrip("%")

    for f in ctx.lib["facts"]:
        kws = [k.lower() for k in f["keywords"]]
        approved = num.findall(f["statement"])
        expired = bool(f.get("valid_until")) and dt.date.fromisoformat(f["valid_until"]) < ctx.today
        quote = f"{f['statement']} (Source: {f.get('source') or 'approved fact'}; owner: {f.get('owner') or 'n/a'})"
        for s, e in sentences(ctx.body):
            sent = ctx.body[s:e]
            low = sent.lower()
            if not all(re.search(r"\b" + re.escape(k), low) for k in kws):
                continue
            title = "Does not match approved fact"
            if expired:
                ctx.add(None, s, e, f"This refers to information that expired on {f['valid_until']}.",
                        "Remove or update this sentence, or ask the fact owner for the current offer.", None, 0.85,
                        needs_human=True, category="facts", rule_id=f["id"], title="Outdated information",
                        quote=quote, severity="high")
                continue
            for m in num.finditer(sent):
                tok = m.group(0)
                same = [a for a in approved if kind(a) == kind(tok)]
                if not same or any(val(a) == val(tok) for a in same):
                    continue
                # ignore plain numbers that are probably part of a different statement
                fix = None
                if len(same) == 1:
                    fix = {"op": "replace", "start": s + m.start(), "end": s + m.end(), "text": same[0]}
                sug = f"Approved value is {same[0]}." if len(same) == 1 else f"Approved statement: “{f['statement']}”"
                ctx.add(None, s + m.start(), s + m.end(),
                        f"“{tok}” does not match the approved fact.", sug, fix, 0.8, needs_human=True,
                        category="facts", rule_id=f["id"], title=title, quote=quote, severity="high")


# -------------------------------------------------------------------- API
DISPATCH = {"term": _term, "pattern": _pattern, "exclaim": _exclaim, "caps": _caps, "claim": _claim,
            "competitor": _competitor, "require": _require, "link": _link, "alt": _alt, "longsentence": _longsentence}


def review(body: str, lib: dict, meta: dict | None = None, today: dt.date | None = None) -> list[dict]:
    meta = meta or {}
    ctx = _Ctx(body, lib, today or dt.date.today())
    for rule in lib["rules"]:
        if not rule.get("active", 1):
            continue
        k = rule["kind"]
        if k in DISPATCH:
            DISPATCH[k](ctx, rule)
        elif k == "contrast":
            _contrast(ctx, rule, meta)
        elif k == "palette":
            _palette(ctx, rule, meta)
    _facts(ctx)
    ctx.out.sort(key=lambda f: (f["start"] if f["start"] is not None else 10 ** 9, SEV_ORDER[f["severity"]]))
    return ctx.out


def analyze_image(data: bytes, alt_text: str, lib: dict) -> list[dict]:
    """Checks an uploaded image: alt text, dominant colours vs approved palette, resolution."""
    from PIL import Image
    ctx = _Ctx("", lib, dt.date.today())
    rules = {r["id"]: r for r in lib["rules"]}
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if "BG-5.2" in rules and not (alt_text or "").strip():
        ctx.add(rules["BG-5.2"], None, None, "No alt text was provided for this image.",
                "Describe what the image shows in one sentence.", None, 0.98, scope="design", text="(missing alt text)")
    if "BG-6.1" in rules:
        small = img.resize((96, 96))
        q = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[:18]
        total = 96 * 96
        for count, idx in sorted(q.getcolors(), reverse=True):
            rgb = tuple(pal[idx * 3: idx * 3 + 3])
            share = count / total
            if share < 0.12 or _is_neutral(rgb):
                continue
            d, p = _nearest(rgb, lib["settings"]["palette"])
            if d > rules["BG-6.1"]["config"].get("tolerance", 60):
                hx = "#%02X%02X%02X" % rgb
                ctx.add(rules["BG-6.1"], None, None,
                        f"{hx} covers about {share:.0%} of the image and is not in the approved palette.",
                        f"Nearest approved colour: {p['name']} ({p['hex']}).", None, 0.8, scope="design", text=hx)
    if img.width < 800:
        ctx.add(rules.get("BG-6.1", {"id": "BG-6.1", "category": "visual", "severity": "low", "title": "Image quality", "text": ""}),
                None, None, f"The image is only {img.width}px wide and may look blurry when published.",
                "Use an image at least 800px wide.", None, 0.9, severity="low", scope="design",
                text=f"{img.width}x{img.height}px", rule_id="BG-6.2", title="Minimum image resolution",
                quote="Images used in public channels must be at least 800px wide.")
    return ctx.out
