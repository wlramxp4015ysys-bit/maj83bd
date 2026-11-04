"""
Persistent JSON Database for Telegram Bot & Backend API.
Manages Channels, Categories, Channel APIs (PHP JSON & M3U), App Updates, Maintenance Mode, and Admins.
"""

import json
import os
import re
import time
import threading
from datetime import datetime
from urllib.request import Request, urlopen
from config import DB_FILE, ADMIN_ID, logger

_lock = threading.RLock()

# Initial defaults are empty as channels and categories are loaded exclusively from the Bot
DEFAULT_CATEGORIES = []
DEFAULT_CHANNELS = []

class Database:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with _lock:
            if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
                data = {
                    "categories": [],
                    "channels": [],
                    "channel_apis": [],
                    "maintenance": {
                        "enabled": False,
                        "message": "التطبيق يخضع لصيانة دورية لتحسين الأداء وتحديث السيرفرات، سنعود قريباً!",
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    },
                    "app_update": {
                        "enabled": False,
                        "version_code": 2,
                        "version_name": "1.1",
                        "download_url": "",
                        "release_notes": "إصلاحات عامة وإضافة قنوات جديدة وسرعة أعلى في البث",
                        "is_force": False,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    },
                    "admins": {}
                }
                if ADMIN_ID and ADMIN_ID != 0:
                    data["admins"][str(ADMIN_ID)] = {
                        "id": ADMIN_ID,
                        "name": "المدير العام (Super Admin)",
                        "role": "super_admin",
                        "permissions": ["all"],
                        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                self._save_raw(data)
            self.clean_manual_channels()

    def clean_manual_channels(self):
        """Removes any manually added app channels from the database permanently."""
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            initial_count = len(channels)
            kept = [
                ch for ch in channels
                if not (
                    str(ch.get("id", "")).startswith("ch-app-")
                    or str(ch.get("id", "")).startswith("direct-")
                    or "مضاف يدوياً" in str(ch.get("currentShow", ""))
                    or "مضاف يدوياً" in str(ch.get("description", ""))
                )
            ]
            if len(kept) != initial_count:
                data["channels"] = kept
                self._save_raw(data)
                logger.info("Cleaned %d manual channels from DB", initial_count - len(kept))
            return initial_count - len(kept)

    def _load_raw(self):
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "categories": [],
                "channels": [],
                "channel_apis": [],
                "maintenance": {"enabled": False, "message": "صيانة دورية", "updated_at": ""},
                "app_update": {"enabled": False, "version_code": 2, "version_name": "1.1", "download_url": "", "release_notes": "", "is_force": False},
                "admins": {}
            }

    def _save_raw(self, data):
        temp_file = f"{self.db_path}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, self.db_path)

    # ------------------ Categories ------------------
    QUAL_RANKS = {
        "4K": 5, "2160P": 5, "UHD": 5,
        "FHD": 4, "1080P": 4,
        "HD": 3, "720P": 3,
        "SD": 2, "480P": 2,
        "LOW": 1, "360P": 1
    }

    def _normalize_name_and_quality(self, raw_name, default_quality="HD"):
        """
        Extracts base channel name and quality string from channel title.
        e.g.:
        'beIN SPORTS 1 FHD' -> ('beIN SPORTS 1', 'FHD')
        'beIN SPORTS 1 [1080p]' -> ('beIN SPORTS 1', 'FHD')
        'SSC 1 - HD' -> ('SSC 1', 'HD')
        'الكأس 1 SD' -> ('الكأس 1', 'SD')
        'beIN Sports 2 4K' -> ('beIN Sports 2', '4K')
        """
        if not raw_name:
            return "قناة بث مباشر", default_quality or "HD"

        cleaned = str(raw_name).strip()
        pattern = r'[\s\-_\[\(\{\|]+(?:FHD|1080p?|HD|720p?|SD|480p?|360p?|4K|2160p?|UHD|LOW|HEVC|H\.?265)[\s\-_\]\)\}\|]*$'
        m = re.search(pattern, cleaned, re.IGNORECASE)
        quality = default_quality or "HD"
        if m:
            matched_str = m.group(0).upper()
            base = cleaned[:m.start()].strip()
            if any(q in matched_str for q in ["4K", "2160", "UHD"]): quality = "4K"
            elif any(q in matched_str for q in ["FHD", "1080"]): quality = "FHD"
            elif any(q in matched_str for q in ["HD", "720"]): quality = "HD"
            elif any(q in matched_str for q in ["SD", "480"]): quality = "SD"
            elif any(q in matched_str for q in ["LOW", "360"]): quality = "LOW"
            return (base if base else cleaned), quality

        upper = cleaned.upper()
        if " 4K" in upper or "[4K]" in upper: quality = "4K"
        elif " FHD" in upper or "[FHD]" in upper or "1080P" in upper: quality = "FHD"
        elif " HD" in upper or "[HD]" in upper or "720P" in upper: quality = "HD"
        elif " SD" in upper or "[SD]" in upper or "480P" in upper: quality = "SD"
        elif " LOW" in upper or "[LOW]" in upper: quality = "LOW"

        return cleaned, quality

    def get_categories(self, api_id=None):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            if api_id and api_id != "all":
                return [c for c in cats if c.get("api_id") == api_id]
            return cats

    def get_categories_for_api(self, api_id):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            categories = data.get("categories", [])
            result = []
            for c in categories:
                # Count channels in this category that belong to this API or in general
                ch_count = len([ch for ch in channels if ch.get("category") == c["id"] and (not api_id or ch.get("api_id") == api_id or c.get("api_id") == api_id)])
                if c.get("api_id") == api_id or (api_id and ch_count > 0) or (not api_id):
                    result.append({
                        "id": c["id"],
                        "name": c["name"],
                        "icon": c.get("icon", "📁"),
                        "count": ch_count,
                        "api_id": c.get("api_id", api_id or "general")
                    })
            return result

    def get_category(self, cat_id):
        with _lock:
            data = self._load_raw()
            for c in data.get("categories", []):
                if c.get("id") == cat_id:
                    return c
            return None

    def add_category(self, cat_id, name, icon="📁", image=None, api_id=None):
        with _lock:
            data = self._load_raw()
            cats = data.setdefault("categories", [])
            clean_id = str(cat_id).strip().lower().replace(" ", "_")
            clean_name = str(name).strip()
            clean_icon = str(icon).strip() if icon else "📁"
            clean_image = str(image).strip() if image else ""
            clean_api = str(api_id).strip() if api_id else "general"
            for c in cats:
                if c["id"] == clean_id:
                    c["name"] = clean_name
                    c["icon"] = clean_icon
                    if clean_image: c["image"] = clean_image
                    if api_id: c["api_id"] = clean_api
                    self._save_raw(data)
                    logger.info("Category updated in DB: %s", c)
                    return True, c

            new_cat = {
                "id": clean_id,
                "name": clean_name,
                "icon": clean_icon,
                "image": clean_image,
                "api_id": clean_api,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            cats.append(new_cat)
            self._save_raw(data)

            # Verification
            verified = any(c["id"] == clean_id for c in self._load_raw().get("categories", []))
            if verified:
                logger.info("Category added to DB: %s", new_cat)
                return True, new_cat
            logger.error("Category persistence verification failed: %s", clean_id)
            return False, "فشل حفظ القسم في قاعدة البيانات"

    def update_category(self, cat_id, new_name=None, new_icon=None, new_image=None, api_id=None):
        with _lock:
            data = self._load_raw()
            cats = data.setdefault("categories", [])
            target = None
            for c in cats:
                if c["id"] == cat_id:
                    target = c
                    break
            if not target:
                return False, "القسم المطلوب غير موجود"

            if new_name is not None and str(new_name).strip():
                target["name"] = str(new_name).strip()
                for ch in data.get("channels", []):
                    if ch.get("category") == cat_id:
                        ch["categoryName"] = target["name"]

            if new_icon is not None and str(new_icon).strip():
                target["icon"] = str(new_icon).strip()

            if new_image is not None:
                target["image"] = str(new_image).strip()

            if api_id is not None:
                if str(api_id).strip() in ["", "none", "direct"]:
                    target.pop("api_id", None)
                else:
                    target["api_id"] = str(api_id).strip()

            self._save_raw(data)

            verified = any(c["id"] == cat_id for c in self._load_raw().get("categories", []))
            if verified:
                logger.info("Category updated in DB: %s", target)
                return True, target
            return False, "فشل حفظ تعديل القسم"

    def delete_category(self, cat_id, delete_channels=False, move_to_cat_id=None):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            initial_len = len(cats)
            data["categories"] = [c for c in cats if c["id"] != cat_id]

            channels = data.get("channels", [])
            if delete_channels:
                data["channels"] = [ch for ch in channels if ch.get("category") != cat_id]
            elif move_to_cat_id:
                dest_cat = next((c for c in data.get("categories", []) if c["id"] == move_to_cat_id), None)
                dest_name = dest_cat.get("name", "عام") if dest_cat else "عام"
                for ch in channels:
                    if ch.get("category") == cat_id:
                        ch["category"] = move_to_cat_id
                        ch["categoryName"] = dest_name
            else:
                gen_cat = next((c for c in data.get("categories", []) if c["id"] == "general"), None)
                if not gen_cat:
                    data.setdefault("categories", []).append({
                        "id": "general",
                        "name": "عام",
                        "icon": "📁"
                    })
                for ch in channels:
                    if ch.get("category") == cat_id:
                        ch["category"] = "general"
                        ch["categoryName"] = "عام"

            self._save_raw(data)

            verified = len(self._load_raw().get("categories", [])) < initial_len
            if verified:
                logger.info("Category deleted from DB: %s (delete_channels=%s, move_to=%s)", cat_id, delete_channels, move_to_cat_id)
                return True, cat_id
            return False, "القسم غير موجود أو تعذر حذفه"

    def search_categories(self, query):
        if not query or not str(query).strip():
            return self.get_categories()
        norm_q = self._normalize_arabic(query)
        with _lock:
            data = self._load_raw()
            results = []
            for c in data.get("categories", []):
                c_name = self._normalize_arabic(c.get("name", ""))
                c_id = c.get("id", "").lower()
                if norm_q in c_name or norm_q in c_id:
                    results.append(c)
            return results

    def get_categories_paged(self, page=1, page_size=8, search_query=""):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            if search_query and search_query.strip():
                norm_q = self._normalize_arabic(search_query)
                cats = [c for c in cats if norm_q in self._normalize_arabic(c.get("name", "")) or norm_q in c.get("id", "").lower()]
            total_items = len(cats)
            total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
            page = max(1, min(page, total_pages))
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            return {
                "items": cats[start_idx:end_idx],
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages
            }

    def clear_categories(self):
        with _lock:
            data = self._load_raw()
            data["categories"] = []
            self._save_raw(data)
            logger.info("All categories cleared from DB")
            return True

    def reorder_category(self, cat_id, direction="up"):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            idx = next((i for i, c in enumerate(cats) if c.get("id") == cat_id), -1)
            if idx == -1:
                return False, "القسم غير موجود"
            if direction == "up" and idx > 0:
                cats[idx], cats[idx - 1] = cats[idx - 1], cats[idx]
            elif direction == "down" and idx < len(cats) - 1:
                cats[idx], cats[idx + 1] = cats[idx + 1], cats[idx]
            else:
                return False, "القسم بالفعل في نهاية الترتيب"
            data["categories"] = cats
            self._save_raw(data)
            return True, "تم تغيير ترتيب القسم بنجاح"

    def toggle_category_hidden(self, cat_id):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            target = None
            for c in cats:
                if c.get("id") == cat_id:
                    new_val = not c.get("hidden", False)
                    c["hidden"] = new_val
                    target = c
                    break
            if not target:
                return False, "القسم غير موجود"
            self._save_raw(data)
            return True, target.get("hidden", False)

    def clear_category_channels(self, cat_id):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            initial_count = len(channels)
            data["channels"] = [c for c in channels if c.get("category") != cat_id]
            removed = initial_count - len(data["channels"])
            self._save_raw(data)
            logger.info("Cleared %d channels from category %s", removed, cat_id)
            return removed

    def move_category_channels(self, from_cat_id, to_cat_id, to_cat_name=None):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            if not to_cat_name:
                for c in data.get("categories", []):
                    if c.get("id") == to_cat_id:
                        to_cat_name = c.get("name", to_cat_id)
                        break
            to_cat_name = to_cat_name or to_cat_id
            count = 0
            for ch in channels:
                if ch.get("category") == from_cat_id:
                    ch["category"] = to_cat_id
                    ch["categoryName"] = to_cat_name
                    count += 1
            self._save_raw(data)
            logger.info("Moved %d channels from %s to %s", count, from_cat_id, to_cat_id)
            return count


    # ------------------ Channels ------------------
    def get_channels(self, category=None):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            if category and category != "all":
                return [c for c in channels if c.get("category") == category]
            return channels

    def get_channel(self, channel_id):
        with _lock:
            data = self._load_raw()
            for ch in data.get("channels", []):
                if ch.get("id") == channel_id:
                    return ch
            return None

    def add_channel(self, ch_dict):
        with _lock:
            data = self._load_raw()
            channels = data.setdefault("channels", [])
            if not ch_dict.get("id"):
                ch_dict["id"] = f"ch-{int(time.time())}-{len(channels)}"
            for i, c in enumerate(channels):
                if c["id"] == ch_dict["id"]:
                    channels[i] = ch_dict
                    self._save_raw(data)
                    return ch_dict
            channels.insert(0, ch_dict)
            self._save_raw(data)
            return ch_dict

    def add_single_channel(self, name, url, category_id="general", category_name=None, logo="📺", quality="FHD", referer="", useragent="", origin="", cookie="", key="", scheme="", api_id="direct"):
        with _lock:
            data = self._load_raw()
            categories = data.setdefault("categories", [])
            channels = data.setdefault("channels", [])

            cat_id_clean = str(category_id or "general").strip()
            cat_match = next((c for c in categories if c["id"] == cat_id_clean or c["name"] == cat_id_clean), None)
            if not cat_match:
                if not category_name:
                    category_name = "قنوات رياضية" if "sport" in cat_id_clean.lower() or "رياض" in cat_id_clean else (cat_id_clean if cat_id_clean != "general" else "منوعات عامة")
                icon = "⚽" if "رياض" in str(category_name) or "sport" in str(category_name).lower() else "📺"
                cat_match = {"id": cat_id_clean.lower().replace(" ", "_"), "name": str(category_name), "icon": icon, "api_id": str(api_id or "general")}
                categories.append(cat_match)
            cat_id = cat_match["id"]
            cat_name = cat_match["name"]

            clean_url = str(url).strip()
            lower_url = clean_url.lower()

            # Auto-detect Ostora / Uruk / Maziika headers
            if any(k in lower_url for k in ["maziika", "sa037", "sa047", "ostora", "uruk", "optikl"]):
                if not referer:
                    referer = "https://www.w2.maziikaaaaa.shop/"
                if not useragent:
                    useragent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

            stream_type = "hls"
            if ".mpd" in lower_url:
                stream_type = "dash"
            elif ".mp4" in lower_url:
                stream_type = "mp4"
            elif ".ts" in lower_url:
                stream_type = "ts"
            elif ".m3u8" in lower_url or ".php" in lower_url or ".js" in lower_url:
                stream_type = "hls"

            base_name, detected_quality = self._normalize_name_and_quality(name, quality)
            effective_quality = quality if quality and quality != "HD" else detected_quality

            server_obj = {
                "name": f"جودة ({effective_quality})",
                "quality": effective_quality,
                "url": clean_url,
                "type": stream_type,
                "referer": str(referer).strip() if referer else "",
                "useragent": str(useragent).strip() if useragent else ""
            }

            # Check if channel with this base_name already exists in this category
            existing_ch = None
            for c in channels:
                if c.get("category") == cat_id and (c.get("name", "").strip().lower() == base_name.lower() or c.get("url") == clean_url):
                    existing_ch = c
                    break

            if existing_ch:
                servers = existing_ch.setdefault("servers", [])
                if not any(s.get("url") == clean_url for s in servers):
                    servers.append(server_obj)

                # If this quality is higher, set as primary
                curr_rank = self.QUAL_RANKS.get(existing_ch.get("quality", "HD").upper(), 3)
                new_rank = self.QUAL_RANKS.get(effective_quality.upper(), 3)
                if new_rank >= curr_rank:
                    existing_ch["quality"] = effective_quality
                    existing_ch["url"] = clean_url
                    existing_ch["streamUrl"] = clean_url
                    if referer: existing_ch["referer"] = referer
                    if useragent: existing_ch["useragent"] = useragent

                self._save_raw(data)
                logger.info("Channel merged into existing entry: %s with quality %s (total qualities: %s)", base_name, effective_quality, len(servers))
                return existing_ch

            ch_id = f"ch-{int(time.time())}-{len(channels)}"
            new_ch = {
                "id": ch_id,
                "name": base_name,
                "category": cat_id,
                "categoryName": cat_name,
                "api_id": str(api_id or "direct"),
                "currentShow": "بث مباشر حصري عبر الإنترنت",
                "logo": str(logo).strip() if logo else "📺",
                "quality": effective_quality,
                "url": clean_url,
                "streamUrl": clean_url,
                "referer": str(referer).strip() if referer else "",
                "useragent": str(useragent).strip() if useragent else "",
                "origin": str(origin).strip() if origin else "",
                "cookie": str(cookie).strip() if cookie else "",
                "key": str(key).strip() if key else "",
                "scheme": str(scheme).strip() if scheme else "",
                "badge": "مباشر",
                "servers": [server_obj]
            }

            channels.insert(0, new_ch)
            self._save_raw(data)
            logger.info("Channel created in DB: %s with quality %s", base_name, effective_quality)
            return new_ch

    def update_channel(self, channel_id, ch_dict):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            target = None
            for i, c in enumerate(channels):
                if c["id"] == channel_id:
                    for k, v in ch_dict.items():
                        c[k] = v
                    c["id"] = channel_id
                    target = c
                    break
            if not target:
                return False, "القناة غير موجودة"

            self._save_raw(data)

            # Verification
            saved_ch = self.get_channel(channel_id)
            if saved_ch:
                logger.info("Channel updated in DB: %s (name: %s)", channel_id, saved_ch.get("name"))
                return True, saved_ch
            logger.error("Channel update verification failed: %s", channel_id)
            return False, "فشل حفظ تعديل القناة في قاعدة البيانات"

    def delete_channel(self, channel_id):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            initial_len = len(channels)
            ch_name = next((c.get("name", channel_id) for c in channels if c["id"] == channel_id), channel_id)
            data["channels"] = [c for c in channels if c["id"] != channel_id]
            self._save_raw(data)

            # Verification
            verified = len(self._load_raw().get("channels", [])) < initial_len
            if verified:
                logger.info("Channel deleted from DB: %s (%s)", channel_id, ch_name)
                return True, ch_name
            return False, "القناة غير موجودة أو تعذر حذفها"

    def move_channel_to_category(self, channel_id, new_category_id):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            target_cat = next((c for c in cats if c["id"] == new_category_id), None)
            if not target_cat:
                return False, "القسم الهدف غير موجود"
            cat_name = target_cat.get("name", new_category_id)

            for ch in data.get("channels", []):
                if ch["id"] == channel_id:
                    ch["category"] = new_category_id
                    ch["categoryName"] = cat_name
                    self._save_raw(data)
                    logger.info("Channel %s moved to category %s", channel_id, new_category_id)
                    return True, ch
            return False, "القناة غير موجودة"

    def get_channels_by_category(self, category_id):
        return self.get_channels(category_id)

    def delete_all_channels(self):
        with _lock:
            data = self._load_raw()
            count = len(data.get("channels", []))
            data["channels"] = []
            self._save_raw(data)
            logger.info("All channels cleared from DB: %s removed", count)
            return count

    @staticmethod
    def _normalize_arabic(text):
        if not text:
            return ""
        text = str(text).lower()
        text = re.sub(r'[إأآا]', 'ا', text)
        text = re.sub(r'ة', 'ه', text)
        text = re.sub(r'[ىي]', 'ي', text)
        text = re.sub(r'[ًٌٍَُِّْـ]', '', text)
        return text.strip()

    def search_channels(self, query, category=None):
        if not query or not str(query).strip():
            return self.get_channels(category)
        norm_q = self._normalize_arabic(query)
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            if category and category != "all":
                channels = [c for c in channels if c.get("category") == category]
            results = []
            for ch in channels:
                name = self._normalize_arabic(ch.get("name", ""))
                cat_name = self._normalize_arabic(ch.get("categoryName", ""))
                url = ch.get("url", "").lower()
                qual = ch.get("quality", "").lower()
                matched = (norm_q in name) or (norm_q in cat_name) or (norm_q in url) or (norm_q in qual)
                if not matched:
                    for srv in ch.get("servers", []):
                        s_name = self._normalize_arabic(srv.get("name", ""))
                        s_url = srv.get("url", "").lower()
                        if norm_q in s_name or norm_q in s_url:
                            matched = True
                            break
                if matched:
                    results.append(ch)
            return results

    def get_channels_by_category_paged(self, category_id, page=1, page_size=8, search_query=""):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            if category_id and category_id != "all":
                channels = [c for c in channels if c.get("category") == category_id]
            if search_query and search_query.strip():
                norm_q = self._normalize_arabic(search_query)
                filtered = []
                for ch in channels:
                    name = self._normalize_arabic(ch.get("name", ""))
                    if norm_q in name or norm_q in ch.get("id", "").lower():
                        filtered.append(ch)
                channels = filtered
            total_items = len(channels)
            total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
            page = max(1, min(page, total_pages))
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            return {
                "items": channels[start_idx:end_idx],
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages
            }

    def update_channel_basic(self, channel_id, name=None, url=None, quality=None, logo=None, category_id=None):
        with _lock:
            data = self._load_raw()
            channels = data.get("channels", [])
            target = next((ch for ch in channels if ch["id"] == channel_id), None)
            if not target:
                return False, "القناة غير موجودة"
            if name and name.strip():
                target["name"] = name.strip()
            if url and url.strip():
                target["url"] = url.strip()
                target["streamUrl"] = url.strip()
                if target.get("servers") and len(target["servers"]) > 0:
                    target["servers"][0]["url"] = url.strip()
            if quality and quality.strip():
                target["quality"] = quality.strip().upper()
                if target.get("servers") and len(target["servers"]) > 0:
                    target["servers"][0]["quality"] = quality.strip().upper()
            if logo is not None:
                target["logo"] = logo.strip()
            if category_id:
                cat = next((c for c in data.get("categories", []) if c["id"] == category_id), None)
                target["category"] = category_id
                target["categoryName"] = cat.get("name", category_id) if cat else category_id
            self._save_raw(data)
            logger.info("Channel %s updated: name=%s, url=%s, qual=%s", channel_id, name, url, quality)
            return True, target

    def toggle_channel_disabled(self, channel_id):
        with _lock:
            data = self._load_raw()
            for ch in data.get("channels", []):
                if ch.get("id") == channel_id:
                    new_val = not ch.get("disabled", False)
                    ch["disabled"] = new_val
                    self._save_raw(data)
                    logger.info("Channel %s toggled disabled=%s", channel_id, new_val)
                    return True, new_val
            return False, "القناة غير موجودة"

    def add_channel_server(self, channel_id, quality, url, name=None, referer="", useragent=""):
        with _lock:
            data = self._load_raw()
            for ch in data.get("channels", []):
                if ch.get("id") == channel_id:
                    servers = ch.setdefault("servers", [])
                    srv_name = name or f"جودة ({quality})"
                    existing = next((s for s in servers if s.get("quality", "").upper() == quality.upper()), None)
                    if not referer or not useragent:
                        lower_u = str(url).lower()
                        if any(k in lower_u for k in ["maziika", "sa037", "sa047", "ostora", "uruk", "optikl"]):
                            if not referer: referer = "https://www.w2.maziikaaaaa.shop/"
                            if not useragent: useragent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

                    if existing:
                        existing["url"] = url
                        existing["name"] = srv_name
                        if referer: existing["referer"] = referer
                        if useragent: existing["useragent"] = useragent
                    else:
                        stype = "hls" if (".m3u8" in url or "m3u8" in url) else ("ts" if ".ts" in url else "mp4")
                        servers.append({
                            "name": srv_name,
                            "quality": quality,
                            "url": url,
                            "type": stype,
                            "referer": referer,
                            "useragent": useragent
                        })
                    self._save_raw(data)
                    logger.info("Server/quality added to channel %s: %s", channel_id, quality)
                    return True, ch
            return False, "القناة غير موجودة"

    def delete_channel_server(self, channel_id, server_idx):
        with _lock:
            data = self._load_raw()
            for ch in data.get("channels", []):
                if ch.get("id") == channel_id:
                    servers = ch.get("servers", [])
                    if 0 <= server_idx < len(servers):
                        removed = servers.pop(server_idx)
                        if servers:
                            ch["url"] = servers[0].get("url", ch.get("url"))
                            ch["quality"] = servers[0].get("quality", ch.get("quality"))
                        self._save_raw(data)
                        logger.info("Server removed from channel %s: %s", channel_id, removed)
                        return True, removed
                    return False, "رقم السيرفر غير صحيح"
            return False, "القناة غير موجودة"

    def update_channel_logo(self, channel_id, logo):
        return self.update_channel(channel_id, {"logo": logo})

    def update_channel_headers(self, channel_id, referer=None, useragent=None, origin=None, cookie=None, key=None):
        patch = {}
        if referer is not None: patch["referer"] = referer
        if useragent is not None: patch["useragent"] = useragent
        if origin is not None: patch["origin"] = origin
        if cookie is not None: patch["cookie"] = cookie
        if key is not None: patch["key"] = key
        return self.update_channel(channel_id, patch)

    def test_stream_url(self, url, referer="", useragent="", timeout=6):
        try:
            req_headers = {
                "User-Agent": useragent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            if referer:
                req_headers["Referer"] = referer
            req = Request(url, headers=req_headers)
            t0 = time.time()
            with urlopen(req, timeout=timeout) as resp:
                elapsed_ms = int((time.time() - t0) * 1000)
                code = resp.getcode()
                ctype = resp.headers.get("Content-Type", "unknown")
                return {
                    "ok": True,
                    "code": code,
                    "latency": elapsed_ms,
                    "content_type": ctype,
                    "message": f"🟢 الرابط يعمل بكفاءة ({code} OK | {elapsed_ms}ms)"
                }
        except Exception as e:
            return {
                "ok": False,
                "code": 0,
                "error": str(e),
                "message": f"🔴 تعذر الاتصال أو الرابط لا يعمل: {e}"
            }

    def export_channels_m3u(self, category=None):
        channels = self.get_channels(category)
        lines = ["#EXTM3U"]
        for ch in channels:
            cid = ch.get("id", "")
            name = ch.get("name", "Channel")
            cat_name = ch.get("categoryName", "عام")
            logo = ch.get("logo", "")
            logo_attr = f' tvg-logo="{logo}"' if logo and logo.startswith("http") else ""
            url = ch.get("url", "")
            ref = ch.get("referer", "")
            ua = ch.get("useragent", "")
            qual = ch.get("quality", "")
            title = f"{name} [{qual}]" if qual else name

            lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}"{logo_attr} group-title="{cat_name}",{title}')
            if ua:
                lines.append(f'#EXTVLCOPT:http-user-agent={ua}')
            if ref:
                lines.append(f'#EXTVLCOPT:http-referrer={ref}')
            lines.append(url)
        return "\n".join(lines)

    def export_database_json(self):
        with _lock:
            data = self._load_raw()
            return json.dumps(data, ensure_ascii=False, indent=2)

    def import_database_json(self, json_content_or_dict, merge=True):
        with _lock:
            try:
                if isinstance(json_content_or_dict, (bytes, bytearray)):
                    json_content_or_dict = json_content_or_dict.decode('utf-8')
                if isinstance(json_content_or_dict, str):
                    imported = json.loads(json_content_or_dict)
                else:
                    imported = json_content_or_dict
            except Exception as e:
                return False, f"تنسيق JSON غير صالح: {e}"

            if not isinstance(imported, dict):
                return False, "تنسيق البيانات غير صحيح، يجب أن يكون كائن JSON رئيسي"

            if not merge:
                self._save_raw(imported)
                return True, "تم استبدال قاعدة البيانات بالكامل بنجاح"

            data = self._load_raw()
            existing_cat_ids = {c["id"]: c for c in data.get("categories", [])}
            for c in imported.get("categories", []):
                if c.get("id") in existing_cat_ids:
                    existing_cat_ids[c["id"]].update(c)
                else:
                    data.setdefault("categories", []).append(c)

            existing_ch_ids = {ch["id"]: ch for ch in data.get("channels", [])}
            added_ch = 0
            for ch in imported.get("channels", []):
                if ch.get("id") in existing_ch_ids:
                    existing_ch_ids[ch["id"]].update(ch)
                else:
                    data.setdefault("channels", []).append(ch)
                    added_ch += 1

            existing_api_ids = {a["id"]: a for a in data.get("channel_apis", [])}
            for a in imported.get("channel_apis", []):
                if a.get("id") in existing_api_ids:
                    existing_api_ids[a["id"]].update(a)
                else:
                    data.setdefault("channel_apis", []).append(a)

            self._save_raw(data)
            return True, f"تم دمج البيانات بنجاح (إضافة {added_ch} قناة جديدة)"

    def get_channel_stats(self):
        with _lock:
            data = self._load_raw()
            cats = data.get("categories", [])
            channels = data.get("channels", [])
            apis = data.get("channel_apis", [])

            active_cnt = sum(1 for c in channels if not c.get("disabled", False))
            disabled_cnt = len(channels) - active_cnt

            by_cat = {}
            for c in cats:
                by_cat[c.get("name", c["id"])] = 0
            for ch in channels:
                cname = ch.get("categoryName", "عام")
                by_cat[cname] = by_cat.get(cname, 0) + 1

            by_qual = {}
            for ch in channels:
                q = ch.get("quality", "FHD").upper()
                by_qual[q] = by_qual.get(q, 0) + 1

            multi_server_count = sum(1 for ch in channels if len(ch.get("servers", [])) > 1)

            return {
                "total_categories": len(cats),
                "total_channels": len(channels),
                "active_channels": active_cnt,
                "disabled_channels": disabled_cnt,
                "multi_quality_channels": multi_server_count,
                "total_apis": len(apis),
                "by_category": by_cat,
                "by_quality": by_qual
            }


    # ------------------ Channel APIs (PHP JSON & M3U) ------------------
    def get_channel_apis(self):
        with _lock:
            data = self._load_raw()
            return data.get("channel_apis", [])

    def get_channel_api(self, api_id):
        with _lock:
            data = self._load_raw()
            for a in data.get("channel_apis", []):
                if a.get("id") == api_id:
                    return a
            return None

    def add_channel_api(self, name, url, api_type="php_json"):
        with _lock:
            data = self._load_raw()
            apis = data.setdefault("channel_apis", [])
            api_id = f"api-{int(time.time())}"
            new_api = {
                "id": api_id,
                "name": str(name).strip(),
                "url": str(url).strip(),
                "type": str(api_type).strip(),
                "status": "نشط",
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            apis.append(new_api)
            self._save_raw(data)

            # Verification
            verified = any(a["id"] == api_id for a in self._load_raw().get("channel_apis", []))
            if not verified:
                logger.error("Channel API verification failed: %s", api_id)
                return False, "فشل حفظ سيرفر API في قاعدة البيانات", {}

        # Auto-sync API channels & categories immediately
        sync_res = {}
        clean_type = str(api_type).strip().lower()
        if clean_type == "m3u":
            cnt = self.sync_m3u_from_url(url, api_id=api_id)
            sync_res = {"success": cnt >= 0, "channels_count": max(0, cnt)}
        else:
            sync_res = self.sync_php_json(url, api_id=api_id)

        # Get the categories created or associated with this API
        api_categories = self.get_categories_for_api(api_id)
        sync_res["categories"] = api_categories

        logger.info("Channel API added and synced: %s (categories: %s, channels: %s)", name, len(api_categories), sync_res.get("channels_count", 0))
        return True, new_api, sync_res

    def update_channel_api(self, api_id, name=None, url=None, api_type=None):
        with _lock:
            data = self._load_raw()
            apis = data.get("channel_apis", [])
            target = None
            for a in apis:
                if a["id"] == api_id:
                    if name is not None and str(name).strip(): a["name"] = str(name).strip()
                    if url is not None and str(url).strip(): a["url"] = str(url).strip()
                    if api_type is not None and str(api_type).strip(): a["type"] = str(api_type).strip()
                    target = a
                    break
            if not target:
                return False, "سيرفر API غير موجود"

            self._save_raw(data)

            # Verification
            verified = any(a["id"] == api_id for a in self._load_raw().get("channel_apis", []))
            if verified:
                logger.info("Channel API updated in DB: %s", target)
                return True, target
            return False, "فشل حفظ تعديل سيرفر API"

    def delete_channel_api(self, api_id):
        with _lock:
            data = self._load_raw()
            apis = data.get("channel_apis", [])
            initial_len = len(apis)
            api_name = next((a.get("name", api_id) for a in apis if a["id"] == api_id), api_id)
            data["channel_apis"] = [a for a in apis if a["id"] != api_id]
            self._save_raw(data)

            # Verification
            verified = len(self._load_raw().get("channel_apis", [])) < initial_len
            if verified:
                logger.info("Channel API deleted from DB: %s (%s)", api_id, api_name)
                return True, api_name
            return False, "سيرفر API غير موجود أو تعذر حذفه"

    # ------------------ PHP API JSON Universal Importer ------------------
    def sync_php_json(self, url_or_raw, api_id=None):
        """
        Universal importer for PHP API JSON endpoints and raw JSON data.
        Supports all common PHP IPTV structures:
        1. Dict with 'categories' and 'channels'
        2. Array of category objects containing channels
        3. Flat array of channels with category fields
        4. Xtream codes / custom PHP output formats
        """
        try:
            raw_str = url_or_raw.strip()
            # If it's a URL, fetch it via HTTP
            if raw_str.startswith("http://") or raw_str.startswith("https://"):
                req = Request(
                    raw_str,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                        "Accept": "application/json, text/plain, */*"
                    }
                )
                with urlopen(req, timeout=14) as response:
                    raw_str = response.read().decode("utf-8", errors="ignore")

            parsed = json.loads(raw_str)
            return self._process_parsed_json(parsed, api_id=api_id)
        except Exception as e:
            return {"success": False, "error": str(e), "channels_count": 0, "categories_count": 0}

    def _process_parsed_json(self, parsed, api_id=None):
        with _lock:
            data = self._load_raw()
            categories = data.setdefault("categories", [])
            channels = data.setdefault("channels", [])

            # Helper to find or create category
            cat_map = {c["id"]: c["name"] for c in categories}
            name_to_id = {c["name"].lower(): c["id"] for c in categories}

            def ensure_category(raw_name_or_id):
                if not raw_name_or_id:
                    cat_name = "منوعات"
                    cat_id = "general"
                else:
                    cat_name = str(raw_name_or_id).strip()
                    cat_id = cat_name.lower().replace(" ", "_")
                    cat_id = re.sub(r'[^a-zA-Z0-9_\u0600-\u06FF]', '', cat_id) or f"cat_{int(time.time())}"

                if cat_name.lower() in name_to_id:
                    c_id = name_to_id[cat_name.lower()]
                    return c_id, cat_map.get(c_id, cat_name)
                if cat_id in cat_map:
                    return cat_id, cat_map[cat_id]

                # Choose an icon
                icon = "📺"
                lower_name = cat_name.lower()
                if "رياض" in cat_name or "sport" in lower_name: icon = "⚽"
                elif "خبر" in cat_name or "أخبار" in cat_name or "news" in lower_name: icon = "🔴"
                elif "سينما" in cat_name or "فيلم" in cat_name or "movie" in lower_name: icon = "🎬"
                elif "دين" in cat_name or "قرآن" in cat_name or "إسلام" in cat_name: icon = "🕋"
                elif "أطفال" in cat_name or "كرتون" in cat_name or "kid" in lower_name: icon = "🦁"

                new_cat = {"id": cat_id, "name": cat_name, "icon": icon, "api_id": str(api_id or "general")}
                categories.append(new_cat)
                cat_map[cat_id] = cat_name
                name_to_id[cat_name.lower()] = cat_id
                return cat_id, cat_name

            # Pre-populate categories if explicitly present in JSON
            if isinstance(parsed, dict) and "categories" in parsed and isinstance(parsed["categories"], list):
                for c in parsed["categories"]:
                    if isinstance(c, dict):
                        cid = c.get("id") or c.get("category_id") or c.get("slug")
                        cname = c.get("name") or c.get("category_name") or c.get("title") or cid
                        if cid and cname:
                            ensure_category(cname)

            raw_channel_list = []

            # 1. Dict with 'channels' or 'streams' or 'data'
            if isinstance(parsed, dict):
                if "channels" in parsed and isinstance(parsed["channels"], list):
                    raw_channel_list = parsed["channels"]
                elif "streams" in parsed and isinstance(parsed["streams"], list):
                    raw_channel_list = parsed["streams"]
                elif "data" in parsed:
                    if isinstance(parsed["data"], list):
                        raw_channel_list = parsed["data"]
                    elif isinstance(parsed["data"], dict) and "channels" in parsed["data"]:
                        raw_channel_list = parsed["data"]["channels"]
            # 2. List of items directly
            elif isinstance(parsed, list):
                if len(parsed) > 0 and isinstance(parsed[0], dict) and ("channels" in parsed[0] or "items" in parsed[0]):
                    for group in parsed:
                        group_cat = group.get("category") or group.get("category_name") or group.get("name") or "منوعات"
                        group_chans = group.get("channels") or group.get("items") or []
                        for ch in group_chans:
                            if isinstance(ch, dict):
                                ch["_forced_category"] = group_cat
                                raw_channel_list.append(ch)
                else:
                    raw_channel_list = parsed

            imported_count = 0
            for item in raw_channel_list:
                if not isinstance(item, dict):
                    continue

                raw_name = (
                    item.get("name") or item.get("title") or item.get("channel_name")
                    or item.get("stream_name") or item.get("label") or item.get("tvg-name")
                )
                if not raw_name:
                    continue

                url = (
                    item.get("url") or item.get("stream_url") or item.get("link")
                    or item.get("stream") or item.get("play_url") or item.get("source")
                    or item.get("direct_source") or item.get("server_url")
                )
                if not url and "servers" in item and isinstance(item["servers"], list) and len(item["servers"]) > 0:
                    url = item["servers"][0].get("url")
                if not url:
                    continue

                raw_cat = item.get("_forced_category") or item.get("category") or item.get("category_name") or item.get("cat") or item.get("group") or "منوعات"
                cat_id, cat_name = ensure_category(raw_cat)

                logo = (
                    item.get("logo") or item.get("icon") or item.get("stream_icon")
                    or item.get("image") or item.get("poster") or "📺"
                )

                item_qual = item.get("quality", "HD")
                base_name, detected_quality = self._normalize_name_and_quality(raw_name, item_qual)
                effective_quality = item_qual if item_qual and item_qual != "HD" else detected_quality

                clean_url = str(url).strip()
                lower_u = clean_url.lower()
                stream_type = "hls" if (".m3u8" in lower_u or ".php" in lower_u or ".js" in lower_u) else ("mp4" if ".mp4" in lower_u else ("ts" if ".ts" in lower_u else "hls"))

                referer = item.get("referer") or ""
                useragent = item.get("useragent") or item.get("agent") or ""
                if any(k in lower_u for k in ["maziika", "sa037", "sa047", "ostora", "uruk", "optikl"]):
                    if not referer: referer = "https://www.w2.maziikaaaaa.shop/"
                    if not useragent: useragent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

                # Check if item has embedded servers/qualities
                if "servers" in item and isinstance(item["servers"], list) and len(item["servers"]) > 0:
                    servers = item["servers"]
                    for s in servers:
                        s_u = str(s.get("url", "")).lower()
                        if any(k in s_u for k in ["maziika", "sa037", "sa047", "ostora", "uruk", "optikl"]):
                            if not s.get("referer"): s["referer"] = referer or "https://www.w2.maziikaaaaa.shop/"
                            if not s.get("useragent"): s["useragent"] = useragent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
                        else:
                            if not s.get("referer") and referer: s["referer"] = referer
                            if not s.get("useragent") and useragent: s["useragent"] = useragent
                else:
                    servers = [{
                        "name": f"جودة ({effective_quality})",
                        "quality": effective_quality,
                        "url": clean_url,
                        "type": stream_type,
                        "referer": referer,
                        "useragent": useragent
                    }]

                # Grouping check: Does a channel with this base_name already exist in this category?
                existing_ch = None
                for c in channels:
                    if c.get("category") == cat_id and (c.get("name", "").strip().lower() == base_name.lower() or c.get("url") == clean_url):
                        existing_ch = c
                        break

                if existing_ch:
                    ex_servers = existing_ch.setdefault("servers", [])
                    for s in servers:
                        s_url = s.get("url")
                        if s_url and not any(es.get("url") == s_url for es in ex_servers):
                            ex_servers.append(s)

                    curr_rank = self.QUAL_RANKS.get(existing_ch.get("quality", "HD").upper(), 3)
                    new_rank = self.QUAL_RANKS.get(effective_quality.upper(), 3)
                    if new_rank >= curr_rank:
                        existing_ch["quality"] = effective_quality
                        existing_ch["url"] = clean_url
                        existing_ch["streamUrl"] = clean_url
                    imported_count += 1
                    continue

                ch_id = item.get("id") or f"ch-php-{int(time.time())}-{imported_count}"
                new_ch = {
                    "id": str(ch_id),
                    "name": base_name,
                    "category": cat_id,
                    "categoryName": cat_name,
                    "api_id": str(api_id or "general"),
                    "currentShow": item.get("currentShow") or item.get("epg") or "بث مباشر عبر الإنترنت",
                    "logo": logo,
                    "quality": effective_quality,
                    "url": clean_url,
                    "streamUrl": clean_url,
                    "referer": referer,
                    "useragent": useragent,
                    "origin": item.get("origin") or "",
                    "cookie": item.get("cookie") or "",
                    "key": item.get("key") or "",
                    "scheme": item.get("scheme") or "",
                    "badge": "مباشر",
                    "servers": servers
                }
                channels.append(new_ch)
                imported_count += 1

            self._save_raw(data)
            return {
                "success": True,
                "channels_count": imported_count,
                "categories_count": len(categories),
                "total_channels": len(channels)
            }

    # ------------------ M3U Importer ------------------
    def sync_m3u_from_url(self, url, category="sports", category_name="قنوات رياضية", api_id=None):
        """Fetch and parse M3U playlist and add discovered channels to database with smart quality grouping."""
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=12) as response:
                content = response.read().decode("utf-8", errors="ignore")

            lines = content.splitlines()
            imported_count = 0
            current_name = ""
            current_logo = "📺"
            current_cat = category
            current_cat_name = category_name

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#EXTINF:"):
                    name_match = re.search(r',([^,]+)$', line)
                    current_name = name_match.group(1).strip() if name_match else "قناة بث مباشر"

                    logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                    current_logo = logo_match.group(1).strip() if logo_match else "📺"

                    group_match = re.search(r'group-title="([^"]+)"', line)
                    if group_match:
                        current_cat_name = group_match.group(1).strip()
                        current_cat = current_cat_name.lower().replace(" ", "_")

                elif not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
                    if current_name:
                        self.add_single_channel(
                            name=current_name,
                            url=line,
                            category_id=current_cat,
                            category_name=current_cat_name,
                            logo=current_logo,
                            api_id=api_id or "general"
                        )
                        imported_count += 1
                        current_name = ""
                        if imported_count >= 250:
                            break
            return imported_count
        except Exception as e:
            logger.error("sync_m3u_from_url error: %s", e)
            return -1

    def _parse_m3u_text(self, content, default_cat="sports", default_cat_name="قنوات رياضية"):
        lines = content.splitlines()
        imported_count = 0
        current_name = ""
        current_logo = "📺"
        current_cat = default_cat
        current_cat_name = default_cat_name

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                name_match = re.search(r',([^,]+)$', line)
                current_name = name_match.group(1).strip() if name_match else "قناة بث مباشر"

                logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                current_logo = logo_match.group(1).strip() if logo_match else "📺"

                group_match = re.search(r'group-title="([^"]+)"', line)
                if group_match:
                    current_cat_name = group_match.group(1).strip()
                    current_cat = current_cat_name.lower().replace(" ", "_")
                    current_cat = re.sub(r'[^a-zA-Z0-9_\u0600-\u06FF]', '', current_cat) or "general"

            elif not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
                if current_name:
                    self.add_single_channel(
                        name=current_name,
                        url=line,
                        category_id=current_cat,
                        category_name=current_cat_name,
                        logo=current_logo,
                        quality="HD"
                    )
                    imported_count += 1
                    current_name = ""
        return {
            "success": True,
            "type": "playlist_imported",
            "format": "m3u",
            "channels_count": imported_count,
            "total_channels": len(self.get_channels())
        }

    def process_universal_link(self, input_text, channel_name=None, category_id=None, category_name=None, logo="📺", quality="FHD"):
        """
        Universal link and raw code processor supporting:
        - m3u8 (HLS stream)
        - ts (MPEG-TS stream)
        - js (JavaScript stream link or API)
        - php (Ostora/PHP stream link or PHP API JSON)
        - json (JSON API endpoint or pasted JSON data)
        - m3u (M3U playlist link or pasted M3U text)
        """
        raw = input_text.strip()
        lower_raw = raw.lower()

        # 1. Pasted raw JSON code
        if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
            res = self.sync_php_json(raw)
            res["type"] = "api_json_imported"
            res["format"] = "json"
            return res

        # 2. Pasted raw M3U playlist text
        if "#EXTM3U" in raw or "#EXTINF:" in raw:
            return self._parse_m3u_text(raw, default_cat=category_id or "sports", default_cat_name=category_name or "قنوات رياضية")

        # 3. HTTP / HTTPS URL
        if raw.startswith("http://") or raw.startswith("https://"):
            # If channel_name is already provided, add directly as single channel
            if channel_name:
                ch = self.add_single_channel(
                    name=channel_name,
                    url=raw,
                    category_id=category_id or "general",
                    category_name=category_name,
                    logo=logo or "📺",
                    quality=quality or "FHD"
                )
                return {
                    "success": True,
                    "type": "single_channel_added",
                    "channel": ch,
                    "total_channels": len(self.get_channels()),
                    "message": f"تمت إضافة القناة {ch['name']} بنجاح في قسم {ch['categoryName']}!"
                }

            # Check if URL explicitly indicates M3U
            if ".m3u" in lower_raw and not ".m3u8" in lower_raw:
                count = self.sync_m3u_from_url(raw, category=category_id or "sports")
                return {
                    "success": True if count >= 0 else False,
                    "type": "playlist_imported",
                    "format": "m3u",
                    "channels_count": count,
                    "total_channels": len(self.get_channels())
                }

            # Attempt inspection of URL content
            try:
                req = Request(
                    raw,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                        "Accept": "*/*"
                    }
                )
                with urlopen(req, timeout=8) as resp:
                    ct = resp.headers.get("Content-Type", "").lower()
                    peek = resp.read(4096).decode("utf-8", errors="ignore")

                    if "#EXTM3U" in peek or "#EXTINF:" in peek:
                        count = self.sync_m3u_from_url(raw, category=category_id or "sports")
                        return {
                            "success": True if count >= 0 else False,
                            "type": "playlist_imported",
                            "format": "m3u",
                            "channels_count": count,
                            "total_channels": len(self.get_channels())
                        }

                    if "application/json" in ct or (peek.strip().startswith("{") or peek.strip().startswith("[")):
                        res = self.sync_php_json(raw)
                        res["type"] = "api_json_imported"
                        res["format"] = "json"
                        return res
            except Exception:
                pass

            # Detect format of single stream
            detected_fmt = "m3u8"
            if ".ts" in lower_raw:
                detected_fmt = "ts"
            elif ".php" in lower_raw:
                detected_fmt = "php"
            elif ".js" in lower_raw:
                detected_fmt = "js"
            elif ".mp4" in lower_raw:
                detected_fmt = "mp4"

            # Suggest channel name from URL if possible
            suggested_name = "قناة بث مباشر"
            if "id=" in raw:
                try:
                    qid = raw.split("id=")[1].split("&")[0]
                    suggested_name = f"قناة سبورت {qid}" if ("cat=4524" in raw or "cat=331" in raw) else f"قناة {qid}"
                except Exception:
                    pass

            return {
                "success": True,
                "type": "need_details",
                "url": raw,
                "format": detected_fmt,
                "suggested_name": suggested_name
            }

        return {
            "success": False,
            "error": "الرابط أو النص المدخل غير صالح. يرجى إرسال رابط يبدأ بـ http:// أو https:// أو لصق كود JSON أو M3U."
        }

    # ------------------ Maintenance Mode ------------------
    def get_maintenance(self):
        with _lock:
            data = self._load_raw()
            m = data.get("maintenance", {})
            return {
                "enabled": m.get("enabled", False),
                "message": m.get("message", "التطبيق تحت الصيانة حالياً، نعمل على تحسين تجربتك. يرجى المحاولة لاحقاً"),
                "image": m.get("image", ""),
                "bg_color": m.get("bg_color", "#0F0A18"),
                "theme": m.get("theme", "dark_purple"),
                "updated_at": m.get("updated_at", "")
            }

    def set_maintenance(self, enabled: bool, message=None, image=None, bg_color=None, theme=None, admin_id=None):
        with _lock:
            data = self._load_raw()
            m = data.setdefault("maintenance", {})
            m["enabled"] = bool(enabled)
            if message is not None and str(message).strip():
                m["message"] = str(message).strip()
            elif not m.get("message") or not m["message"].strip():
                m["message"] = "التطبيق تحت الصيانة حالياً، نعمل على تحسين تجربتك. يرجى المحاولة لاحقاً"
            if image is not None:
                m["image"] = str(image).strip()
            if bg_color is not None and str(bg_color).strip():
                m["bg_color"] = str(bg_color).strip()
            elif not m.get("bg_color"):
                m["bg_color"] = "#0F0A18"
            if theme is not None and str(theme).strip():
                m["theme"] = str(theme).strip()
            m["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_raw(data)

            # Verification: Re-read directly from disk
            saved_m = self._load_raw().get("maintenance", {})
            if saved_m.get("enabled") == bool(enabled):
                logger.info("Maintenance state updated to %s (message: %s, image: %s, bg: %s) by admin %s", enabled, m.get("message"), m.get("image"), m.get("bg_color"), admin_id)
                return True, saved_m
            logger.error("Maintenance persistence verification failed for admin %s", admin_id)
            return False, "فشل حفظ حالة الصيانة في قاعدة البيانات"

    # ------------------ App Update ------------------
    def get_app_update(self):
        with _lock:
            data = self._load_raw()
            return data.get("app_update", {
                "enabled": False,
                "version_code": 2,
                "version_name": "1.1",
                "download_url": "",
                "release_notes": "تحديث جديد لتطبيق A2 TV",
                "is_force": False,
                "updated_at": ""
            })

    def set_app_update(self, version_code: int, version_name: str, download_url: str, release_notes: str, is_force: bool = False, enabled: bool = True):
        with _lock:
            data = self._load_raw()
            up = data.setdefault("app_update", {})
            up["enabled"] = bool(enabled)
            up["version_code"] = int(version_code)
            up["version_name"] = str(version_name).strip()
            up["download_url"] = str(download_url).strip()
            up["release_notes"] = str(release_notes).strip()
            up["is_force"] = bool(is_force)
            up["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_raw(data)
            return True, up

    def toggle_app_update(self, enabled: bool):
        with _lock:
            data = self._load_raw()
            up = data.setdefault("app_update", {})
            up["enabled"] = bool(enabled)
            up["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_raw(data)
            return up

    # ------------------ Push Notifications ------------------
    def add_notification(self, title, message, image=None):
        with _lock:
            data = self._load_raw()
            notifs = data.setdefault("notifications", [])
            notif_id = f"notif_{int(time.time())}"
            item = {
                "id": notif_id,
                "title": str(title).strip(),
                "message": str(message).strip(),
                "image": str(image).strip() if image else "",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            notifs.insert(0, item)
            data["notifications"] = notifs[:50]
            self._save_raw(data)
            logger.info("New notification created: %s (%s)", notif_id, title)
            return True, item

    def get_notifications(self, limit=10):
        with _lock:
            data = self._load_raw()
            return data.get("notifications", [])[:limit]

    def get_latest_notification(self):
        with _lock:
            data = self._load_raw()
            notifs = data.get("notifications", [])
            return notifs[0] if notifs else None

    def delete_notification(self, notif_id):
        with _lock:
            data = self._load_raw()
            notifs = data.get("notifications", [])
            data["notifications"] = [n for n in notifs if n.get("id") != notif_id]
            self._save_raw(data)
            return True

    # ------------------ Admins & Permissions ------------------
    def get_admins(self):
        with _lock:
            data = self._load_raw()
            return data.get("admins", {})

    def is_admin(self, user_id):
        try:
            uid_int = int(user_id)
        except (ValueError, TypeError):
            uid_int = 0
        if ADMIN_ID and uid_int == ADMIN_ID:
            return True
        with _lock:
            data = self._load_raw()
            admins = data.get("admins", {})
            return str(user_id) in admins or (uid_int and str(uid_int) in admins)

    def has_permission(self, user_id, permission):
        try:
            uid_int = int(user_id)
        except (ValueError, TypeError):
            uid_int = 0
        if ADMIN_ID and uid_int == ADMIN_ID:
            return True
        with _lock:
            data = self._load_raw()
            admins = data.get("admins", {})
            admin = admins.get(str(user_id)) or admins.get(str(uid_int))
            if not admin:
                return False
            perms = admin.get("permissions", [])
            return "all" in perms or permission in perms

    def add_admin(self, user_id, name="مشرف", permissions=None):
        if permissions is None:
            permissions = ["all"]
        with _lock:
            data = self._load_raw()
            admins = data.setdefault("admins", {})
            admins[str(user_id)] = {
                "id": int(user_id),
                "name": str(name),
                "role": "admin",
                "permissions": permissions,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            self._save_raw(data)
            return admins[str(user_id)]

    def delete_admin(self, user_id):
        if ADMIN_ID and int(user_id) == ADMIN_ID:
            return False
        with _lock:
            data = self._load_raw()
            admins = data.get("admins", {})
            if str(user_id) in admins:
                del admins[str(user_id)]
                self._save_raw(data)
                return True
            return False

# Global Database Instance
db = Database()
