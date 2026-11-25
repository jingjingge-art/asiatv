#!/usr/bin/env python3
"""Classify an M3U playlist into regional and Chinese-language playlists.

This uses playlist metadata and channel-name keywords only. It never probes
streams; source URLs are copied as-is.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SOURCE_URL = "https://raw.githubusercontent.com/jingjingge-art/iptv/refs/heads/main/iptv_all.txt"

# Order matters: more specific regions (HK/MO/TW) precede mainland China.
COUNTRIES = {
    "🇭🇰 香港": ["香港", "港", "hong kong", "hongkong", "tvb", "翡翠台", "明珠台", "港台", "凤凰", "鳳凰", "now tv", "viu tv"],
    "🇲🇴 澳门": ["澳门", "澳門", "macau", "macao", "澳视", "澳視"],
    "🇹🇼 台湾": ["台湾", "台灣", "taiwan", "中视", "中視", "华视", "華視", "台视", "台視", "民视", "民視", "公视", "公視", "年代", "东森", "東森", "三立", "中天", "八大", "壹电视", "壹電視", "纬来", "緯來", "TVBS", "非凡", "客家电视", "客家電視"],
    "🇸🇬 新加坡": ["新加坡", "singapore", "mediacorp", "channel 5", "channel 8", "channel u", "suria", "vasantham", "okto", "cna"],
    "🇲🇾 马来西亚": ["马来西亚", "馬來西亞", "malaysia", "astro", "tv1", "tv2", "tv3", "ntv7", "8tv", "tv9", "didik tv", "bernama", "awani", "tonton"],
    "🇻🇳 越南": ["越南", "vietnam", "vtv", "htv", "vtc", "sctv", "thvl", "vĩnh long", "vinh long", "hanoi tv", "hcm tv"],
    "🇵🇭 菲律宾": ["菲律宾", "菲律賓", "pilipinas", "philippines", "gma", "abs-cbn", "abscbn", "tv5", "one news", "ptv", "net 25", "rptv", "dzrh"],
    "🇮🇩 印度尼西亚": ["印度尼西亚", "印尼", "indonesia", "rcti", "sctv", "indosiar", "antv", "trans tv", "trans7", "mnctv", "net tv", "tvone", "kompas tv", "metro tv"],
    "🇰🇭 柬埔寨": ["柬埔寨", "cambodia", "khmer", "bayon", "b tv", "ctn", "cambodian"],
    "🇲🇲 缅甸": ["缅甸", "緬甸", "myanmar", "burma", "mrtv", "mrtv-4", "channel 7 myanmar", "mahar", "fortune tv"],
    "🇹🇭 泰国": ["泰国", "泰國", "thailand", "thai", "ช่อง", "ch3", "ch5", "ch7", "ch8", "one31", "gmm25", "workpoint", "pptv", "thairath", "mono 29", "mcot"],
    "🇧🇳 文莱": ["文莱", "汶萊", "brunei", "rtb", "prima", "sukmaindera"],
}

CHINA_TERMS = ["中国", "中国大陆", "大陆", "china", "cctv", "央视", "中央电视", "中央電視", "北京卫视", "北京衛視", "东方卫视", "東方衛視", "湖南卫视", "湖南衛視", "浙江卫视", "浙江衛視", "江苏卫视", "江苏衛視", "广东卫视", "廣東衛視", "山东卫视", "山东衛視", "河南卫视", "四川卫视", "深圳卫视", "重庆卫视"]
PROVINCES = {
    "北京": ["北京", "b tv"], "天津": ["天津"], "上海": ["上海", "东方卫视", "東方衛視"], "重庆": ["重庆", "重慶"],
    "河北": ["河北"], "山西": ["山西"], "辽宁": ["辽宁", "遼寧"], "吉林": ["吉林"], "黑龙江": ["黑龙江", "黑龍江"],
    "江苏": ["江苏", "江蘇"], "浙江": ["浙江"], "安徽": ["安徽"], "福建": ["福建"], "江西": ["江西"], "山东": ["山东", "山東"],
    "河南": ["河南"], "湖北": ["湖北"], "湖南": ["湖南"], "广东": ["广东", "廣東", "深圳", "珠江"], "海南": ["海南"],
    "四川": ["四川"], "贵州": ["贵州", "貴州"], "云南": ["云南", "雲南"], "陕西": ["陕西", "陝西"], "甘肃": ["甘肃", "甘肅"],
    "青海": ["青海"], "台湾": ["台湾", "台灣"], "内蒙古": ["内蒙古", "內蒙古"], "广西": ["广西", "廣西"], "西藏": ["西藏"], "宁夏": ["宁夏", "寧夏"], "新疆": ["新疆"],
}
# Commonly identifiable Chinese-language channel labels. This intentionally
# favors explicit language markers and known Mandarin/Cantonese brands to avoid
# treating every foreign channel as Chinese just because metadata has CJK text.
CHINESE_TERMS = ["中文", "国语", "國語", "普通话", "普通話", "粤语", "粵語", "华语", "華語", "mandarin", "cantonese", "中文台", "中文频道", "中文頻道", "凤凰中文", "鳳凰中文", "凤凰资讯", "鳳凰資訊", "凤凰卫视", "鳳凰衛視", "翡翠台", "本港台", "TVB", "中视", "中視", "华视", "華視", "台视", "台視", "民视", "民視", "公视", "公視", "中天", "东森", "東森", "三立", "TVBS", "八度空间", "八度空間", "Astro AEC", "TV1", "TV2", "CCTV", "CGTN", "湖南卫视", "湖南衛視", "浙江卫视", "浙江衛視", "江苏卫视", "江苏衛視", "东方卫视", "東方衛視", "广东卫视", "廣東衛視", "北京卫视", "北京衛視"]


def read_input(path_or_url: str) -> str:
    if path_or_url.startswith(("https://", "http://")):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "asiatv-playlist-organizer/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read().decode("utf-8-sig", errors="replace")
    return Path(path_or_url).read_text(encoding="utf-8-sig", errors="replace")


def parse_playlist(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF"):
            pending = line
        elif line and not line.startswith("#") and pending is not None:
            name = pending.rsplit(",", 1)[-1].strip() if "," in pending else "Unnamed"
            entries.append({"extinf": pending, "name": name, "url": line})
            pending = None
    return entries


def matches(text: str, terms: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def classify(entry: dict[str, str]) -> tuple[str, str]:
    name = entry["name"]
    metadata = entry["extinf"]
    text = f"{name} {metadata}"
    for country, terms in COUNTRIES.items():
        if matches(text, terms):
            return country, country
    if matches(text, CHINA_TERMS):
        for province, terms in PROVINCES.items():
            if matches(text, terms):
                return "🇨🇳 中国", province
        return "🇨🇳 中国", "其他"
    if any("\u4e00" <= char <= "\u9fff" for char in name):
        return "中文", "其他中文"
    if re.search(r"[A-Za-z]", name):
        return "英文其他", "英文其他"
    return "其他", "其他"


def is_chinese(entry: dict[str, str], country: str) -> bool:
    text = f"{entry['name']} {entry['extinf']}"
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in entry["name"])
    return has_cjk or matches(text, CHINESE_TERMS)


def m3u(entries: list[dict[str, str]], title: str) -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    for item in entries:
        lines.extend((item["extinf"], item["url"]))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=SOURCE_URL, help="M3U/text playlist URL or local file")
    parser.add_argument("--output-dir", default=".", help="directory for generated playlists")
    args = parser.parse_args()
    try:
        entries = parse_playlist(read_input(args.source))
    except (OSError, ValueError) as exc:
        print(f"Cannot read playlist: {exc}", file=sys.stderr)
        return 2
    if not entries:
        print("No #EXTINF/URL pairs found; refusing to write empty playlists.", file=sys.stderr)
        return 2

    regional: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    chinese: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    report = {"source": args.source, "total_channels": len(entries), "regional_groups": {}, "chinese_groups": {}}
    for entry in entries:
        country, subgroup = classify(entry)
        regional[country][subgroup].append(entry)
        if is_chinese(entry, country):
            chinese[country][subgroup].append(entry)

    def flatten(groups: dict[str, dict[str, list[dict[str, str]]]]) -> list[dict[str, str]]:
        result = []
        for country, subgroups in groups.items():
            result.append({"extinf": f'#EXTINF:-1 group-title="{country}",{country}', "url": "", "name": country})
            for subgroup, items in subgroups.items():
                title = f"{country} - {subgroup}" if subgroup != country else country
                for item in items:
                    extinf = item["extinf"]
                    # Replace group-title while preserving the original metadata.
                    if "group-title=" in extinf:
                        extinf = re.sub(r'group-title="[^"]*"', f'group-title="{title}"', extinf, count=1)
                    else:
                        extinf = extinf.replace("#EXTINF:", f'#EXTINF:-1 group-title="{title}" ', 1)
                    result.append({**item, "extinf": extinf})
                    report_key = title
                    target = report["regional_groups"] if groups is regional else report["chinese_groups"]
                    target[report_key] = target.get(report_key, 0) + 1
        return result

    # Do not include decorative group header rows in the M3U: IPTV clients use
    # group-title metadata and some clients treat rows without URLs as invalid.
    def write_groups(groups: dict[str, dict[str, list[dict[str, str]]]], path: Path, title: str, report_key: str) -> None:
        output = ["#EXTM3U", f"#PLAYLIST:{title}"]
        for country, subgroups in groups.items():
            for subgroup, items in subgroups.items():
                group_title = country if subgroup == country else f"{country} - {subgroup}"
                report[report_key][group_title] = len(items)
                for item in items:
                    extinf = item["extinf"]
                    if "group-title=" in extinf:
                        extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group_title}"', extinf, count=1)
                    else:
                        extinf = re.sub(r"^#EXTINF:(-?\d+)", rf'#EXTINF:\1 group-title="{group_title}"', extinf, count=1)
                    output.extend((extinf, item["url"]))
        path.write_text("\n".join(output) + "\n", encoding="utf-8")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_groups(regional, output_dir / "亚洲地区.m3u", "亚洲地区频道", "regional_groups")
    write_groups(chinese, output_dir / "中文频道.m3u", "亚洲中文频道", "chinese_groups")
    (output_dir / "分类报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Processed {len(entries)} channels. Wrote 亚洲地区.m3u, 中文频道.m3u, 分类报告.json to {output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
