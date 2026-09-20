# MiniCut Studio + AI Agent

Versi ini memasukkan arsitektur agent langsung ke MiniCut Studio.

## Yang ditambahkan
- Panel **AI Agent** di dalam aplikasi.
- Mode **Lokal (tanpa API)** untuk perintah umum seperti `bagi jadi 8 part`, `tiap 10 menit`, dan `tambah cut di 00:10:00`.
- Mode **OpenAI-compatible** untuk model lokal atau API yang menyediakan endpoint `/v1/chat/completions`.
- **Tool Registry deterministik**. Agent tidak mengubah timeline secara bebas; semua perubahan melewati tool yang tervalidasi.
- Preview rencana JSON sebelum `Terapkan`.
- Checkpoint / **Undo Agent**.
- Local bridge `127.0.0.1:8765` untuk agent eksternal.
- Companion **MiniCut MCP.exe** yang mengekspos tool MiniCut ke host MCP melalui stdio.

## Tool agent
`get_state`, `seek`, `play`, `pause`, `add_cut`, `remove_cut`, `clear_cuts`, `divide_equal`, `divide_interval`, `save_project`, `export_all`, `undo`.

## Prinsip local-first
Video tidak dikirim ke bridge atau MCP. Bridge hanya mengirim status proyek/timestamp/cut dan menerima operasi tool. Mode Lokal tidak membutuhkan API sama sekali. Mode OpenAI-compatible hanya mengirim state teks proyek + instruksi pengguna untuk menghasilkan rencana JSON.

## MCP
1. Jalankan **MiniCut Studio Agent.exe** dan biarkan `Bridge lokal` aktif.
2. Konfigurasikan host MCP untuk menjalankan **MiniCut MCP.exe** sebagai server stdio.
3. MCP server meneruskan tool ke aplikasi melalui `127.0.0.1:8765`.

## Build
Gunakan Windows + Python 3.11. FFmpeg dan ffprobe dibutuhkan pada PATH.
