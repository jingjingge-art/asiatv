import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "generate_global_playlist", Path(__file__).parents[1] / "scripts" / "generate_global_playlist.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class GlobalPlaylistTests(unittest.TestCase):
    def test_selects_only_chinese_other_and_english_other_groups(self):
        source = '''#EXTM3U
#EXTINF:-1 group-title="中文 - 其他中文",中文台
https://192.0.2.1/cn
#EXTINF:-1 group-title="英文其他",Mystery TV
https://192.0.2.2/en
#EXTINF:-1 group-title="🇯🇵 日本",Channel JP
https://192.0.2.3/jp
'''
        entries = module.parse_other_entries(source)
        self.assertEqual([entry["name"] for entry in entries], ["中文台", "Mystery TV"])

    def test_extract_host_handles_ipv4_ipv6_and_bad_urls(self):
        self.assertEqual(module.extract_host("https://Example.COM:8443/live"), "example.com")
        self.assertEqual(module.extract_host("http://[2001:db8::1]:8080/live"), "2001:db8::1")
        self.assertIsNone(module.extract_host("not a url"))

    def test_groups_by_resolved_ip_country_not_channel_name(self):
        entries = [
            {"name": "日本频道", "url": "https://one.example/live"},
            {"name": "美国频道", "url": "https://two.example/live"},
        ]
        groups = module.assign_countries(
            entries,
            resolver=lambda host: {"one.example": ["203.0.113.1"], "two.example": ["203.0.113.2"]}[host],
            geo_lookup=lambda ips: {"203.0.113.1": ("Japan", "JP"), "203.0.113.2": ("United States", "US")},
        )
        self.assertEqual(groups[("Japan", "JP")][0]["name"], "日本频道")
        self.assertEqual(groups[("United States", "US")][0]["name"], "美国频道")

    def test_output_is_country_grouped_text_with_name_and_url(self):
        output = module.format_playlist({("United States", "US"): [{"name": "News", "url": "https://example.test/live"}]})
        self.assertIn("# 美国 (US)", output)
        self.assertIn("News,https://example.test/live", output)


if __name__ == "__main__":
    unittest.main()
