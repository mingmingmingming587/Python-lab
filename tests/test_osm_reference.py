import tempfile
import unittest
from pathlib import Path

from visualization.osm_reference import lines_for_ways, read_osm
from visualization.apk_places import load_apk_places, gcj02_to_wgs84_approx


class OSMReferenceTests(unittest.TestCase):
    def test_apk_place_parser_and_approximate_conversion(self):
        sample = "r = {'id': 'builtin-demo', 'name': '示例入口', 'longitude': 116.404, 'latitude': 39.915};"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.txt"
            path.write_text(sample, encoding="utf-8")
            self.assertEqual(load_apk_places(path), [("示例入口", 116.404, 39.915)])
        lon, lat = gcj02_to_wgs84_approx(116.404, 39.915)
        self.assertAlmostEqual(lon, 116.397755, places=4)
        self.assertAlmostEqual(lat, 39.913596, places=4)
        self.assertEqual(gcj02_to_wgs84_approx(0.0, 0.0), (0.0, 0.0))

    def test_reads_way_and_breaks_on_missing_node(self):
        xml = '''<osm><node id="1" lon="116.1" lat="39.1"/>
        <node id="2" lon="116.2" lat="39.2"/>
        <way id="9"><nd ref="1"/><nd ref="missing"/><nd ref="2"/>
        <tag k="highway" v="service"/></way></osm>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.osm"
            path.write_text(xml, encoding="utf-8")
            nodes, ways, _ = read_osm(path)
            self.assertEqual(ways["9"]["tags"]["highway"], "service")
            x, y = lines_for_ways(nodes, ways, ["9"])
            self.assertEqual(x, [116.1, None, 116.2, None])
            self.assertEqual(y, [39.1, None, 39.2, None])


if __name__ == "__main__":
    unittest.main()
