import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("organize_playlist", Path(__file__).parents[1] / "scripts" / "organize_playlist.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class PlaylistTests(unittest.TestCase):
    def test_parses_source_repo_format(self):
        entries = module.parse_playlist("1| 源频道,#genre#\n2| CCTV1[1080],http://example.test/cctv\n3| Astro AEC,https://example.test/astro\n")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["name"], "CCTV1[1080]")
        self.assertEqual(entries[0]["url"], "http://example.test/cctv")

    def test_parses_m3u(self):
        entries = module.parse_playlist("#EXTM3U\n#EXTINF:-1,TVB 翡翠台\nhttps://example.test/tvb.m3u8\n")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "TVB 翡翠台")

    def test_region_and_chinese_recognition(self):
        self.assertEqual(module.classify({"name": "TVB 翡翠台", "extinf": "#EXTINF:-1,TVB 翡翠台"})[0], "🇭🇰 香港")
        self.assertEqual(module.classify({"name": "Astro AEC", "extinf": "#EXTINF:-1,Astro AEC"})[0], "🇲🇾 马来西亚")
        self.assertEqual(module.classify({"name": "CCTV-1", "extinf": "#EXTINF:-1,CCTV-1"})[0], "🇨🇳 中国")
        self.assertEqual(module.classify({"name": "VTV1", "extinf": "#EXTINF:-1,VTV1"})[0], "🇻🇳 越南")
        self.assertTrue(module.is_chinese({"name": "新加坡 8频道", "extinf": "#EXTINF:-1,新加坡 8频道"}))

    def test_unclassified_language_buckets(self):
        self.assertEqual(module.classify({"name": "Mystery TV", "extinf": "#EXTINF:-1,Mystery TV"})[0], "英文其他")
        self.assertEqual(module.classify({"name": "未知台", "extinf": "#EXTINF:-1,未知台"})[0], "中文")

    def test_writes_groups_as_valid_extinf_url_pairs(self):
        entry = {"name": "CCTV1", "extinf": "#EXTINF:-1,CCTV1", "url": "https://example.test/live"}
        groups = {"🇨🇳 中国": {"总台/全国": [entry]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.m3u"
            counts = module.write_groups(groups, path, "test")
            output = path.read_text(encoding="utf-8")
        self.assertEqual(counts["🇨🇳 中国 - 总台/全国"], 1)
        self.assertIn('group-title="🇨🇳 中国 - 总台/全国"', output)
        self.assertIn("https://example.test/live", output)


if __name__ == "__main__":
    unittest.main()
