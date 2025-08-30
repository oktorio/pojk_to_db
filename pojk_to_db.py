#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POJK/SEOJK PDF → JSON/SQLite converter (with Penjelasan stopper)

Usage:
  python pojk_to_db.py --pdf POJK_12_2021.pdf --type POJK \
    --number "12/POJK.03/2021" --title "Peraturan OJK tentang X" \
    --year 2021 --effective-date 2021-12-31 --outdir out --build-db

Deps (install one):
  pip install pymupdf          # preferred
  # or
  pip install pdfminer.six     # fallback
"""

import argparse, json, os, re, sqlite3, sys

# ---------- Text extraction ----------
def extract_text_from_pdf(path: str) -> str:
    # Try PyMuPDF first
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return "\n".join(page.get_text("text") for page in doc)
    except Exception as e:
        sys.stderr.write(f"[i] PyMuPDF failed ({e}); trying pdfminer...\n")
    # Fallback: pdfminer.six
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path)
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")

# ---------- Normalisation ----------
def normalize_text(raw: str) -> str:
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    # drop lines that are only page numbers
    s = re.sub(r"(?m)^\s*\d+\s*$", "", s)
    # fix hyphenation across line breaks: "infor-\nmasi" -> "informasi"
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    # collapse >2 blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s

# ---------- Split Pasal & Ayat ----------
PASAL_RE = re.compile(r"(?im)^\s*Pasal\s+(\d+)\s*$")
AYAT_RE  = re.compile(r"(?m)^\s*\((\d+[a-z]?)\)\s*")
PENJELASAN_RE = re.compile(r"(?im)^\s*Penjelasan\b.*$", re.MULTILINE)

def split_into_pasal_blocks(text: str):
    """
    Returns list of tuples: [(pasal_number:int, content:str), ...]
    Stops scanning when:
      - a second "Pasal 1" appears (typical start of Penjelasan), OR
      - a clear "Penjelasan" heading is encountered.
    """
    # If "Penjelasan" appears, ignore everything after its first occurrence
    m_pen = PENJELASAN_RE.search(text)
    if m_pen:
        text = text[:m_pen.start()]

    indices = [(m.start(), m.end(), int(m.group(1))) for m in PASAL_RE.finditer(text)]
    if not indices:
        # No explicit Pasal headings; treat all as single block
        return [(1, text.strip())] if text.strip() else []

    blocks = []
    seen_pasal1 = False
    for i, (start, end, pasal_num) in enumerate(indices):
        # stop if "Pasal 1" appears again after we've already processed the first one
        if pasal_num == 1 and seen_pasal1:
            break
        if pasal_num == 1:
            seen_pasal1 = True

        nxt = indices[i+1][0] if i+1 < len(indices) else len(text)
        content = text[end:nxt].strip()
        if content:
            blocks.append((pasal_num, content))
    return blocks

def split_pasal_into_ayat(pasal_content: str):
    ayat_matches = list(AYAT_RE.finditer(pasal_content))
    if not ayat_matches:
        content = pasal_content.strip()
        return [(None, content)] if content else []
    parts = []
    for i, m in enumerate(ayat_matches):
        start = m.end()
        end = ayat_matches[i+1].start() if i+1 < len(ayat_matches) else len(pasal_content)
        label = m.group(1).strip()
        chunk = pasal_content[start:end].strip()
        if chunk:
            parts.append((label, chunk))
    return parts

# ---------- Build records ----------
def build_records(reg_meta, text: str):
    text = normalize_text(text)
    pasal_blocks = split_into_pasal_blocks(text)
    regulations = [reg_meta]
    articles, next_id = [], 1
    for pasal_num, pasal_content in pasal_blocks:
        for ayat_label, ayat_text in split_pasal_into_ayat(pasal_content):
            articles.append({
                "id": next_id,
                "regulation_id": reg_meta["id"],
                "pasal": pasal_num,
                "ayat": ayat_label,
                "text": ayat_text
            })
            next_id += 1
    return regulations, articles

# ---------- Schema ----------
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE regulations(
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  number_text TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER NOT NULL,
  effective_date TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  replaces_number TEXT,
  amended_by_number TEXT,
  revoked_by_number TEXT,
  source_url TEXT,
  pdf_path TEXT
);

CREATE TABLE articles(
  id INTEGER PRIMARY KEY,
  regulation_id INTEGER NOT NULL,
  pasal INTEGER NOT NULL,
  ayat TEXT,
  text TEXT NOT NULL
);

CREATE VIRTUAL TABLE articles_fts USING fts5(
  text, content='articles', content_rowid='id', tokenize='unicode61'
);

CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO articles_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

def build_db(path, regulations, articles):
    if os.path.exists(path):
        os.remove(path)
    cx = sqlite3.connect(path)
    cx.executescript(SCHEMA_SQL)
    cx.executemany("""INSERT INTO regulations VALUES
        (:id,:type,:number_text,:title,:year,:effective_date,:status,
         :replaces_number,:amended_by_number,:revoked_by_number,:source_url,:pdf_path)""", regulations)
    cx.executemany("""INSERT INTO articles VALUES
        (:id,:regulation_id,:pasal,:ayat,:text)""", articles)
    cx.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild');")
    cx.commit(); cx.close()

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Convert POJK/SEOJK PDF into JSON and optional SQLite DB; ignores Penjelasan")
    ap.add_argument("--pdf", required=True, help="Path to PDF")
    ap.add_argument("--type", required=True, choices=["POJK","SEOJK"])
    ap.add_argument("--number", required=True, help='e.g. "12/POJK.03/2021"')
    ap.add_argument("--title", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--id", type=int, default=1)
    ap.add_argument("--effective-date")
    ap.add_argument("--status", default="active")
    ap.add_argument("--source-url")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--build-db", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    text = extract_text_from_pdf(args.pdf)

    reg_meta = {
        "id": args.id,
        "type": args.type,
        "number_text": args.number,
        "title": args.title,
        "year": args.year,
        "effective_date": args.effective_date,
        "status": args.status,
        "replaces_number": None,
        "amended_by_number": None,
        "revoked_by_number": None,
        "source_url": args.source_url,
        "pdf_path": os.path.basename(args.pdf)
    }

    regs, arts = build_records(reg_meta, text)

    regs_path = os.path.join(args.outdir, "regulations.json")
    arts_path = os.path.join(args.outdir, "articles.json")
    with open(regs_path, "w", encoding="utf-8") as f:
        json.dump(regs, f, ensure_ascii=False, indent=2)
    with open(arts_path, "w", encoding="utf-8") as f:
        json.dump(arts, f, ensure_ascii=False, indent=2)

    print(f"[✓] Wrote {regs_path} (1 item)")
    print(f"[✓] Wrote {arts_path} ({len(arts)} items)")

    if args.build_db:
        db_path = os.path.join(args.outdir, "ojk.db")
        build_db(db_path, regs, arts)
        print(f"[✓] Built SQLite database: {db_path}")

if __name__ == "__main__":
    main()
