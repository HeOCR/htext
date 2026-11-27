"""Pre-render v2-p4 page images into the editions driver's cache in parallel: one sha1-checked PDF download per IA
item (hard-linked to every pair path), one `pdfimages -p` call per page range; pages with more or fewer than one
image fall back to the driver's own renderer. Atomic writes. Usage: prerender.py MANIFEST WORK JOBS"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.expanduser("~/agents/environments/opensource/projects/heocr/agent_worktrees/htext-v2p3/src"))
from htext.linepairs.editions import safe_id
from htext.linepairs import wikisource as W
MAN, WORK, JOBS = sys.argv[1], sys.argv[2], int(sys.argv[3]); UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
pairs = json.load(open(MAN))["pairs"]
def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def pdf_for(pair):
    url, want = pair["scan"]["url"], pair["scan"]["sha1"]
    shared = os.path.join(WORK, "pdf_shared", want + ".pdf"); os.makedirs(os.path.dirname(shared), exist_ok=True)
    if not (os.path.exists(shared) and sha1(shared) == want):
        tmp = shared + ".part"
        subprocess.run(["curl", "-sSfL", "-A", UA, "-o", tmp, url], check=True)
        if sha1(tmp) != want: raise SystemExit(f"{url}: sha1 mismatch")
        os.replace(tmp, shared)
    dest = os.path.join(WORK, "scans", f"{safe_id(pair['id'])}.pdf"); os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not os.path.exists(dest): os.link(shared, dest)
    return dest
def render(pair):
    sid = safe_id(pair["id"]); outd = os.path.join(WORK, "pilot", "pages", sid); os.makedirs(outd, exist_ok=True)
    pages = pair["scope"]["pdf_ordinals"]; todo = [n for n in pages if not os.path.exists(os.path.join(outd, f"p{n:04d}.png"))]
    if not todo: return pair["id"], 0
    pdf = pdf_for(pair); lo, hi = min(todo), max(todo)
    lst = subprocess.run(["pdfimages", "-list", "-f", str(lo), "-l", str(hi), pdf], capture_output=True, text=True).stdout.splitlines()[2:]
    per = {}
    for l in lst:
        f = l.split()
        if len(f) >= 14 and f[2] == "image": per[int(f[0])] = per.get(int(f[0]), 0) + 1
    with tempfile.TemporaryDirectory(dir=outd) as td:
        subprocess.run(["pdfimages", "-png", "-p", "-f", str(lo), "-l", str(hi), pdf, f"{td}/x"], check=True, capture_output=True)
        got = {}
        for f in os.listdir(td):
            m = re.match(r"x-(\d+)-(\d+)\.png$", f)
            if m: got.setdefault(int(m.group(1)), []).append(f)
        n_done = 0
        for n in todo:
            dst = os.path.join(outd, f"p{n:04d}.png")
            if per.get(n) == 1 and len(got.get(n, [])) == 1:
                os.replace(os.path.join(td, got[n][0]), dst + ".tmp"); os.replace(dst + ".tmp", dst); n_done += 1
            else:
                W.page_image(__import__("pathlib").Path(pdf), n, __import__("pathlib").Path(dst))
                n_done += 1
    return pair["id"], n_done
if __name__ == "__main__":
    with ProcessPoolExecutor(JOBS) as ex:
        for pid, n in ex.map(render, pairs):
            print(pid, n, flush=True)
    print("PRERENDER_DONE")
