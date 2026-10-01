# Folder Aset — SelfPDF

Taruh berkas logo Anda di sini. Aplikasi otomatis memuatnya saat start, tanpa
perlu mengubah kode.

## Nama berkas yang dikenali

| Berkas | Kegunaan | Ukuran yang disarankan |
|---|---|---|
| `LogoSelfPDFull.jpeg` / `.png` | **Wordmark**: lambang + nama dalam satu gambar lebar | lebar ≥ 600 px, rasio lebar tinggi, latar putih atau transparan |
| `logo.png` | Lambang bujur sangkar di header, dipakai berdampingan dengan teks nama | lebar 120–320 px, tinggi 32–80 px, **latar transparan** |
| `icon.png` | Ikon jendela / taskbar | 64×64 px (atau kelipatan: 128, 256), latar transparan |
| `icon.ico` | Ikon jendela untuk Windows (opsional) | 16/32/64/256 |
| `logo.jpg` / `logo.webp` | Alternatif bila tidak pakai PNG | sama seperti `logo.png` |

Nama berkas dicari **tanpa membedakan huruf besar-kecil**, jadi
`logoselfpdfull.jpeg` juga dikenali.

## Prioritas

1. Kalau wordmark ditemukan, header memakainya dan **teks nama disembunyikan** —
   nama tidak akan tampil dua kali.
2. Kalau hanya `logo.png` yang ada, logo dan teks nama ditampilkan berdampingan
   pada satu sumbu vertikal.
3. Kalau tidak ada aset sama sekali, header hanya menampilkan teks nama.

Semua berkas opsional: tanpa satu pun, aplikasi tetap jalan normal.

## Yang dilakukan otomatis

- **Latar putih dihapus.** Gambar RGB berkolom putih diulu-ulu (mirip) otomatis
  dijadikan transparan, lalu diskalakan. Hasilnya tidak terlihat seperti kotak
  putih di header yang gelap.
- **Diskalakan turun** sesuai batas ukuran header, tidak memotong gambar.
- **Ditempel rata kiri** pada baris nama, bukan mengambang di tengah blok
  dua baris — ini yang membuat logo terlihat meleset dari tulisan nama.

## Tips

- Resolusi tinggi lebih aman. Aset besar tetap turun skala dengan rapi.
- Untuk `icon.png`, pilih desain yang masih terbaca di 16 px (tebal, kontras
  tinggi, tanpa teks kecil).
- Untuk wordmark, pakai kontras jelas antara lambang dan latar; artwork gelap
  di atas header gelap akan menghilang.
- Setelah mengganti berkas, jalankan ulang aplikasi.
