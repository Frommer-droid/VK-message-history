"""Проверки сохранности файлов при конвертации истории."""

import runpy
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.theme import DERIVED_COLORS, THEME_COLORS, apply_theme


APP = runpy.run_path(str(Path(__file__).resolve().parents[1] / "process_all_vk.pyw"), run_name="test_app")
ChatProcessor = APP["ChatProcessor"]
ChatConverterGUI = APP["ChatConverterGUI"]


def write_message(path: Path, body: str) -> None:
    markup = (
        '<div class="message"><div class="message__header">'
        'Аня 1 января 2025 в 12:00:00</div><div>' + body + '</div></div>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(markup.encode("cp1251"))


class ConversionSafetyTests(unittest.TestCase):
    def test_one_dark_theme_and_button_roles(self):
        app = QApplication.instance() or QApplication([])
        apply_theme(app)
        window = ChatConverterGUI()
        self.assertEqual(window.styleSheet(), "")
        self.assertEqual(window.remove_selected_btn.objectName(), "danger_btn")
        self.assertEqual(window.clear_list_btn.objectName(), "danger_btn")
        self.assertEqual(window.start_button.objectName(), "start_btn")
        self.assertIn("v1.1.0", window.about_text.toPlainText())
        self.assertNotIn("universal_python_desktop_guide", window.about_text.toPlainText())
        used_colors = set(re.findall(r"#[0-9A-Fa-f]{6}", app.styleSheet()))
        self.assertTrue(used_colors)
        self.assertTrue(used_colors.issubset(set(THEME_COLORS.values()) | set(DERIVED_COLORS.values())))
        self.assertNotIn("#17212B", app.styleSheet())
        window.deleteLater()

    def test_existing_intermediate_and_output_files_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "messages1.html"
            write_message(source, "Новое сообщение")
            existing_txt = root / "messages1.txt"
            existing_html = root / "conversation_chat_view.html"
            existing_css = root / "style_chat_view.css"
            for path in (existing_txt, existing_html, existing_css):
                path.write_text("Сохранить", encoding="utf-8")

            self.assertTrue(ChatProcessor(lambda *_: None).run([str(source)], str(root), True))

            for path in (existing_txt, existing_html, existing_css):
                self.assertEqual(path.read_text(encoding="utf-8"), "Сохранить")
            self.assertEqual(list(root.glob("messages1_*.txt")), [])
            generated = list(root.glob("conversation_chat_view*.html"))
            self.assertEqual(len(generated), 2)
            new_html = next(p for p in generated if p != existing_html)
            self.assertIn("Новое сообщение", new_html.read_text(encoding="utf-8"))
            self.assertIn("style_chat_view_2.css", new_html.read_text(encoding="utf-8"))
            self.assertTrue((root / "style_chat_view_2.css").exists())

    def test_equal_basenames_from_different_folders_both_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first" / "messages1.html"
            second = root / "second" / "messages1.html"
            write_message(first, "Первое")
            write_message(second, "Второе")

            self.assertTrue(ChatProcessor(lambda *_: None).run([str(first), str(second)], str(root), True))

            output = (root / "conversation_chat_view.html").read_text(encoding="utf-8")
            self.assertIn("Первое", output)
            self.assertIn("Второе", output)

    def test_html_line_breaks_remain_in_message_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "messages1.html"
            write_message(source, "Строка 1<br>Строка 2<br><br>Строка 3")

            self.assertTrue(ChatProcessor(lambda *_: None).run([str(source)], str(root), True))

            soup = BeautifulSoup(
                (root / "conversation_chat_view.html").read_text(encoding="utf-8"), "lxml"
            )
            messages = soup.select("div.message")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].select_one(".body").get_text(), "Строка 1\nСтрока 2\n\nСтрока 3")

    def test_attachments_keep_labels_and_safe_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "messages1.html"
            write_message(
                source,
                '<div class="attachment"><div class="attachment__description">'
                '<a href="https://example.com/photo?x=1&amp;y=2">Фото</a></div></div>'
                '<div class="attachment"><div class="attachment__description">Голосовое сообщение</div></div>'
                '<div class="attachment"><div class="attachment__description">'
                '<a href="javascript:alert(1)">Опасная ссылка</a></div></div>'
                '<div class="attachment"><div class="attachment__description">'
                '&lt;img src=x onerror=alert(1)&gt;</div></div>',
            )

            self.assertTrue(ChatProcessor(lambda *_: None).run([str(source)], str(root), True))

            soup = BeautifulSoup(
                (root / "conversation_chat_view.html").read_text(encoding="utf-8"), "lxml"
            )
            messages = soup.select("div.message")
            self.assertEqual(len(messages), 1)
            self.assertIsNone(messages[0].select_one(".empty-message"))
            items = messages[0].select(".attachments li")
            self.assertEqual(len(items), 4)
            self.assertEqual([item.get_text(strip=True) for item in items],
                             ["Фото", "Голосовое сообщение", "Опасная ссылка",
                              "<img src=x onerror=alert(1)>"])
            links = messages[0].select(".attachments a")
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["href"], "https://example.com/photo?x=1&y=2")
            self.assertEqual(messages[0].select("img"), [])

    def test_window_remains_responsive_during_conversion(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "messages1.html"
            write_message(source, "Сообщение")
            window = ChatConverterGUI()
            window._add_file_to_list(str(source))

            def slow_conversion(*_):
                time.sleep(0.25)
                return True

            with patch.object(ChatProcessor, "run", side_effect=slow_conversion), \
                 patch.object(QMessageBox, "information"):
                started = time.perf_counter()
                window._run_processing()
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 0.15)
                self.assertFalse(window.start_button.isEnabled())
                deadline = time.perf_counter() + 3
                while not window.start_button.isEnabled() and time.perf_counter() < deadline:
                    app.processEvents()
                    time.sleep(0.01)
                self.assertTrue(window.start_button.isEnabled())
            window.deleteLater()

    def test_conversion_error_dialog_shows_reason(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "messages1.html"
            window = ChatConverterGUI()
            window._add_file_to_list(str(missing))
            shown = []

            def record_dialog(dialog):
                shown.append((dialog.text(), dialog.informativeText(), dialog.detailedText()))
                return QMessageBox.StandardButton.Ok

            with patch.object(QMessageBox, "exec", record_dialog):
                window._run_processing()
                deadline = time.perf_counter() + 3
                while not window.start_button.isEnabled() and time.perf_counter() < deadline:
                    app.processEvents()
                    time.sleep(0.01)

            self.assertEqual(len(shown), 1)
            self.assertIn("Критическая ошибка при парсинге", shown[0][1])
            self.assertIn("messages1.html", shown[0][2])
            window.deleteLater()

    def test_gui_converts_with_default_level_log_messages(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "messages1.html"
            write_message(source, "Сообщение")
            window = ChatConverterGUI()
            window._add_file_to_list(str(source))
            with patch.object(QMessageBox, "information") as show_success:
                window._run_processing()
                deadline = time.perf_counter() + 3
                while not window.start_button.isEnabled() and time.perf_counter() < deadline:
                    app.processEvents()
                    time.sleep(0.01)

            self.assertTrue(window.start_button.isEnabled())
            show_success.assert_called_once()
            self.assertTrue((root / "conversation_chat_view.html").is_file())
            window.deleteLater()

    def test_settings_are_saved_in_user_profile(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APPDATA": directory}):
            window = ChatConverterGUI()
            window._save_settings()
            self.assertTrue((Path(directory) / "VK-message-history" / "ChatConverter_settings.json").is_file())
            window.deleteLater()

    def test_legacy_settings_are_loaded_before_profile_save(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ChatConverter_settings.json").write_text(
                '{"cleanup_checked": false}', encoding="utf-8"
            )
            with patch.dict(os.environ, {"APPDATA": str(root / "profile")}), \
                 patch.object(Path, "cwd", return_value=root):
                window = ChatConverterGUI()
                self.assertFalse(window.cleanup_checkbox.isChecked())
                window._save_settings()
                self.assertTrue((root / "profile" / "VK-message-history" /
                                 "ChatConverter_settings.json").is_file())
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
