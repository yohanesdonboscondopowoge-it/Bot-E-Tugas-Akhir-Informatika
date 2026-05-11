from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import sys
import time

app = Flask(__name__)

# Load config
try:
    from config import NIM, PASSWORD
except ImportError:
    print("ERROR: config.py tidak ditemukan!")
    sys.exit(1)

try:
    from config import E_OFFICE_COOKIE_FALLBACK
except ImportError:
    E_OFFICE_COOKIE_FALLBACK = ""

# ============================================
# KONFIGURASI
# ============================================
BASE_PDDIKTI = "https://api-pddikti.kemdiktisaintek.go.id"
BASE_FOTO = "https://ais.unmul.ac.id/file/foto"
BASE_E_OFFICE = "https://e-office.ft.unmul.ac.id"
NAMA_PT = "UNIVERSITAS MULAWARMAN"
HEADERS_PDDIKTI = {"Origin": "https://pddikti.kemdiktisaintek.go.id"}

E_OFFICE_COOKIE = ""

# ============================================
# AUTO-LOGIN
# ============================================
def login_e_office():
    global E_OFFICE_COOKIE
    
    if E_OFFICE_COOKIE_FALLBACK and len(E_OFFICE_COOKIE_FALLBACK) > 50:
        E_OFFICE_COOKIE = E_OFFICE_COOKIE_FALLBACK
        print("📋 Menggunakan cookie manual dari config.py")
        return True
    
    print("🔐 Mencoba login ke e-Office...")
    
    session = requests.Session()
    
    get_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    }
    
    login_page_url = f"{BASE_E_OFFICE}/e-ta"
    resp = session.get(login_page_url, headers=get_headers)
    print(f"  GET /e-ta → {resp.status_code}")
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    token = None
    for inp in soup.find_all('input', {'type': 'hidden'}):
        if 'token' in inp.get('name', '').lower():
            token = inp.get('value')
            break
    
    if token:
        print(f"  ✅ Token: {token[:30]}...")
    
    login_data = {
        "_token": token,
        "user_id": NIM,
        "password": PASSWORD,
        "role": "Mahasiswa",
    }
    
    post_headers = {
        **get_headers,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE_E_OFFICE,
        "Referer": login_page_url,
    }
    
    resp = session.post(
        f"{BASE_E_OFFICE}/user/proses_login_eta",
        data=login_data,
        headers=post_headers,
        allow_redirects=False,
        timeout=10
    )
    
    print(f"  POST login → {resp.status_code}")
    
    if resp.status_code in [301, 302, 303, 307, 308]:
        redirect_url = resp.headers.get('Location', '')
        print(f"  Redirect: {redirect_url}")
        
        while redirect_url:
            full_url = BASE_E_OFFICE + redirect_url if redirect_url.startswith('/') else redirect_url
            resp2 = session.get(full_url, headers=get_headers, allow_redirects=False, timeout=10)
            print(f"  → {resp2.status_code} | {resp2.url}")
            
            if resp2.status_code in [301, 302, 303, 307, 308]:
                redirect_url = resp2.headers.get('Location', '')
            else:
                break
    
    cookies = session.cookies.get_dict()
    E_OFFICE_COOKIE = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    
    jadwal_url = f"{BASE_E_OFFICE}/mahasiswa/e-ta/lihat_jadwal_skripsi"
    resp3 = session.get(jadwal_url, headers={**get_headers, "Cookie": E_OFFICE_COOKIE}, timeout=10)
    
    if "events:" in resp3.text:
        print(f"  ✅ Berhasil! ({len(resp3.text)} chars)")
        return True
    else:
        print(f"  ❌ Gagal. HTML: {len(resp3.text)} chars")
        return False

# ============================================
# PENCARIAN MAHASISWA
# ============================================
def cari_mahasiswa(query):
    url = f"{BASE_PDDIKTI}/pencarian/mhs/{query}"
    resp = requests.get(url, headers=HEADERS_PDDIKTI, timeout=30)
    resp.raise_for_status()
    semua = resp.json() or []
    hasil = [m for m in semua if m.get("nama_pt") == NAMA_PT]
    if query.isdigit():
        hasil = [m for m in hasil if m.get("nim") == query]
    return hasil

def ekstrak_angkatan(nim):
    if nim and len(nim) >= 2:
        try:
            return str(2000 + int(nim[:2]))
        except:
            return "-"
    return "-"

def cek_foto(nim):
    try:
        r = requests.head(f"{BASE_FOTO}/{nim}", timeout=10)
        return r.status_code == 200
    except:
        return False

# ============================================
# JADWAL
# ============================================
def ambil_jadwal():
    url = f"{BASE_E_OFFICE}/mahasiswa/e-ta/lihat_jadwal_skripsi"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": E_OFFICE_COOKIE
    }
    resp = requests.get(url, headers=headers)
    html = resp.text
    
    if "events:" not in html:
        return []
    
    idx = html.find("events:")
    snippet = html[idx:idx+50000]
    
    jadwal_list = []
    event_blocks = re.findall(r"\{([^}]*title:[^}]*start:[^}]*)\}", snippet)
    
    for block in event_blocks:
        title_match = re.search(r"title:\s*'([^']*)'", block)
        start_match = re.search(r"start:\s*'([^']*)'", block)
        end_match = re.search(r"end:\s*'([^']*)'", block)
        url_match = re.search(r"url:\s*'([^']*)'", block)
        
        if title_match and start_match:
            start = start_match.group(1)
            if start.strip() == "-":
                continue
             
            bg_match = re.search(r'backgroundColor:\s*"([^"]*)"', block)
            warna = bg_match.group(1) if bg_match else ""
            
            
            jenis = "Seminar"
            if warna == "#609450" or warna == "#609450":
                jenis = "Seminar Proposal"
            elif warna == "#4a8bc2" or warna == "#4a8bc2":
                jenis = "Seminar Hasil"
            elif warna == "#bd362f" or warna == "#bd362f":
                jenis = "Pendadaran"
            jadwal_list.append({
                "nama": title_match.group(1),
                "mulai": start,
                "selesai": end_match.group(1) if end_match else start,
                "link": BASE_E_OFFICE + url_match.group(1) if url_match else "",
                "judul": "-",
                "nim": "",
                "url_foto": "",
                "ada_foto": False,
                "jenis": jenis 
            })
    
    return jadwal_list

def cari_nim_dari_nama(nama_lengkap):
    """Cari NIM dari nama mahasiswa di PDDikti"""
    nama_bersih = re.sub(r'\s*[-–]\s*(D\d+|ZOOM\d*|belum)\s*$', '', nama_lengkap, flags=re.IGNORECASE).strip()
    
    try:
        hasil = cari_mahasiswa(nama_bersih)
        if hasil and len(hasil) > 0:
            return hasil[0].get("nim", ""), hasil[0].get("nama", nama_lengkap)
        
        parts = nama_bersih.split()
        if len(parts) >= 2:
            nama_pendek = f"{parts[0]} {parts[-1]}"
            hasil = cari_mahasiswa(nama_pendek)
            if hasil and len(hasil) > 0:
                return hasil[0].get("nim", ""), hasil[0].get("nama", nama_lengkap)
    except:
        pass
    
    return "", nama_lengkap

def ambil_detail_skripsi(url_path, nama_dari_jadwal=""):
    """Ambil judul, NIM, dan nama dari halaman detail skripsi"""
    full_url = BASE_E_OFFICE + url_path if url_path.startswith('/') else url_path
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": E_OFFICE_COOKIE
    }
    
    result = {"judul": "-", "nim": "", "nama": nama_dari_jadwal}
    
    try:
        resp = requests.get(full_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 1. Ambil judul
        for strong in soup.find_all('strong'):
            if 'judul' in strong.text.lower():
                h3 = strong.find('h3')
                if not h3:
                    h3 = strong.find_next('h3')
                if h3 and len(h3.text.strip()) > 10:
                    result["judul"] = h3.text.strip()[:300]
                    break
        
        # 2. Ambil NIM dari lead_paragraphs[1]
        lead_paragraphs = soup.find_all('p', class_='lead')
        if len(lead_paragraphs) >= 2:
            text = lead_paragraphs[1].text.strip()
            if re.match(r'^\d{8,12}$', text):
                result["nim"] = text
        
        # 3. Fallback ke PDDikti
        if not result["nim"] and nama_dari_jadwal:
            nim_fallback, _ = cari_nim_dari_nama(nama_dari_jadwal)
            if nim_fallback:
                result["nim"] = nim_fallback
        
                # DEBUG: Cek apakah halaman login atau halaman detail
        if "E-ROOM" in resp.text or "Akun AIS" in resp.text:
            print(f"  {nama_dari_jadwal[:30]}... → HALAMAN LOGIN! Cookie expired!")
        else:
            lead_paragraphs = soup.find_all('p', class_='lead')
            print(f"  {nama_dari_jadwal[:30]}... → lead_paragraphs: {[p.text.strip()[:50] for p in lead_paragraphs]}")
            print(f"  NIM ditemukan: {result['nim']}")
        
        return result
    except:
        return result

# ============================================
# ENDPOINT
# ============================================
@app.route('/cari')
def cari():
    q = request.args.get('query', '')
    if not q:
        return jsonify({"error": "Query kosong"}), 400
    try:
        hasil = cari_mahasiswa(q)
        for m in hasil:
            nim = m.get("nim", "")
            m["angkatan"] = ekstrak_angkatan(nim)
            m["ada_foto"] = cek_foto(nim)
            m["url_foto"] = f"{BASE_FOTO}/{nim}" if m.get("ada_foto") else ""
        return jsonify(hasil)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/jadwal')
def jadwal():
    data = ambil_jadwal()
    
    for i, item in enumerate(data[:10]):
        if item.get('link'):
            url_path = item['link'].replace(BASE_E_OFFICE, '')
            detail = ambil_detail_skripsi(url_path, item.get('nama', ''))
            
            item['judul'] = detail['judul']
            item['nim'] = detail['nim']
            
            if item['nim']:
                item['url_foto'] = f"{BASE_FOTO}/{item['nim']}"
                item['ada_foto'] = cek_foto(item['nim'])
            else:
                item['url_foto'] = ""
                item['ada_foto'] = False
            
            if i < len(data[:5]) - 1:
                time.sleep(0.5)
    
    return jsonify(data)

@app.route('/health')
def health():
    return jsonify({"status": "ok", "cookie": len(E_OFFICE_COOKIE) > 0})

@app.route('/debug-warna')
def debug_warna():
    """Debug: lihat warna dari 5 event pertama"""
    url = f"{BASE_E_OFFICE}/mahasiswa/e-ta/lihat_jadwal_skripsi"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": E_OFFICE_COOKIE
    }
    resp = requests.get(url, headers=headers)
    html = resp.text
    
    idx = html.find("events:")
    snippet = html[idx:idx+50000]
    
    event_blocks = re.findall(r"\{([^}]*title:[^}]*start:[^}]*)\}", snippet)
    
    result = []
    for block in event_blocks[:5]:
        title_match = re.search(r"title:\s*'([^']*)'", block)
        bg_match = re.search(r"backgroundColor:\s*\"([^\"]*)\"", block)
        bg_match2 = re.search(r"backgroundColor:\s*'([^']*)'", block)
        
        result.append({
            "title": title_match.group(1) if title_match else "?",
            "bg_double_quote": bg_match.group(1) if bg_match else "NOT FOUND",
            "bg_single_quote": bg_match2.group(1) if bg_match2 else "NOT FOUND",
            "block_snippet": block[:300]
        })
    
    return jsonify(result)

# ============================================
# JALANKAN
# ============================================
if __name__ == '__main__':
    print("=" * 50)
    print("🔧 API Server Bot Unmul")
    print("=" * 50)
    login_e_office()
    app.run(host='127.0.0.1', port=5000, debug=False)