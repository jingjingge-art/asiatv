import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("organize_playlist", Path(__file__).parents[1] / "scripts" / "organize_playlist.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class PlaylistTests(unittest.TestCase):
    def test_recognizes_regions_and_chinese(self):
        self.assertEqual(module.classify({"name": "TVB 翡翠台", "extinf": "#EXTINF:-1,TVB 翡翠台"})[0], "🇭🇰 香港")
        self.assertEqual(module.classify({"name": "Astro AEC", "extinf": "#EXTINF:-1,Astro AEC"})[0], "🇲🇾 马来西亚")
        self.assertEqual(module.classify({"name": "CCTV-1", "extinf": "#EXTINF:-1,CCTV-1"})[0], "🇨🇳 ���国")

    def test_unclassified_language_buckets(self):
        self.assertEqual(module.classify({"name": "Mystery TV", "extinf": "#EXTINF:-1,Mystery TV"})[0], "英文其他")
        self.assertEqual(module.classify({"name": "未知台", "extinf": "#EXTINF:-1,未知台"})[0], "中文")

    def test_parses_playlist_and_chinese_group(self):
        entries = module.parse_playlist('#EXTM3U\n#EXTINF:-1,新加坡 8频道\nhttp://example.test/live\n')
        self.assertEqual(len(entries), 1)
        self.assertTrue(module.is_chinese(entries[0], "🇸🇬 新加坡"))


if __name__ == "__main__":
    unittest.main()
