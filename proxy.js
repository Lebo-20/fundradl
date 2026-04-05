const express = require('express');
const axios = require('axios');
const cors = require('cors');
const { URL } = require('url');

const app = express();
const PORT = process.env.PORT || 3000;

// Aktifkan CORS agar bisa diakses dari domain berbeda (misal player web)
app.use(cors());

/**
 * Endpoint Utama Proxy
 * URL format: /proxy?url=[URL_TUJUAN]
 */
app.get('/proxy', async (req, res) => {
    const targetUrl = req.query.url;

    if (!targetUrl) {
        return res.status(400).send('Missing parameter: url');
    }

    // Header statis sesuai permintaan
    const customHeaders = {
        'Referer': 'https://www.flickreels.net/',
        'Origin': 'https://www.flickreels.net/',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
    };

    try {
        const isM3U8 = targetUrl.includes('.m3u8');

        if (isM3U8) {
            // Jalankan logika untuk file manifest .m3u8
            const response = await axios.get(targetUrl, {
                headers: customHeaders,
                responseType: 'text'
            });

            let content = response.data;
            const baseUrl = targetUrl.substring(0, targetUrl.lastIndexOf('/') + 1);

            /**
             * Regex untuk mencari path dalam m3u8.
             * Mencari baris yang tidak diawali '#' (biasanya itu URL segment/sub-playlist)
             */
            const lines = content.split('\n');
            const rewrittenLines = lines.map(line => {
                const trimmedLine = line.trim();
                
                // Jika baris bukan comment/tag m3u8 dan tidak kosong
                if (trimmedLine && !trimmedLine.startsWith('#')) {
                    let absoluteUrl;
                    try {
                        // Jika sudah absolute (http://...), biarkan. Jika relative, gabung ke baseUrl
                        absoluteUrl = new URL(trimmedLine, baseUrl).href;
                    } catch (e) {
                        absoluteUrl = baseUrl + trimmedLine;
                    }
                    
                    // Bungkus kembali ke endpoint proxy kita sendiri
                    const host = req.get('host');
                    const protocol = req.protocol;
                    return `${protocol}://${host}/proxy?url=${encodeURIComponent(absoluteUrl)}`;
                }
                
                // Jika baris mengandung atribut URI="..." (misal pada sub-playlists atau subtitle)
                if (trimmedLine.includes('URI="')) {
                     return line.replace(/URI="([^"]+)"/g, (match, p1) => {
                        let abs;
                        try { abs = new URL(p1, baseUrl).href; } catch(e) { abs = baseUrl + p1; }
                        const host = req.get('host');
                        const protocol = req.protocol;
                        return `URI="${protocol}://${host}/proxy?url=${encodeURIComponent(abs)}"`;
                     });
                }

                return line;
            });

            res.set('Content-Type', 'application/x-mpegURL');
            return res.send(rewrittenLines.join('\n'));

        } else {
            // Jalankan logika untuk file media .ts atau binary lainnya
            const response = await axios({
                method: 'get',
                url: targetUrl,
                headers: customHeaders,
                responseType: 'stream'
            });

            // Set Content-Type sesuai aslinya (biasanya video/MP2T)
            res.set('Content-Type', response.headers['content-type'] || 'video/mp2t');
            
            // Pipe stream binary agar data tidak korup
            return response.data.pipe(res);
        }

    } catch (error) {
        console.error(`Error fetching URL ${targetUrl}:`, error.message);
        return res.status(500).send(`Proxy Error: ${error.message}`);
    }
});

app.listen(PORT, () => {
    console.log(`HLS Proxy Server running on port ${PORT}`);
    console.log(`Example usage: http://localhost:${PORT}/proxy?url=https://example.com/video.m3u8`);
});
