# SelfPDF

Aplikasi desktop (Tkinter) untuk menggabungkan beberapa PDF **secara visual** —
geser thumbnail halaman untuk mengurutkan ulang — sekaligus menjalankan **OCR
English** dan menyimpan hasilnya sebagai PDF yang bisa dicari, ditambah satu
bar menu berisi 26 perkakas PDF.

## Cara pakai

1. Klik **+ Tambah PDF** di baris atas — semua pekerjaan lewat tombol ini.
2. Berkas langsung **muncul di preview** (grid thumbnail di kiri).
3. Pilih perkakas dari **menubar**, isi parameternya, lalu klik **Jalankan**.

Tidak ada tombol "+Tambah" per tool, dan tidak ada daftar berkas terpisah di
dalam form. Satu preview, satu tombol, semua pekerjaan.

## Fitur inti

- **Gabung banyak PDF** — semua file dipecah jadi halaman, tampil sebagai grid thumbnail.
- **Reorder visual** — seret thumbnail ke posisi mana pun; urutan langsung berubah
  dan menjadi urutan halaman di PDF hasil.
- **OCR English** — per halaman (klik ganda / klik kanan) atau semua halaman sekaligus.
- **Teks tak terlihat** — hasil OCR disisipkan sebagai lapisan teks di atas gambar,
  jadi PDF hasil tetap tampilan aslinya tapi bisa dicari & disalin.
- **Pratinjau & cari teks** — panel samping menampilkan teks per halaman, ditambah
  pencarian di seluruh hasil OCR.
- **Putar, duplikat, hapus** halaman (halaman dengan badge hijau sudah punya teks OCR).
- **Tiga mode simpan**: *Searchable* (teks tak terlihat), *Image-only* (rata), *Original*.

## Perkakas PDF

Semua tool hidup di **satu panel in-window**, bukan dialog terpisah:

- Jendela berdua kolom: **grid thumbnail** di kiri, **panel** di kanan.
- **Tidak ada tab "Halaman / Perkakas" dan tidak ada daftar tool.** Panel kanan
  menampilkan **satu isi saja**: saat aplikasi dibuka berisi halaman + OCR,
  dan berubah jadi form parameter begitu satu perkakas diklik di menubar.
  Memilih halaman di grid mengembalikannya ke tampilan halaman.
- Menubar tetap jadi satu-satunya cara memilih perkakas. Tidak ada `Toplevel`,
  tidak ada `grab_set()`, jadi dialog pilih berkas tidak pernah tertutup di
  belakang jendela.
- Tidak ada tombol atau input yang muncul dua kali — misalnya tombol OCR hanya
  ada di baris di atas grid, tidak lagi diulang di panel samping.

### Satu sumber berkas

Berkas masuk hanya lewat **satu tombol Tambah** di header, dan langsung tampil
di preview. Tidak ada tombol "+Tambah" di tiap form tool, dan tidak ada daftar
input terpisah per tool.

- Label tombol menyesuaikan jenis file yang dibutuhkan tool aktif:
  `+ Tambah PDF`, `+ Tambah Gambar`, `+ Tambah Office`, `+ Tambah Berkas`.
- PDF dan gambar muncul sebagai thumbnail; badge `[PDF]` / `[Gambar]` menandai jenisnya.
- Office dan HTML tidak bisa dirender jadi thumbnail, jadi nama berkasnya
  ditampilkan sebagai daftar di atas preview sampai tool dijalankan.
- Parameter dan berkas yang dipilih disimpan **per tool**, jadi berpindah tool
  tidak menghapus isian yang sudah diisi.
- Hasil — sukses, peringatan, maupun error — ditulis inline di kotak hasil pada
  panel yang sedang tampil, lengkap dengan tombol **Buka Folder Hasil**. Tidak
  ada popup hasil.
- Proses jalan di thread terpisah; tombol dan input terkunci selama berjalan
  dan selalu kembali normal setelah selesai.

Satu-satunya dialog yang tersisa adalah pemilih berkas/folder dari sistem,
yang memang harus berupa dialog.

| Kategori | Tool |
|---|---|
| File | Tambah Berkas, Gabung & Simpan, Kosongkan Proyek, Keluar |
| Edit | Putar, Duplikat, Hapus, OCR semua / terpilih |
| Organize PDF | Split PDF, Extract Pages, Remove Pages, Scan to PDF |
| Optimize PDF | Compress PDF, Repair PDF |
| Convert To PDF | JPG to PDF, WORD/POWERPOINT/EXCEL to PDF, HTML to PDF |
| Convert From PDF | PDF to JPG, PDF to WORD, PDF to POWERPOINT, PDF to EXCEL, PDF to PDF/A |
| Edit PDF | Add Page Numbers, Add Watermark, Crop PDF, Edit PDF, PDF Forms |
| PDF Security | Unlock, Protect, Sign, Redact, Compare |
| PDF Intelligence | PDF to Markdown |

> Menubar memuat seluruh 30 tool, termasuk Merge, Organize, Remove Pages, OCR,
> dan Rotate. Yang punya pintasan di grid atau menubar tetap punya pintasan.

Rentang halaman ditulis seperti `1-3, 5, 8-`; mengosongkan berarti semua halaman.

### Catatan hasil konversi

- **PDF → POWERPOINT** memakai satu gambar penuh per slide, jadi teksnya
  **tidak bisa diedit**.
- **PDF → WORD** memakai `pdf2docx`, **PDF → EXCEL** memakai `pdfplumber`.
  Tata letak yang rumit sering perlu diperiksa manual.
- **Sign PDF** punya dua mode: *gambar* (cap visual) dan *sertifikat digital*
  (butuh berkas `.pfx`/`.p12` dan field signature yang sudah ada di PDF).
- **PDF → PDF/A** memakai Ghostscript dan menyertakan profil warna sRGB.

## Persyaratan

| Kebutuhan | Paket |
|---|---|
| GUI Tkinter | `sudo apt install python3-tk` |
| Mesin OCR | `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd` |
| Kompresi & PDF/A | `sudo apt install ghostscript icc-profiles-free` |
| Konversi Office | `sudo apt install libreoffice` |
| Library Python | `pip install -r requirements.txt` |

Tool yang butuh Ghostscript atau LibreOffice akan memberi pesan jelas bila
programnya belum ada; tool lain tetap berfungsi.

## Menjalankan

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Kalau `tesseract` belum terpasang, aplikasi tetap jalan — catatan peringatan
menampilkan perintah instalasinya, dan semua fitur selain OCR tetap berfungsi.

### Ekstensi OCR Rust (eksperimental, tidak dipakai aplikasi)

Ekstensi ini **tidak dipakai aplikasi ini** dan sudah dipindahkan keluar dari
repo ke `~/Downloads/selfpdf_ocr/`. Seluruh OCR pada GUI memakai Tesseract
(`pdfocr/ocr.py`), jadi semua fitur tetap berjalan tanpa folder tersebut.

Eksperimen ini memakai `ocrs`. Perlu Rust/Cargo, virtual environment,
`maturin`, dan dua model `ocrs` format `.rten`; model tidak disertakan.
Setelah pindah ke luar repo, aktifkan dulu virtual environment tujuan, lalu:

```bash
cd ~/Downloads/selfpdf_ocr
curl -fL https://ocrs-models.s3-accelerate.amazonaws.com/text-detection.rten \
  -o text-detection.rten
curl -fL https://ocrs-models.s3-accelerate.amazonaws.com/text-recognition.rten \
  -o text-recognition.rten
pip install 'maturin>=1.7,<2'
maturin develop --release
```

Contoh pemakaian setelah dibangun:

```python
from selfpdf_ocr import OcrEngine

engine = OcrEngine("text-detection.rten", "text-recognition.rten")
result = engine.ocr_file("scan.png")
print(result.text)
```

`ocr_bytes(bytes)` menerima data gambar PNG/JPEG, sementara
`ocr_batch(list[str])` menjalankan OCR pada beberapa file secara berurutan.
Kesalahan model, file, dan format gambar dilaporkan sebagai exception Python.

Keterbatasan yang membuatnya belum bisa menggantikan Tesseract: `OcrResult`
hanya mengembalikan teks, tanpa koordinat tiap kata. Fitur inti aplikasi ini
(searchable PDF, `search_text`, badge OCR) membutuhkan posisi kata, jadi
penggunaannya memerlukan `get_text_with_locations` dari `ocrs` yang belum
di-bind.

## Cara pakai

1. **+ Tambah PDF** — pilih satu atau beberapa file. Halaman dari semua file
   digabung jadi satu daftar.
2. **Susun urutan** — seret thumbnail ke posisi yang diinginkan.
   Klik kanan untuk menu cepat. Shift-klik untuk memilih beberapa halaman.
3. **OCR** — `OCR Semua` untuk seluruh dokumen, atau `OCR Halaman Terpilih`
   untuk halaman yang ditandai saja. Klik ganda satu thumbnail untuk OCR
   halaman itu.
4. **Perkakas** — pakai menubar di atas untuk tool PDF lain.
5. **Gabung & Simpan** — pilih mode simpan dan nama file.

## Cara kerja lapisan teks OCR

Tesseract mengembalikan posisi setiap kata dalam piksel. Aplikasi memetakan
posisi itu kembali ke satuan PDF (`px × 72 / dpi`) lalu menuliskannya sebagai
teks dengan `render_mode=3` (tak terlihat). Orientasi rotasi diterapkan
*setelah* teks disisipkan, supaya teks ikut terputar bersama halamannya.

Karena teksnya tak terlihat, dokumen asli tidak berubah tampilan — tapi
pencarian dan selection teks di Acrobat/editor PDF bekerja seperti biasa.

## Struktur

```
main.py                 entry point
assets/                 logo & ikon (opsional, lihat assets/README.md)
  logo.png              logo header
  icon.png              ikon jendela/taskbar
pdfocr/
  core.py               Project: urutan halaman, merge, lapisan teks OCR
  ocr.py                pembungkus Tesseract
  tools/                perkakas PDF
    base.py             ToolSpec, Param, ToolOutcome, run_spec
    organize.py         split, remove, extract, scan
    optimize.py         compress, repair, OCR
    to_pdf.py           gambar/Office/HTML -> PDF
    from_pdf.py         PDF -> gambar/Word/PPT/Excel/PDF-A
    edit.py             nomor halaman, watermark, crop, anotasi, formulir
    security.py         unlock, protect, sign, redact, compare
    intel.py            PDF -> Markdown
  gui/
    app.py              jendela utama, 2 kolom (grid + panel samping)
    header.py           baris identitas + tombol aksi utama
    menubar.py          bar menu in-window (hindari flicker X11)
    app_colors.py       palet warna bersama
    branding.py         nama aplikasi + pemuat wordmark/logo dari assets/
    page_grid.py        grid thumbnail + drag-reorder
    thumbs.py           cache thumbnail
    tool_panel.py       isi panel saat perkakas dipilih: form, progres, hasil
    feedback.py         kotak hasil inline + buka folder
tests/
  test_core.py          tes logika inti (tanpa GUI)
  test_tools.py         tes seluruh perkakas PDF
  test_gui.py           smoke test GUI (butuh display)
```

## Logo

Semua aset opsional — tanpa satu pun, aplikasi tetap jalan dan hanya menampilkan
teks nama. Yang dikenali, urut dari prioritas tertinggi:

| Berkas | Dipakai sebagai |
|---|---|
| `LogoSelfPDFull.jpeg` (atau `.png`) | wordmark lebar: lambang + nama sekaligus |
| `logo.png` | lambang bujur sangkar, dipakai bersama teks nama |
| `icon.png` | ikon jendela |

Kalau wordmark ditemukan, teks nama disembunyikan supaya nama tidak tampil dua
kali. Pencarian berkas tidak membedakan huruf besar-kecil. Lihat
`assets/README.md` untuk daftar nama yang dikenali.

## Tes

```bash
.venv/bin/python -m pytest tests/ -q
xvfb-run -a .venv/bin/python tests/test_gui.py
```