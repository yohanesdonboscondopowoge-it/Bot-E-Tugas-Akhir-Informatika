const { makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

const API_URL = 'http://127.0.0.1:5000';

async function cariMahasiswa(query) {
    try {
        const response = await axios.get(`${API_URL}/cari`, { params: { query } });
        return response.data;
    } catch (error) {
        return { error: 'Gagal' };
    }
}

async function ambilJadwal() {
    try {
        const response = await axios.get(`${API_URL}/jadwal`);
        return response.data;
    } catch (error) {
        return { error: 'Gagal mengambil jadwal' };
    }
}

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_session');

    const sock = makeWASocket({
        auth: state,
        browser: ['Bot Unmul', 'Chrome', '1.0.0'],
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            console.log('📱 Scan QR:');
            qrcode.generate(qr, { small: false });
        }
        if (connection === 'close') {
            const reason = lastDisconnect?.error?.output?.statusCode;
            if (reason !== DisconnectReason.loggedOut) {
                setTimeout(() => startBot(), 5000);
            }
        } else if (connection === 'open') {
            console.log('✅ Bot terhubung!');
        }
    });

    sock.ev.on('messages.upsert', async (m) => {
        const message = m.messages[0];
        if (!message.key.fromMe && m.type === 'notify') {
            const from = message.key.remoteJid;
            const text = message.message?.conversation ||
                message.message?.extendedTextMessage?.text || '';
            const trimmedText = text.trim();

            // ==========================================
            // FITUR !help
            // ==========================================
            if (trimmedText === '!help') {
                const helpText =
                    '*BOT UNMUL FT*\n\n' +
                    '*Perintah:*\n' +
                    '  `!cari <NIM/Nama>` — Cari data mahasiswa\n' +
                    '  `!jadwal` — Jadwal seminar TA terbaru\n' +
                    '  `!help` — Tampilkan bantuan ini\n\n' +
                    '*Contoh:*\n' +
                    '  `!cari 2209......`\n' +
                    '  `!cari yohanes`\n' +
                    '  `!jadwal`';
                await sock.sendMessage(from, { text: helpText });
            }

            // ==========================================
            // FITUR !cari
            // ==========================================
            if (trimmedText.startsWith('!cari')) {
                const query = trimmedText.substring(5).trim();
                if (!query) return;

                await sock.sendMessage(from, { text: `🔎 Mencari '${query}'...` });

                try {
                    const hasil = await cariMahasiswa(query);

                    if (!hasil || hasil.length === 0 || hasil.error) {
                        await sock.sendMessage(from, { text: 'Mahasiswa Unmul tidak ditemukan.' });
                        return;
                    }

                    for (let i = 0; i < Math.min(hasil.length, 5); i++) {
                        const m = hasil[i];

                        if (m.ada_foto && m.url_foto) {
                            try {
                                const img = await axios.get(m.url_foto, { responseType: 'arraybuffer' });
                                await sock.sendMessage(from, {
                                    image: Buffer.from(img.data),
                                    caption:
                                        `*${m.nama}*\n\n` +
                                        `Nama: ${m.nama}\n` +
                                        `NIM: ${m.nim}\n` +
                                        `Prodi: ${m.nama_prodi}\n` +
                                        `Angkatan: ${m.angkatan}`
                                });
                            } catch (e) {
                                await sock.sendMessage(from, {
                                    text:
                                        `*${m.nama}*\n\n` +
                                        `Nama: ${m.nama}\n` +
                                        `NIM: ${m.nim}\n` +
                                        `Prodi: ${m.nama_prodi}\n` +
                                        `Angkatan: ${m.angkatan}\n` +
                                        `Foto tidak tersedia`
                                });
                            }
                        } else {
                            await sock.sendMessage(from, {
                                text:
                                    `*Nama:* ${m.nama}\n` +
                                    `*NIM:* ${m.nim}\n` +
                                    `*Prodi:* ${m.nama_prodi}\n` +
                                    `*Angkatan:* ${m.angkatan}`
                            });
                        }
                    }
                } catch (e) {
                    await sock.sendMessage(from, { text: 'Error: ' + e.message });
                }
            }

            // ==========================================
            // FITUR !jadwal (BARU)
            // ==========================================
            if (trimmedText === '!jadwal') {
                await sock.sendMessage(from, { text: '🔎 Mengambil jadwal seminar terbaru...' });

                try {
                    const jadwalList = await ambilJadwal();

                    if (!jadwalList || jadwalList.length === 0 || jadwalList.error) {
                        await sock.sendMessage(from, { text: '📭 Belum ada jadwal seminar terbaru.' });
                        return;
                    }

                    // Filter jadwal hari ini dan besok
                    const sekarang = new Date();
                    const besok = new Date(sekarang);
                    besok.setDate(besok.getDate() + 2);

                    const jadwalTerdekat = jadwalList.filter(j => {
                        const mulai = new Date(j.mulai);
                        return mulai >= sekarang && mulai < besok;
                    });

                    const jadwalTampil = jadwalTerdekat.length > 0 ? jadwalTerdekat : jadwalList.slice(0, 5);

                    let reply = '*JADWAL SEMINAR TERDEKAT*\n\n';

                    // Kirim data SATU PER SATU dengan foto
                    for (const j of jadwalTampil) {
                        const tgl = new Date(j.mulai);
                        const jamMulai = tgl.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
                        const jamSelesai = j.selesai ? new Date(j.selesai).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '';
                        const tglStr = tgl.toLocaleDateString('id-ID', {
                            weekday: 'long',
                            day: 'numeric',
                            month: 'long',
                            year: 'numeric'
                        });

                        const caption =
                            `*${j.nama}*\n\n` +
                            `NIM: ${j.nim || 'Tidak ditemukan'}\n` +
                            `${tglStr}\n` +
                            `${jamMulai}${jamSelesai ? ' - ' + jamSelesai : ''}\n` +
                            `*Jenis:* ${j.jenis || 'Seminar'}\n` +
                            `*Judul:* ${j.judul || '-'}\n`;
                        // `🔗 ${j.link || ''}`;

                        if (j.ada_foto && j.url_foto) {
                            try {
                                const img = await axios.get(j.url_foto, { responseType: 'arraybuffer' });
                                await sock.sendMessage(from, {
                                    image: Buffer.from(img.data),
                                    caption: caption
                                });
                            } catch (e) {
                                // Kalau gagal kirim foto, kirim teks saja
                                await sock.sendMessage(from, { text: caption });
                            }
                        } else {
                            // Tanpa foto
                            await sock.sendMessage(from, { text: caption });
                        }
                    }

                    await sock.sendMessage(from, { text: reply });
                } catch (error) {
                    await sock.sendMessage(from, { text: 'Gagal mengambil jadwal. Coba lagi nanti.' });
                }
            }

        }
    });
}

console.log('BOT UNMUL');
startBot().catch(err => console.error(err));