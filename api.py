import httpx
import logging

logger = logging.getLogger(__name__)

# ============================================
# FunDrama API
# ============================================
BASE_FUNDRAMA = "https://drakula.dramabos.online/api/fundrama"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}


async def get_drama_detail(drama_id: str):
    """Ambil detail drama dari FunDrama API."""
    url = f"{BASE_FUNDRAMA}/drama/{drama_id}"
    params = {"code": AUTH_CODE}
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                logger.error(f"[FunDrama] Detail {drama_id} HTTP {res.status_code}")
                return None

            data = res.json()
            if not data.get("success"):
                logger.error(f"[FunDrama] API failed: {data.get('mchart')}")
                return None

            # Safely navigate the nested dict
            data_dict = data.get("data") or {}
            ddriv = data_dict.get("ddriv") or {}
            payload = ddriv.get("btra") or data_dict or {}

            # Prioritize finding a real title
            title = (
                payload.get("title") or 
                payload.get("sstat") or 
                payload.get("dshame") or 
                payload.get("short_play_name") or 
                payload.get("bookName") or 
                payload.get("name") or 
                ""
            )
            intro = payload.get("sdebt") or payload.get("intro") or ""
            poster = payload.get("fdar") or payload.get("poster") or ""
            
            if not title:
                logger.warning(f"[FunDrama] Drama {drama_id} tidak punya judul")
                return None

            return {
                "_source": "fundrama",
                "id": str(drama_id),
                "title": title,
                "intro": intro,
                "poster": poster,
                "episodeCount": 0,
                "_raw": payload
            }
        except Exception as e:
            logger.error(f"[FunDrama] Detail error {drama_id}: {e}")
    return None


async def get_all_episodes(drama_id: str, lang: str = "id"):
    """Ambil semua episode dari FunDrama API."""
    url = f"{BASE_FUNDRAMA}/drama/{drama_id}/episodes"
    params = {"lang": lang, "code": AUTH_CODE}
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                logger.error(f"[FunDrama] Episodes {drama_id} HTTP {res.status_code}")
                return []

            data = res.json()
            if not data.get("success"):
                return []

            episode_list = data.get("data", {}).get("episodes", [])
            eps = []
            for ep in episode_list:
                ep_num = ep.get("episode")
                ep_id = ep.get("id")
                
                videos = ep.get("videos") or []
                play_url = ""
                if videos:
                    # Kualitas: cari yang 720p dulu
                    for v in videos:
                        if v.get("quality") in ["720p", "HD"]:
                            play_url = v.get("url")
                            break
                    if not play_url:
                        play_url = videos[0].get("url")

                if ep_num is not None and play_url:
                    eps.append({
                        "_source": "fundrama",
                        "dramaId": str(drama_id),
                        "ep": int(ep_num),
                        "episode": int(ep_num),
                        "videoId": str(ep_id),
                        "play_url": play_url,
                        "subtitle": "",
                    })
            
            return sorted(eps, key=lambda x: x["episode"])
        except Exception as e:
            logger.error(f"[FunDrama] Episodes error {drama_id}: {e}")
    return []


async def search_dramas(query: str, lang: str = "id"):
    """Cari drama dari FunDrama API."""
    url = f"{BASE_FUNDRAMA}/search"
    params = {"q": query, "lang": lang, "code": AUTH_CODE}
    all_dramas = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                logger.error(f"[FunDrama] Search {query} HTTP {res.status_code}")
                return []

            data = res.json()
            if not data.get("success"):
                return []

            dramas_raw = data.get("data", {}).get("ddriv", {}).get("lsumm", [])
            for item in dramas_raw:
                drama_id = str(item.get("id") or item.get("dshame") or "")
                title = item.get("title") or item.get("sstat") or item.get("dshame") or "Unknown"
                poster = item.get("fdar") or ""

                all_dramas.append({
                    "_source": "fundrama",
                    "id": drama_id,
                    "title": title,
                    "bookName": title,
                    "poster": poster,
                })
        except Exception as e:
            logger.error(f"[FunDrama] Search error {query}: {e}")
    return all_dramas


async def get_latest_dramas(pages=1, limit=20, lang="id", types=None, **kwargs):
    """
    Ambil daftar drama terbaru. 
    'types' bisa berupa list: ['discovery', 'popular', 'search_hot']
    """
    all_dramas = []
    seen_ids = set()
    
    # Defaults to just 'dramas' if no types specified
    if not types:
        search_types = ["dramas"]
    else:
        search_types = types if isinstance(types, list) else [types]

    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        for s_type in search_types:
            for page in range(1, pages + 1):
                try:
                    # Map types to endpoints
                    endpoint = s_type if s_type != "dramas" else "dramas"
                    url = f"{BASE_FUNDRAMA}/{endpoint}"
                    
                    params = {"lang": lang, "page": page, "limit": limit, "code": AUTH_CODE}
                    res = await client.get(url, params=params)
                    if res.status_code != 200:
                        continue

                    data = res.json()
                    if not data.get("success"):
                        continue

                    # Structure varies: sometimes in .data.ddriv.lsumm, sometimes .data.list
                    data_payload = data.get("data", {})
                    if isinstance(data_payload, dict):
                        dramas_raw = data_payload.get("ddriv", {}).get("lsumm") or data_payload.get("list") or []
                    else:
                        dramas_raw = []
                    
                    if not dramas_raw and isinstance(data_payload, list):
                        dramas_raw = data_payload

                    added = 0
                    for item in dramas_raw:
                        drama_id = str(item.get("id") or item.get("dshame") or "")
                        if not drama_id or drama_id in seen_ids:
                            continue
                        seen_ids.add(drama_id)

                        title = item.get("title") or item.get("sstat") or item.get("dshame") or "Unknown"
                        poster = item.get("fdar") or ""

                        all_dramas.append({
                            "_source": f"fundrama_{s_type}",
                            "id": drama_id,
                            "title": title,
                            "bookName": title,
                            "poster": poster,
                        })
                        added += 1

                    if added > 0:
                        logger.info(f"[FunDrama] {s_type} p{page}: +{added} drama")
                except Exception as e:
                    logger.error(f"[FunDrama] {s_type} error: {e}")

    return all_dramas


async def get_languages():
    """Ambil daftar bahasa dari FunDrama API."""
    url = f"{BASE_FUNDRAMA}/languages"
    params = {"code": AUTH_CODE}
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    return data.get("data", [])
        except Exception as e:
            logger.error(f"[FunDrama] Languages error: {e}")
    return []


# ============================================
# Compatibility Aliases
# ============================================
async def get_idrama_detail(book_id: str):
    return await get_drama_detail(book_id)

async def get_idrama_all_episodes(book_id: str):
    return await get_all_episodes(book_id)

async def get_latest_idramas(pages=1):
    return await get_latest_dramas(pages=pages)

async def get_stream_url(drama_id: str, ep: int):
    # Data episode sudah termasuk play_url
    return None

