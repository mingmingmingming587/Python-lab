import unittest
import json
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import database.store as store


class NavigationTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory())
        self.db = Path(temporary) / "test.db"
        self.list_routes = partial(store.list_routes, db_path=self.db)
        self.load_map = partial(store.load_map, db_path=self.db)
        for name in ("init_database", "load_map", "save_grid", "save_route", "add_place", "update_place", "delete_place", "list_routes", "replace_map"):
            original = getattr(store, name)
            self.enterContext(patch.object(store, name, partial(original, db_path=self.db)))

    def click(self, app, label):
        return next(button for button in app.button if button.label == label).click().run()

    def test_place_management_and_history_page(self):
        root = Path(__file__).resolve().parents[1]
        management = AppTest.from_file(str(root / "pages" / "1_地图管理.py"), default_timeout=15).run()
        management.text_input[0].input("模拟新入口")
        management.number_input[0].set_value(1)
        management.number_input[1].set_value(2)
        self.click(management, "添加")
        self.assertIn("模拟新入口", self.load_map()["places"])
        management.selectbox[0].select("模拟新入口").run()
        management.checkbox[0].check().run()
        self.click(management, "删除地点")
        self.assertNotIn("模拟新入口", self.load_map()["places"])
        self.assertFalse(management.exception)

        navigation = AppTest.from_file(str(root / "pages" / "2_智能导航.py"), default_timeout=15).run()
        self.click(navigation, "开始 A* 搜索")
        history = AppTest.from_file(str(root / "pages" / "4_历史记录.py"), default_timeout=15).run()
        self.assertEqual(len(history.expander), 1)
        self.assertIn("模拟教学楼入口", history.expander[0].label)
        self.assertFalse(history.exception)

    def test_map_save_reload_and_history_snapshot(self):
        page = Path(__file__).resolve().parents[1] / "pages" / "2_智能导航.py"
        app = AppTest.from_file(str(page), default_timeout=15).run()
        self.click(app, "设置为障碍物")
        self.click(app, "开始 A* 搜索")
        self.assertFalse(self.list_routes()[0]["found"])
        self.assertEqual(self.list_routes()[0]["grid_snapshot"][3][4], 1)
        self.click(app, "保存地图")
        self.assertEqual(self.load_map()["grid"][3][4], 1)
        restarted = AppTest.from_file(str(page), default_timeout=15).run()
        self.assertEqual(restarted.session_state["grid"][3][4], 1)
        self.assertEqual(self.list_routes()[0]["grid_snapshot"][3][4], 1)
        self.assertFalse(restarted.exception)

    def test_search_replay_and_reset(self):
        page = Path(__file__).resolve().parents[1] / "pages" / "2_智能导航.py"
        app = AppTest.from_file(str(page), default_timeout=15).run()
        self.click(app, "开始 A* 搜索")
        self.assertEqual(len(self.list_routes()), 1)
        total = int(app.slider[0].max)
        self.assertEqual(app.slider[0].value, total)

        app.slider[0].set_value(0).run()
        self.assertEqual(len(self.list_routes()), 1)
        traces = json.loads(app.get("plotly_chart")[0].proto.spec)["data"]
        self.assertNotIn("已扩展节点", [t.get("name") for t in traces])
        self.assertNotIn("A* 路径", [t.get("name") for t in traces])

        app.slider[0].set_value(1).run()
        traces = json.loads(app.get("plotly_chart")[0].proto.spec)["data"]
        visited = next(t for t in traces if t.get("name") == "已扩展节点")
        self.assertEqual(len(visited["x"]), 1)
        self.assertNotIn("A* 路径", [t.get("name") for t in traces])

        app.slider[0].set_value(total).run()
        traces = json.loads(app.get("plotly_chart")[0].proto.spec)["data"]
        self.assertIn("A* 路径", [t.get("name") for t in traces])

        app.slider[0].set_value(0).run()
        self.click(app, "开始 A* 搜索")
        self.assertEqual(app.slider[0].value, total)
        self.click(app, "设置为障碍物")
        self.assertEqual(len(app.slider), 0)
        self.click(app, "开始 A* 搜索")
        self.assertTrue(any("没有可行路线" in item.value for item in app.warning))
        self.assertGreater(app.slider[0].value, 0)
        self.assertFalse(app.exception)

    def test_search_edit_and_same_point(self):
        page = Path(__file__).resolve().parents[1] / "pages" / "2_智能导航.py"
        app = AppTest.from_file(str(page), default_timeout=15).run()
        self.assertFalse(app.exception)
        self.click(app, "开始 A* 搜索")
        self.assertFalse(app.exception)
        self.assertTrue(any("已找到" in item.value for item in app.success))

        # 默认选择 (3, 4)，它连接模拟地图的左右两侧。
        self.click(app, "设置为障碍物")
        self.assertFalse(any("已找到" in item.value for item in app.success))
        self.click(app, "开始 A* 搜索")
        self.assertTrue(any("没有可行路线" in item.value for item in app.warning))

        app.selectbox[1].select("模拟教学楼入口").run()
        self.click(app, "开始 A* 搜索")
        self.assertTrue(any(item.value == "0 步" for item in app.metric))
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
