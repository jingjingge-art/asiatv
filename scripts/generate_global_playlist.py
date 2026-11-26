#!/usr/bin/env python3
"""Export the Chinese/English "other" groups by the public IP country of each stream.

Only channels already in the source playlist's Chinese-other or English-other
M3U groups are included. Hostnames are resolved to public IP addresses, which
are geolocated through ip-api.com's free batch API. Channel names are not used
for country classification.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Callable

SOURCE_URL = "https://raw.githubusercontent.com/jingjingge-art/asiatv/refs/heads/main/%E4 सं"
# Keep this URL as the exact raw source requested by the repository owner.
SOURCE_URL = "https://raw.githubusercontent.com/jingjingge-art/asiatv/refs/heads/main/%E4%BA%9A%E6%B4%B2%E5%9C%B0%E5%8C%BA.m3u"
OUTPUT_PATH = Path("全球频道.txt")
GEO_API_URL = "http://ip-api.com/batch?fields=status,message,country,countryCode,query"
UNKNOWN_COUNTRY = ("未知国家", "ZZ")

# Use Chinese labels for commonly encountered countries; ip-api's English
# country name and ISO code remain the fallback so every supported country is
# still represented, rather than silently dropped.
COUNTRY_NAMES_ZH = {
    "US": "美国", "CA": "加拿大", "MX": "墨西哥", "BR": "巴西", "AR": "阿根廷",
    "CL": "智利", "CO": "哥伦比亚", "GB": "英国", "IE": "爱尔兰", "FR": "法国",
    "DE": "德国", "IT": "意大利", "ES": "西班牙", "PT": "葡萄牙", "NL": "荷兰",
    "BE": "比利时", "CH": "瑞士", "AT": "奥地利", "SE": "瑞典", "NO": "挪威",
    "DK": "丹麦", "FI": "芬兰", "IS": "冰岛", "PL": "波兰", "CZ": "捷克",
    "SK": "斯洛伐克", "HU": "匈牙利", "RO": "罗马尼亚", "BG": "保加利亚",
    "GR": "希腊", "UA": "乌克兰", "RU": "俄罗斯", "TR": "土耳其", "IL": "以色列",
    "SA": "沙特阿拉伯", "AE": "阿联酋", "IR": "伊朗", "IQ": "伊拉克",
    "EG": "埃及", "ZA": "南非", "NG": "尼日利亚", "KE": "肯尼亚", "MA": "摩洛哥",
    "IN": "印度", "PK": "巴基斯坦", "BD": "孟加拉国", "LK": "斯里兰卡",
    "NP": "尼泊尔", "JP": "日本", "KR": "韩国", "KP": "朝鲜", "CN": "中国",
    "HK": "香港", "MO": "澳门", "TW": "台湾", "SG": "新加坡", "MY": "马来西亚",
    "TH": "泰国", "VN": "越南", "PH": "菲律宾", "ID": "印度尼西亚", "KH": "柬埔寨",
    "LA": "老挝", "MM": "缅甸", "BN": "文莱", "AU": "澳大利亚", "NZ": "新西兰",
    "KZ": "哈萨克斯坦", "UZ": "乌兹别克斯坦", "AZ": "阿塞拜疆", "GE": "格鲁吉亚",
}


def read_source(source: str) -> str:
    request = urllib.request.Request(source, headers={"User-Agent": "asiatv-global-playlist/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def _other_group(group: str) -> bool:
    normalized = re.sub(r"[\s_-]+", "", group).casefold()
    return normalized in {
        "中文其他", "其他中文", "chineseother", "otherchinese",
        "英文其他", "其他英文", "englishother", "otherenglish",
    }


def parse_other_entries(text: str) -> list[dict[str, str]]:
    """Parse M3U entries, retaining only the two designated other groups."""
    entries: list[dict[str, str]] = []
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending = line
            continue
        if line.startswith("#"):
            continue
        if pending is None:
            continue
        extinf, pending = pending, None
        group_match = re.search(r'group-title\s*=\s*"([^"]*)"', extinf, re.IGNORECASE)
        if not group_match or not _other_group(group_match.group(1)):
            continue
        name = extinf.rsplit(",", 1)[-1].strip() if "," in extinf else "未命名频道"
        if name:
            entries.append({"name": name, "url": line, "group": group_match.group(1)})
    return entries


def extract_host(url: str) -> str | None:
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").casefold() if host else None


def resolve_public_ips(host: str) -> list[str]:
    """Resolve a host and return only globally routable IP addresses."""
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
        except (OSError, ValueError):
            return []
    return sorted({str(address) for address in addresses if address.is_global})


def geolocate_ips(ips: list[str]) -> dict[str, tuple[str, str]]:
    """Batch public IP lookups; free ip-api endpoint allows up to 100 per call."""
    results: dict[str, tuple[str, str]] = {}
    unique_ips = sorted(set(ips))
    for offset in range(0, len(unique_ips), 100):
        batch = unique_ips[offset:offset + 100]
        request = urllib.request.Request(
            GEO_API_URL,
            data=json.dumps(batch).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "asiatv-global-playlist/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print(f"Geolocation batch failed: {exc}", file=sys.stderr)
            payload = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict) or item.get("status") != "success":
                    continue
                code = str(item.get("countryCode") or "").upper()
                country = str(item.get("country") or "").strip()
                query = str(item.get("query") or "")
                if code and country and query:
                    results[query] = (country, code)
        # The free batch endpoint is rate-limited to 15 requests/minute.
        if offset + 100 < len(unique_ips):
            time.sleep(4.1)
    return results


def assign_countries(
    entries: list[dict[str, str]],
    resolver: Callable[[str], list[str]] = resolve_public_ips,
    geo_lookup: Callable[[list[str]], dict[str, tuple[str, str]]] = geolocate_ips,
) -> dict[tuple[str, str], list[dict[str, str]]]:
    hosts = sorted({host for entry in entries if (host := extract_host(entry["url"]))})
    host_ips = {host: resolver(host) for host in hosts}
    ip_country = geo_lookup(sorted({ip for ips in host_ips.values() for ip in ips}))
    host_country: dict[str, tuple[str, str]] = {}
    for host, ips in host_ips.items():
        host_country[host] = next((ip_country[ip] for ip in ips if ip in ip_country), UNKNOWN_COUNTRY)

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for entry in entries:
        host = extract_host(entry["url"])
        groups[host_country.get(host, UNKNOWN_COUNTRY)].append(entry)
    return dict(groups)


def format_playlist(groups: dict[tuple[str, str], list[dict[str, str]]]) -> str:
    lines = ["全球频道（按线路服务器 IP 归属地分组）", "说明：只收录源列表“中文其他”和“英文其他”分组；国家按线路域名解析到的公网 IP 判断。", ""]
    for country, code in sorted(groups, key=lambda item: (COUNTRY_NAMES_ZH.get(item[1], item[0]).casefold(), item[1])):
        display = COUNTRY_NAMES_ZH.get(code, country)
        lines.append(f"# {display} ({code})")
        for entry in groups[(country, code)]:
            lines.append(f"{entry['name']},{entry['url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    try:
        entries = parse_other_entries(read_source(SOURCE_URL))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"Cannot read source playlist: {exc}", file=sys.stderr)
        return 2
    if not entries:
        print("No channels found in the Chinese-other or English-other M3U groups.", file=sys.stderr)
        return 2
    groups = assign_countries(entries)
    OUTPUT_PATH.write_text(format_playlist(groups), encoding="utf-8")
    print(f"Wrote {len(entries)} channels in {len(groups)} IP-country groups to {OUTPUT_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
