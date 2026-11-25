#!/usr/bin/env python3
"""Build country/region and Chinese-channel playlists from common IPTV formats.

Accepted inputs: M3U (#EXTINF followed by URL) and the pipe/comma format used
by iptv_all.txt (optionally with a numeric prefix, e.g. ``12| Name,URL``).
Classification is based on channel names/metadata only; stream URLs are never
probed and are copied unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SOURCE_URL = "https://raw.githubusercontent.com/jingjingge-art/iptv/refs/heads/main/iptv_all.txt"

# Specific regions first. Chinese names and locally popular broadcaster brands
# are included alongside the country name so that unlabeled feeds are found.
COUNTRIES: dict[str, list[str]] = {
    "🇭🇰 香港": ["香港", "港台", "hong kong", "hongkong", "tvb", "翡翠台", "明珠台", "凤凰卫视", "鳳凰衛視", "凤凰中文", "鳳凰中文", "now tv", "viu tv", "now香港"],
    "🇲🇴 澳门": ["澳门", "澳門", "macau", "macao", "澳视", "澳視", "澳门电视", "澳門電視"],
    "🇹🇼 台湾": ["台湾", "台灣", "taiwan", "中视", "中視", "华视", "華視", "台视", "台視", "民视", "民視", "公视", "公視", "东森", "東森", "三立", "中天", "年代", "纬来", "緯來", "TVBS", "非凡", "客家电视", "客家電視"],
    "🇸🇬 新加坡": ["新加坡", "singapore", "mediacorp", "channel 5", "channel 8", "channel u", "suria", "vasantham", "okto", "cna", "八频道", "8频道", "8頻道"],
    "🇲🇾 马来西亚": ["马来西亚", "馬來西亞", "malaysia", "astro", "ntv7", "8tv", "tv9", "didik tv", "bernama", "awani", "tonton", "八度空间", "八度空間", "爱 fm", "愛 fm"],
    "🇻🇳 越南": ["越南", "vietnam", "vtv", "htv", "vtc", "sctv", "thvl", "vĩnh long", "vinh long", "hanoi tv", "hcm tv", "越南语", "越南語"],
    "🇵🇭 菲律宾": ["菲律宾", "菲律賓", "pilipinas", "philippines", "gma", "abs-cbn", "abscbn", "one news", "ptv", "net 25", "rptv", "dzrh", "kapamilya", "kapuso"],
    "🇮🇩 印度尼西亚": ["印度尼西亚", "印尼", "indonesia", "rcti", "indosiar", "trans tv", "trans7", "mnctv", "net tv", "tvone", "kompas tv", "metro tv", "antv"],
    "🇰🇭 柬埔寨": ["柬埔寨", "cambodia", "khmer", "bayon", "ctn", "cambodian", "apsara tv"],
    "🇲🇲 缅甸": ["缅甸", "緬甸", "myanmar", "burma", "mrtv", "mrtv-4", "channel 7 myanmar", "mahar", "fortune tv", "မြန်မာ"],
    "🇹🇭 泰国": ["泰国", "泰國", "thailand", "ช่อง", "ch3", "ch5", "ch7", "ch8", "one31", "gmm25", "workpoint", "pptv", "thairath", "mono 29", "mcot", "อมรินทร์"],
    "🇧🇳 文莱": ["文莱", "汶萊", "brunei", "rtb", "sukmaindera"],
}

# Provinces, autonomous regions and municipalities; these are used to make
# mainland China groups granular. City-level identifiers cover common feeds.
CHINA_REGIONS: dict[str, list[str]] = {
    "北京": ["北京", "beijing", "bjws"], "天津": ["天津", "tianjin", "tjws"],
    "上海": ["上海", "shanghai", "东方卫视", "東方衛視", "dfws"], "重庆": ["重庆", "重慶", "chongqing"],
    "河北": ["河北", "hebei"], "山西": ["山西", "shanxi"], "辽宁": ["辽宁", "遼寧", "liaoning"],
    "吉林": ["吉林", "jilin"], "黑龙江": ["黑龙江", "黑龍江", "heilongjiang"],
    "江苏": ["江苏", "江蘇", "jiangsu"], "浙江": ["浙江", "zhejiang"], "安徽": ["安徽", "anhui"],
    "福建": ["福建", "fujian", "东南卫视", "東南衛視"], "江西": ["江西", "jiangxi"],
    "山东": ["山东", "山東", "shandong"], "河南": ["河南", "henan"], "湖北": ["湖北", "hubei"],
    "湖南": ["湖南", "hunan"], "广东": ["广东", "廣東", "guangdong", "深圳", "shenzhen", "珠江"],
    "海南": ["海南", "hainan", "三沙"], "四川": ["四川", "sichuan"], "贵州": ["贵州", "貴州", "guizhou"],
    "云南": ["云南", "雲南", "yunnan"], "陕西": ["陕西", "陝西", "shaanxi"], "甘肃": ["甘肃", "甘肅", "gansu"],
    "青海": ["青海", "qinghai"], "台湾": ["台湾", "台灣", "taiwan"], "内蒙古": ["内蒙古", "內蒙古", "neimenggu"],
    "广西": ["广西", "廣西", "guangxi"], "西藏": ["西藏", "tibet"], "宁夏": ["宁夏", "寧夏", "ningxia"],
    "新疆": ["新疆", "xinjiang"],
}
CHINA_NATIONAL_TERMS = ["中国", "中國", "中国大陆", "大陆", "china", "cctv", "央视", "中央电视", "中央電視", "cctv4k"]
CHINESE_TERMS = [
    "中文", "国语", "國語", "普通话", "普通話", "粤语", "粵語", "华语", "華語", "mandarin", "cantonese",
    "中文台", "中文频道", "中文頻道", "凤凰中文", "鳳凰中文", "凤凰资讯", "鳳凰資訊", "凤凰卫视", "鳳凰衛視",
    "翡翠台", "本港台", "TVB", "中视", "中視", "华视", "華視", "台视", "台視", "民视", "民視", "公视", "公視",
    "中天", "东森", "東森", "三立", "TVBS", "八度空间", "八度空間", "Astro AEC", "CCTV", "CGTN",
    "湖南卫视", "湖南衛視", "浙江卫视", "浙江衛視", "江苏卫视", "江蘇衛視", "东方卫视", "東方衛視",
    "广东卫视", "廣東衛視", "北京卫视", "北京衛視",
]


def _contains(text: str, terms: Iterable[str]) -> bool:
    """Substring match for CJK terms, word match for Latin brand names."""
    folded = text.casefold()
    for term in terms:
        candidate = term.casefold()
        if any("\u4e00" <= char <= "\u9fff" for char in candidate):
            if candidate in folded:
                return True
        else:
            # Keep short Latin marks such as TVB/CNA from matching inside words.
            if re.search(r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])", folded):
                return True
    return False


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def read_input(path_or_url: str) -> str:
    if path_or_url.startswith(("https://", "http://")):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "asiatv-playlist-organizer/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read().decode("utf-8-sig", errors="replace")
    return Path(path_or_url).read_text(encoding="utf-8-sig", errors="replace")


def parse_playlist(text: str) -> list[dict[str, str]]:
    """Parse M3U or iptv_all.txt (number|name,url) into channel entries."""
    entries: list[dict[str, str]] = []
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending = line
            continue
        if line.startswith("#") or line.endswith("#genre#"):
            continue
        if pending is not None:
            extinf = pending
            name = pending.rsplit(",", 1)[-1].strip() if "," in pending else "Unnamed"
            entries.append({"extinf": extinf, "name": name, "url": line})
            pending = None
            continue

        # Source text uses entries like ``123| Channel name,https://...``.
        if "|" in line:
            _, line = line.split("|", 1)
            line = line.strip()
        if "," not in line:
            continue
        name, url = line.split(",", 1)
        name, url = name.strip(), url.strip()
        if not name or not url or url.lower().endswith("#genre#"):
            continue
        entries.append({"extinf": f"#EXTINF:-1,{name}", "name": name, "url": url})
    return entries


def classify(entry: dict[str, str]) -> tuple[str, str]:
    name = entry["name"]
    text = f"{name} {entry['extinf']}"
    for country, terms in COUNTRIES.items():
        if _contains(text, terms):
            return country, country
    for region, terms in CHINA_REGIONS.items():
        if _contains(text, terms):
            return "🇨🇳 中国", region
    if _contains(text, CHINA_NATIONAL_TERMS):
        return "🇨🇳 中国", "总台/全国"
    if _has_cjk(name):
        return "中文", "其他中文"
    if re.search(r"[A-Za-z]", name):
        return "英文其他", "英文其他"
    return "其他", "其他"


def is_chinese(entry: dict[str, str]) -> bool:
    return _has_cjk(entry["name"]) or _contains(f"{entry['name']} {entry['extinf']}", CHINESE_TERMS)


def write_groups(groups: dict[str, dict[str, list[dict[str, str]]]], path: Path, title: str) -> dict[str, int]:
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    counts: dict[str, int] = {}
    for country, subgroups in groups.items():
        for subgroup, items in subgroups.items():
            group_title = country if subgroup == country else f"{country} - {subgroup}"
            counts[group_title] = len(items)
            for item in items:
                extinf = item["extinf"]
                if "group-title=" in extinf:
                    extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group_title}"', extinf, count=1)
                else:
                    extinf = re.sub(r"^#EXTINF:(-?\d+)", rf'#EXTINF:\1 group-title="{group_title}"', extinf, count=1)
                lines.extend((extinf, item["url"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=SOURCE_URL, help="M3U/text playlist URL or local file")
    parser.add_argument("--output-dir", default=".", help="directory for generated playlists")
    args = parser.parse_args()
    try:
        entries = parse_playlist(read_input(args.source))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"Cannot read playlist: {exc}", file=sys.stderr)
        return 2
    if not entries:
        print("No channels found. Expected M3U #EXTINF/URL pairs or name,URL lines.", file=sys.stderr)
        return 2

    regional: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    chinese: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        country, subgroup = classify(entry)
        regional[country][subgroup].append(entry)
        if is_chinese(entry):
            chinese[country][subgroup].append(entry)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "source": args.source,
        "total_channels": len(entries),
        "regional_groups": write_groups(regional, output_dir / "亚洲地区.m3u", "亚洲地区频道"),
        "chinese_groups": write_groups(chinese, output_dir / "中文频道.m3u", "亚洲中文频道"),
    }
    (output_dir / "分类报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Processed {len(entries)} channels. Wrote 亚洲地区.m3u, 中文频道.m3u, 分类报告.json to {output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
