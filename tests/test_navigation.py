import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.campus_project import CampusMapService
from database.pdf_map import initial_pdf_state
from tests.test_pdf_map import pdf_fixture


class NavigationTests(unittest.TestCase):
    def test_product_navigation(self):
        root = Path(__file__).resolve().parents[1]
        temporary = self.enterContext(TemporaryDirectory())
        db = Path(temporary) / "pdf.db"
        layout = pdf_fixture()
        service = CampusMapService(initial_pdf_state(layout), db)
        with patch("database.pdf_map.open_pdf_project", side_effect=lambda: (layout, service, *service.load())):
            app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertIn("校园地图导航", [title.value for title in app.title])
            width = next(slider for slider in app.slider if slider.label == "左侧宽度（%）")
            self.assertEqual((width.min, width.max, width.value), (25, 33, 25))
            width.set_value(33).run()
            app.switch_page("pages/map_management.py").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["control_width"], 33)
            self.assertTrue(any(button.label == "保存网格修改" for button in app.button))
            app.switch_page("pages/route_history.py").run()
            self.assertFalse(app.exception)
            self.assertIn("路线记录", [title.value for title in app.title])
