import sys
import traceback
import os
import json
import glob
import re
import html
import base64
import ctypes
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QFileDialog, QMessageBox,
    QStatusBar, QTextEdit, QGroupBox, QCheckBox, QSplitter, QTabWidget,
    QListWidget, QListWidgetItem
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QThread, Signal, Slot

from app.version import __version__
from app.ui.theme import apply_theme, enforce_button_proportions

# =============================================================================
# 1. ОБЯЗАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ РЕСУРСОВ (ИЗ РУКОВОДСТВА)
# =============================================================================
def resource_path(relative_path):
    """ Получает абсолютный путь к ресурсу, работает как для dev, так и для PyInstaller """
    try:
        # PyInstaller создает временную папку и сохраняет путь в _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Если не в PyInstaller, используем путь к текущему скрипту
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# =============================================================================
# 2. ОРИГИНАЛЬНАЯ ЛОГИКА (сохранена и адаптирована)
# =============================================================================
class ChatProcessor:
    """
    Класс, инкапсулирующий всю логику обработки файлов.
    Оригинальная логика сохранена, но теперь принимает список файлов.
    """
    def __init__(self, log_callback):
        self.log = log_callback

    def _extract_messages_from_html(self, html_filepath, txt_filepath, read_encoding='cp1251', write_encoding='utf-8'):
        """Читает HTML, извлекает сообщения, сохраняет в TXT файл."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            self.log("Ошибка: библиотека BeautifulSoup не найдена. Установите ее: pip install beautifulsoup4 lxml", "error")
            return None

        self.log(f"Обработка HTML: {os.path.basename(html_filepath)} -> {os.path.basename(txt_filepath)}")
        try:
            with open(html_filepath, 'r', encoding=read_encoding, errors='ignore') as f_html:
                html_content = f_html.read()

            soup = BeautifulSoup(html_content, 'lxml')
            message_divs = soup.find_all('div', class_='message')

            if not message_divs:
                with open(txt_filepath, 'w', encoding=write_encoding) as f_txt:
                    f_txt.write("")
                return []

            extracted_data = []
            messages = []
            for msg_div in message_divs:
                header = msg_div.find('div', class_='message__header')
                body_div = header.find_next_sibling('div') if header else None
                if header and body_div:
                    attachments = []
                    for block in body_div.find_all('div', class_='attachment'):
                        label = block.get_text(' ', strip=True) or 'Вложение'
                        link = block.find('a', href=True)
                        href = link.get('href', '').strip() if link else ''
                        parsed = urlparse(href)
                        if (parsed.scheme.lower() not in ('http', 'https')
                                or not parsed.netloc
                                or any(char.isspace() or ord(char) < 32 for char in href)):
                            href = ''
                        attachments.append((label, href))
                        block.decompose()
                    for unwanted in body_div.find_all('div', class_='kludges'):
                        unwanted.decompose()
                    header_text = header.get_text(strip=True)
                    # U+2028 сохраняет переносы внутри TXT без конфликта с разделителем сообщений.
                    for br in body_div.find_all('br'):
                        br.replace_with('\u2028')
                    body_text = re.sub(
                        r'[ \t]*\u2028[ \t]*', '\u2028',
                        body_div.get_text(separator=' ', strip=False),
                    ).strip()
                    messages.append((header_text, body_text, attachments))
                    if header_text:
                        extracted_data.append(header_text)
                    if body_text:
                        extracted_data.append(body_text)
                    for label, href in attachments:
                        extracted_data.append(f"Вложение: {label}" + (f" — {href}" if href else ""))
                    extracted_data.append("")

            if extracted_data and extracted_data[-1] == "":
                extracted_data.pop()

            final_output = "\n".join(extracted_data)
            with open(txt_filepath, 'w', encoding=write_encoding) as f_txt:
                f_txt.write(final_output)
            return messages
        except Exception as e:
            self.log(f"Критическая ошибка при парсинге {os.path.basename(html_filepath)}: {e}", "error")
            return None

    def _extract_number_from_filename(self, filename):
        """Извлекает число из имени файла вида 'messages123.txt'."""
        basename = os.path.basename(filename)
        match = re.search(r'messages(\d+)\.txt$', basename, re.IGNORECASE)
        return int(match.group(1)) if match else -1

    def _parse_header_final(self, header_line):
        """Извлекает автора и дату из строки заголовка."""
        cleaned_header = header_line.replace('\xa0', ' ').replace('(ред.)', '').strip()
        datetime_pattern = re.compile(r'(\d{1,2}\s+\w+\s+\d{4}\s+в\s+\d{1,2}:\d{1,2}:\d{2})', re.IGNORECASE)
        matches = list(datetime_pattern.finditer(cleaned_header))
        if matches:
            last_match = matches[-1]
            datetime_str = last_match.group(1)
            author_str = cleaned_header[:last_match.start()].strip().rstrip(',').strip()
            if not author_str and cleaned_header.startswith(datetime_str):
                author_str = "Вы"
            return author_str if author_str else "(Неизвестный автор)", datetime_str
        return cleaned_header, ""

    def _generate_css_content(self):
        """Генерирует CSS для итогового HTML."""
        return """
body { font-family: 'Aptos', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #282C34; color: #ABB2BF; line-height: 1.6; margin: 0; padding: 20px; }
.container { max-width: 900px; margin: 20px auto; background-color: #21252B; padding: 25px 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4); border: 1px solid #3E4451; overflow: hidden; }
h1 { text-align: center; color: #E6E6E6; margin-bottom: 35px; padding-bottom: 15px; border-bottom: 2px solid #3E4451; font-weight: 400; }
.message { padding: 12px 18px; margin-bottom: 12px; border-radius: 18px; line-height: 1.5; word-wrap: break-word; max-width: 80%; clear: both; position: relative; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
.message-left { float: left; background-color: #2C313A; border-top-left-radius: 5px; text-align: left; color: #D3D3D3; }
.message-left .author { color: #3AE2CE; margin-right: 10px; display: block; font-size: 0.95em; margin-bottom: 4px; font-weight: bold; }
.message-left .datetime { font-size: 0.8em; color: #7F848E; display: block; text-align: left; }
.message-left .body { margin-top: 5px; }
.message-right { float: right; background-color: #005A8D; border-top-right-radius: 5px; text-align: left; color: #F0F0F0; }
.message-right .author { display: none; }
.message-right .header { text-align: right; margin-bottom: 3px; }
.message-right .datetime { font-size: 0.8em; color: #A3D5FF; display: inline; }
.message-right .body { margin-top: 5px; color: #f5f5f5; }
.header { margin-bottom: 5px; }
.body { white-space: pre-wrap; font-size: 1.05em; }
.attachments { margin: 8px 0 0; padding-left: 20px; overflow-wrap: anywhere; }
.attachments li { margin: 4px 0; }
.attachments a { color: #8FD6FF; text-decoration: underline; }
.empty-message { color: #8a9aab; font-style: italic; }
.container::after { content: ""; display: table; clear: both; }
        """

    def run(self, html_files, output_dir, cleanup_intermediate):
        """Основной метод, запускающий весь процесс на основе списка файлов."""
        self.log("--- Запуск процесса конвертации ---", "info")
        intermediate_txt_files = []
        try:
            # --- Шаг 1: HTML -> TXT ---
            self.log("\n--- Шаг 1: Обработка HTML файлов из списка ---", "info")
            if not html_files:
                self.log("Список файлов для обработки пуст.", "error")
                return False

            processed_count = 0
            for html_path in html_files:
                base_name = os.path.splitext(os.path.basename(html_path))[0]
                handle, txt_path = tempfile.mkstemp(
                    prefix=base_name + "_", suffix=".txt", dir=output_dir
                )
                os.close(handle)
                intermediate_txt_files.append((html_path, txt_path, None))
                messages = self._extract_messages_from_html(html_path, txt_path)
                if messages is not None:
                    processed_count += 1
                    intermediate_txt_files[-1] = (html_path, txt_path, messages)
                else:
                    intermediate_txt_files.pop()
                    os.remove(txt_path)
                    self.log(f"Пропуск файла {os.path.basename(html_path)} из-за ошибки.", "warning")

            if processed_count == 0:
                self.log("Не удалось обработать ни одного HTML файла. Процесс остановлен.", "error")
                return False

            # Остальная логика (Шаги 2, 3, 4) остается практически без изменений
            self.log("\n--- Шаг 2: Объединение текстовых данных ---", "info")
            intermediate_txt_files.sort(
                key=lambda pair: self._extract_number_from_filename(
                    os.path.splitext(os.path.basename(pair[0]))[0] + ".txt"
                ),
                reverse=True,
            )
            all_messages_in_order = []
            for _, _, messages in intermediate_txt_files:
                all_messages_in_order.extend(reversed(messages))

            if not all_messages_in_order:
                self.log("Нет данных для сборки итогового файла. Процесс остановлен.", "error")
                return False

            self.log("\n--- Шаг 3: Генерация итоговых HTML и CSS файлов ---", "info")
            all_messages_data = []
            for header_text, body_text, attachments in all_messages_in_order:
                author, datetime_str = self._parse_header_final(header_text)
                body_line = body_text.replace('\u2028', '\n')
                all_messages_data.append((author, datetime_str, body_line, attachments))

            html_message_blocks = []
            for author, datetime_str, body, attachments in all_messages_data:
                safe_author = html.escape(author)
                safe_body = html.escape(body)
                safe_datetime = html.escape(datetime_str) if datetime_str else ""
                is_you = (author.strip() == "Вы")
                alignment_class = "message-right" if is_you else "message-left"
                author_html = f'<span class="author">{safe_author}</span>' if not is_you else ''
                body_content_html = f'<div class="body">{safe_body}</div>' if safe_body else ('<div class="body"><span class="empty-message">(пустое сообщение)</span></div>' if not attachments else '')
                attachment_items = []
                for label, href in attachments:
                    safe_label = html.escape(label)
                    if href:
                        safe_href = html.escape(href, quote=True)
                        attachment_items.append(f'<li><a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_label}</a></li>')
                    else:
                        attachment_items.append(f'<li>{safe_label}</li>')
                attachment_html = f'<ul class="attachments">{"".join(attachment_items)}</ul>' if attachment_items else ''
                html_block = f"""<div class="message {alignment_class}"><div class="header">{author_html}<span class="datetime">({safe_datetime})</span></div>{body_content_html}{attachment_html}</div>"""
                html_message_blocks.append(html_block)

            suffix = 1
            while True:
                marker = "" if suffix == 1 else f"_{suffix}"
                output_html_filename = f"conversation_chat_view{marker}.html"
                output_css_filename = f"style_chat_view{marker}.css"
                output_html_path = os.path.join(output_dir, output_html_filename)
                output_css_path = os.path.join(output_dir, output_css_filename)
                if not os.path.exists(output_html_path) and not os.path.exists(output_css_path):
                    break
                suffix += 1

            html_content = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>История переписки</title><link rel="stylesheet" href="{html.escape(output_css_filename)}"></head><body><div class="container"><h1>История переписки</h1>{''.join(html_message_blocks)}</div></body></html>"""
            css_content = self._generate_css_content()

            with open(output_css_path, 'x', encoding='utf-8') as f:
                f.write(css_content)
            with open(output_html_path, 'x', encoding='utf-8') as f:
                f.write(html_content)
            self.log(f"Успешно сгенерирован HTML: {output_html_path}", "success")
            self.log(f"Успешно сгенерирован CSS: {output_css_path}", "success")

            if cleanup_intermediate:
                self.log("\n--- Шаг 4: Очистка промежуточных файлов ---", "info")
                deleted_count = 0
                for _, txt_path, _ in intermediate_txt_files:
                    try:
                        os.remove(txt_path)
                        deleted_count += 1
                    except Exception as e:
                        self.log(f"Не удалось удалить файл {os.path.basename(txt_path)}: {e}", "warning")
                self.log(f"Удалено {deleted_count} промежуточных .txt файлов.")

            self.log("\n--- Процесс успешно завершен! ---", "success")
            return True
        except Exception as e:
            self.log(f"Критическая ошибка в процессе выполнения: {e}\n{traceback.format_exc()}", "error")
            return False
        finally:
            if cleanup_intermediate:
                for _, txt_path, _ in intermediate_txt_files:
                    if os.path.exists(txt_path):
                        try:
                            os.remove(txt_path)
                        except OSError as error:
                            self.log(f"Не удалось удалить временный файл {txt_path}: {error}", "warning")


class ConversionThread(QThread):
    progress = Signal(str, str)

    def __init__(self, file_paths, output_dir, cleanup_intermediate):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.cleanup_intermediate = cleanup_intermediate
        self.success = False
        self.errors = []

    def _report_progress(self, message, level="info"):
        if level == "error":
            self.errors.append(message)
        self.progress.emit(message, level)

    def run(self):
        try:
            self.success = ChatProcessor(self._report_progress).run(
                self.file_paths, self.output_dir, self.cleanup_intermediate
            )
        except Exception as error:
            self._report_progress(f"Непредвиденная ошибка: {type(error).__name__}: {error}", "error")

class ChatConverterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        settings_root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        self.settings_file = settings_root / "VK-message-history" / "ChatConverter_settings.json"
        self.conversion_thread = None
        self.setWindowTitle(f"Конвертер истории сообщений ВК v{__version__}")
        self.setAcceptDrops(True)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Создает и компонует все виджеты в соответствии со стандартом."""
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        enforce_button_proportions(self.findChildren(QPushButton))
        # Иконка для окна (дополнительно к иконке приложения)
        try:
            self.setWindowIcon(QIcon(resource_path("logo.ico")))
        except Exception:
            print("Предупреждение: файл иконки 'logo.ico' не найден.")

    def _create_widgets(self):
        """Создание всех виджетов приложения."""
        self.tabs = QTabWidget()

        # --- Панель управления (правая) ---
        # 1. Группа "Источник файлов"
        self.source_group = QGroupBox("Источник файлов")
        self.source_path_combo = QComboBox()
        self.source_path_combo.setEditable(True)
        self.source_path_combo.lineEdit().setPlaceholderText("Выберите папку или перетащите сюда")
        self.browse_source_btn = QPushButton("Обзор...")
        self.browse_source_btn.setFixedWidth(150)
        self.add_files_btn = QPushButton("Добавить отдельные файлы")

        # 2. Группа "Управление списком"
        self.list_mgmt_group = QGroupBox("Управление списком")
        self.remove_selected_btn = QPushButton("Убрать выбранное")
        self.remove_selected_btn.setObjectName("danger_btn")
        self.clear_list_btn = QPushButton("Очистить список")
        self.clear_list_btn.setObjectName("danger_btn")

        # 3. Группа "Параметры конвертации"
        self.params_group = QGroupBox("Параметры конвертации")
        self.cleanup_checkbox = QCheckBox("Удалять промежуточные .txt файлы")
        self.output_path_label = QLabel("Папка для сохранения:")
        self.output_path_combo = QComboBox()
        self.output_path_combo.setEditable(True)
        self.output_path_combo.addItem("В той же папке") # Обязательный пункт
        self.browse_output_btn = QPushButton("Обзор...")
        self.browse_output_btn.setFixedWidth(150)

        # 4. Основная кнопка действия
        self.start_button = QPushButton("Начать конвертацию")
        self.start_button.setObjectName("start_btn")

        # --- Панель списка файлов (левая) ---
        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QListWidget.ExtendedSelection)

        # --- Вкладка "О программе" ---
        self.about_text = QTextEdit()
        self.about_text.setReadOnly(True)
        self.about_text.setHtml(f"""
            <h2>Конвертер истории сообщений ВК v{html.escape(__version__)}</h2>
            <p>Объединяет выгруженную историю ВКонтакте в один HTML-файл.
            Сохраняет текст, даты, подписи вложений и доступные веб-ссылки.</p>
            <h3>Как использовать</h3>
            <ol>
                <li>Выберите папку с файлами <code>messages*.html</code> или перетащите её в окно.</li>
                <li>При необходимости добавьте отдельные файлы и укажите папку для результата.</li>
                <li>Нажмите «Начать конвертацию» и откройте созданный <code>conversation_chat_view.html</code> в браузере.</li>
            </ol>
            <p>Медиафайлы не встраиваются в HTML. Для открытия ссылок на вложения может потребоваться доступ к сайту-источнику.</p>
        """)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _create_layout(self):
        """Компоновка виджетов в соответствии со стандартом."""
        # --- Правая панель ---
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)

        source_layout = QVBoxLayout(self.source_group)
        source_path_layout = QHBoxLayout()
        source_path_layout.addWidget(self.source_path_combo)
        source_path_layout.addWidget(self.browse_source_btn)
        source_layout.addLayout(source_path_layout)
        source_layout.addWidget(self.add_files_btn)

        list_mgmt_layout = QHBoxLayout(self.list_mgmt_group)
        list_mgmt_layout.addWidget(self.remove_selected_btn)
        list_mgmt_layout.addWidget(self.clear_list_btn)

        params_layout = QVBoxLayout(self.params_group)
        params_layout.addWidget(self.cleanup_checkbox)
        params_layout.addWidget(self.output_path_label)
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(self.output_path_combo)
        output_path_layout.addWidget(self.browse_output_btn)
        params_layout.addLayout(output_path_layout)

        right_panel_layout.addWidget(self.source_group)
        right_panel_layout.addWidget(self.list_mgmt_group)
        right_panel_layout.addWidget(self.params_group)
        right_panel_layout.addStretch() # Распорка
        right_panel_layout.addWidget(self.start_button)

        # --- Сборка сплиттера ---
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.file_list_widget)
        self.main_splitter.addWidget(right_panel_widget)
        # Установка начальных пропорций (левая панель шире)
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 1)

        # --- Сборка вкладок ---
        main_tab = QWidget()
        main_tab_layout = QVBoxLayout(main_tab)
        main_tab_layout.addWidget(self.main_splitter)
        self.tabs.addTab(main_tab, "Основная функция")

        about_tab = QWidget()
        about_tab_layout = QVBoxLayout(about_tab)
        about_tab_layout.addWidget(self.about_text)
        self.tabs.addTab(about_tab, "О программе")

        self.setCentralWidget(self.tabs)

    def _connect_signals(self):
        """Подключение всех сигналов к слотам."""
        # Кнопки
        self.browse_source_btn.clicked.connect(self._browse_source_directory)
        self.add_files_btn.clicked.connect(self._add_individual_files)
        self.browse_output_btn.clicked.connect(self._browse_output_directory)
        self.remove_selected_btn.clicked.connect(self._remove_selected_files)
        self.clear_list_btn.clicked.connect(self._clear_file_list)
        self.start_button.clicked.connect(self._run_processing)

        # QComboBox для авто-сканирования
        self.source_path_combo.activated.connect(self._on_source_combo_activated)

    def _load_settings(self):
        """Загрузка настроек из JSON файла."""
        try:
            legacy_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
            settings_source = self.settings_file if self.settings_file.is_file() else legacy_root / "ChatConverter_settings.json"
            if not settings_source.is_file():
                self.setGeometry(200, 200, 1200, 800) # Размер по умолчанию для первого запуска
                return

            with open(settings_source, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            # Восстановление состояния окна, сплиттера, вкладок
            geometry = settings.get("geometry")
            if geometry:
                self.restoreGeometry(base64.b64decode(geometry))

            splitter_state = settings.get("splitter_state")
            if splitter_state:
                self.main_splitter.restoreState(base64.b64decode(splitter_state))
            
            self.tabs.setCurrentIndex(settings.get("current_tab_index", 0))

            # Восстановление истории и последнего выбора
            self._load_combo_history(self.source_path_combo, settings.get("source_history", []), settings.get("last_source_index", 0))
            self._load_combo_history(self.output_path_combo, settings.get("output_history", []), settings.get("last_output_index", 0))
            
            self.cleanup_checkbox.setChecked(settings.get("cleanup_checked", True))
            self.status_bar.showMessage("Настройки успешно загружены", 3000)
        except (json.JSONDecodeError, KeyError, Exception) as e:
            self.status_bar.showMessage(f"Ошибка загрузки настроек: {e}", 5000)
            self.setGeometry(200, 200, 1200, 800) # Безопасные значения по умолчанию

    def _save_settings(self):
        """Сохранение настроек в JSON файл."""
        # Обновляем историю перед сохранением
        self._update_path_history(self.source_path_combo, self.source_path_combo.currentText())
        self._update_path_history(self.output_path_combo, self.output_path_combo.currentText())

        settings = {
            "geometry": base64.b64encode(self.saveGeometry()).decode('utf-8'),
            "splitter_state": base64.b64encode(self.main_splitter.saveState()).decode('utf-8'),
            "current_tab_index": self.tabs.currentIndex(),
            "cleanup_checked": self.cleanup_checkbox.isChecked(),
            "source_history": [self.source_path_combo.itemText(i) for i in range(self.source_path_combo.count())],
            "last_source_index": self.source_path_combo.currentIndex(),
            "output_history": [self.output_path_combo.itemText(i) for i in range(1, self.output_path_combo.count())], # Не сохраняем "В той же папке"
            "last_output_index": self.output_path_combo.currentIndex(),
        }
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            self._log_message(f"Критическая ошибка сохранения настроек: {e}", "error")

    def _update_path_history(self, combo, new_path):
        """Обновляет историю путей в QComboBox, избегая дубликатов и сохраняя лимит."""
        if not new_path or not os.path.isdir(new_path):
            return

        is_output_combo = (combo.itemText(0) == "В той же папке")
        start_index = 1 if is_output_combo else 0

        # Удаляем старую запись, если она есть
        for i in range(start_index, combo.count()):
            if combo.itemText(i) == new_path:
                combo.removeItem(i)
                break
        
        # Вставляем новый путь в начало истории
        combo.insertItem(start_index, new_path)
        
        # Ограничиваем историю до 10 записей (+1 для "В той же папке")
        limit = 11 if is_output_combo else 10
        while combo.count() > limit:
            combo.removeItem(combo.count() - 1)
        
        combo.setCurrentIndex(start_index)

    def _load_combo_history(self, combo, history, last_index):
        """Загружает историю в QComboBox."""
        is_output_combo = (combo.itemText(0) == "В той же папке")
        
        # Очищаем все, кроме первого элемента, если это output_combo
        if is_output_combo:
            while combo.count() > 1:
                combo.removeItem(1)
        else:
            combo.clear()

        unique_history = []
        for path in history:
            if path not in unique_history and (not is_output_combo or path != "В той же папке"):
                unique_history.append(path)
        
        combo.addItems(unique_history)
        if 0 <= last_index < combo.count():
            combo.setCurrentIndex(last_index)

    def _add_file_to_list(self, file_path):
        """Добавляет файл в QListWidget, избегая дубликатов и используя UserRole."""
        # Проверяем, нет ли уже такого файла
        for i in range(self.file_list_widget.count()):
            if self.file_list_widget.item(i).data(Qt.UserRole) == file_path:
                return # Файл уже в списке

        filename = os.path.basename(file_path)
        parent_folder = os.path.basename(os.path.dirname(file_path))
        display_text = f"{filename} ({parent_folder})"

        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, file_path) # Сохраняем полный путь
        self.file_list_widget.addItem(item)
    
    # --- Методы-обработчики событий ---
    
    def _browse_source_directory(self):
        """Вызывает диалог выбора папки-источника и запускает сканирование."""
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку с файлами чата")
        if directory:
            self._update_path_history(self.source_path_combo, directory)
            self._scan_source_folder(directory)

    def _on_source_combo_activated(self, index):
        """Запускает сканирование при выборе папки из истории."""
        path = self.source_path_combo.itemText(index)
        if os.path.isdir(path):
            self._scan_source_folder(path)

    def _scan_source_folder(self, path):
        """Сканирует папку на наличие 'messages*.html' и заполняет список."""
        self.file_list_widget.clear()
        self._log_message(f"Сканирование папки: {path}...", "info")
        try:
            # Ищем файлы рекурсивно
            found_files = glob.glob(os.path.join(path, '**', 'messages*.html'), recursive=True)
            if not found_files:
                self._log_message("Файлы 'messages*.html' не найдены.", "warning")
                return
            
            for file_path in found_files:
                self._add_file_to_list(file_path)
            self._log_message(f"Найдено и добавлено {len(found_files)} файлов.", "success")
        except Exception as e:
            self._log_message(f"Ошибка при сканировании папки: {e}", "error")

    def _add_individual_files(self):
        """Добавляет отдельные файлы в список."""
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы", "", "HTML файлы (*.html)")
        if files:
            for file in files:
                self._add_file_to_list(file)
            self._log_message(f"Добавлено {len(files)} файлов вручную.", "info")
    
    def _browse_output_directory(self):
        """Вызывает диалог выбора папки для сохранения."""
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения результатов")
        if directory:
            self._update_path_history(self.output_path_combo, directory)

    def _remove_selected_files(self):
        """Удаляет выбранные элементы из списка."""
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.file_list_widget.takeItem(self.file_list_widget.row(item))
        self._log_message(f"Удалено {len(selected_items)} файлов из списка.", "info")

    def _clear_file_list(self):
        """Очищает весь список файлов."""
        self.file_list_widget.clear()
        self._log_message("Список файлов очищен.", "info")
        
    @Slot(str, str)
    def _log_message(self, message, level="info"):
        """Выводит сообщение в статус-бар (для GUI)."""
        self.status_bar.showMessage(message, 5000)

    def _run_processing(self):
        """Запускает основной процесс обработки."""
        # 1. Сбор и проверка данных
        file_paths = []
        for i in range(self.file_list_widget.count()):
            file_paths.append(self.file_list_widget.item(i).data(Qt.UserRole))

        if not file_paths:
            QMessageBox.warning(self, "Нет файлов", "Список файлов для обработки пуст. Добавьте файлы.")
            return

        output_path_text = self.output_path_combo.currentText()
        if output_path_text == "В той же папке":
            # Используем папку первого файла в списке как целевую
            output_dir = os.path.dirname(file_paths[0])
        else:
            output_dir = output_path_text

        if not os.path.isdir(output_dir):
            reply = QMessageBox.question(self, "Создать папку?", f"Папка '{output_dir}' не существует. Создать ее?")
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(output_dir)
                    self._log_message(f"Папка создана: {output_dir}", "info")
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку: {e}")
                    return
            else:
                return
        
        # 2. Запуск логики
        self.start_button.setEnabled(False)
        self.tabs.setCurrentIndex(0) # Переключаемся на основную вкладку
        
        self.conversion_thread = ConversionThread(
            file_paths, output_dir, self.cleanup_checkbox.isChecked()
        )
        self.conversion_thread.progress.connect(self._log_message)
        self.conversion_thread.finished.connect(self._conversion_finished)
        self.conversion_thread.start()

    @Slot()
    def _conversion_finished(self):
        worker = self.conversion_thread
        self.conversion_thread = None
        self.start_button.setEnabled(True)
        if worker.success:
            QMessageBox.information(self, "Успех!", f"Обработка завершена. Результаты сохранены в:\n{worker.output_dir}")
        else:
            reason = worker.errors[0].splitlines()[0] if worker.errors else "Причина ошибки не указана."
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Завершено с ошибками")
            dialog.setText("Не удалось завершить конвертацию.")
            dialog.setInformativeText(reason)
            if worker.errors:
                dialog.setDetailedText("\n\n".join(worker.errors))
            dialog.exec()
        worker.deleteLater()
            
    # --- Drag and Drop ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        
        # Обрабатываем только первую перетащенную сущность
        path = urls[0].toLocalFile()
        
        if os.path.isdir(path):
            self._update_path_history(self.source_path_combo, path)
            self._scan_source_folder(path)
        elif os.path.isfile(path) and path.lower().endswith('.html'):
             self._add_file_to_list(path)

    def closeEvent(self, event):
        """Перехват события закрытия окна для сохранения настроек."""
        if self.conversion_thread is not None and self.conversion_thread.isRunning():
            self.status_bar.showMessage("Дождитесь завершения конвертации.", 5000)
            event.ignore()
            return
        self._save_settings()
        super().closeEvent(event)

# =============================================================================
# 4. ТОЧКА ВХОДА (по стандарту)
# =============================================================================
if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--smoke-conversion':
        source_dir, output_dir = sys.argv[2:]
        files = glob.glob(os.path.join(source_dir, '**', 'messages*.html'), recursive=True)
        worker = ConversionThread(files, output_dir, True)
        worker.run()
        for message in worker.errors:
            print(message, file=sys.stderr)
        sys.exit(0 if worker.success else 1)
    try:
        # Уникальный ID для корректного отображения иконки в панели задач Windows
        myappid = 'mycompany.chatconverter.gui.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        app = QApplication(sys.argv)
        apply_theme(app)
        
        # Установка иконки для всего приложения
        try:
            app.setWindowIcon(QIcon(resource_path("logo.ico")))
        except Exception:
            pass # Ошибка уже выводится в консоль при инициализации окна
        
        window = ChatConverterGUI()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        # Глобальный обработчик ошибок для проблем при запуске
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setText("Произошла критическая ошибка при запуске приложения.")
        error_dialog.setInformativeText(f"{type(e).__name__}: {e}")
        error_dialog.setDetailedText(traceback.format_exc())
        error_dialog.setWindowTitle("Ошибка Запуска")
        error_dialog.exec()
        sys.exit(1)
