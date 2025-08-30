# 📘 OJK Regulation Viewer (POJK/SEOJK)

An offline app to **search and read POJK/SEOJK** with precise citation (*Pasal* / *Ayat*).  
 **Python converter** to transform official PDFs into a compact, searchable **`ojk.db`** database.

## 🛠️ Building the Database from a PDF

### 1) Install dependencies
```bash
pip install pymupdf   # recommended
# or
pip install pdfminer.six
```

### 2) Run the converter
```bash
python tools/pojk_to_db.py   --pdf "POJK_12_2021.pdf"   --type POJK   --number "12/POJK.03/2021"   --title "Peraturan OJK tentang X"   --year 2021   --build-db   --outdir build/seed
```

### 3) Outputs
- `build/seed/regulations.json`  
- `build/seed/articles.json`  
- `build/seed/ojk.db` ← copy this into `app/src/main/assets/seed/`  

> 📝 The script automatically **ignores Penjelasan** (anything after a second *Pasal 1* or explicit “Penjelasan” header).

---

## 🔄 Updating Regulations
- Rerun converter for new POJK/SEOJK → replace `ojk.db`  
- Future roadmap: in-app updater via GitHub Releases or Firebase  

---

## 🗺️ Roadmap
- [ ] Detail screen with Pasal/Ayat navigator  
- [ ] Filters (type/year/status)  
- [ ] PDF viewer button (PdfRenderer)  
- [ ] Bookmarks & notes  
- [ ] Amendment links (“Amended by SEOJK …”)  
- [ ] Updater for new regs  

---

## 🤝 Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and PRs welcome!  

---

## 📜 License
[MIT](LICENSE)  
