<p align="center"><img src="assets/icon.png" alt="Application icon" width="96"></p>
<h1 align="center">VK Message History</h1>
<p align="center">Turn a VKontakte data export into one readable HTML conversation.</p>
<p align="center"><a href="README.md">Русский</a> · <a href="https://github.com/Frommer-droid/VK-message-history/releases/latest">Latest release</a></p>

## Get started

1. Download the Windows installer from the [latest release](https://github.com/Frommer-droid/VK-message-history/releases/latest) and install the app.
2. Request a VKontakte data archive containing your message history.
3. Open the app and select the folder containing `messages*.html`, or drag the folder into the window.
4. Choose an output folder and click **«Начать конвертацию»** (Start conversion).
5. Open `conversation_chat_view.html` in a browser. Keep `style_chat_view.css` beside it.

The app runs on Windows 10/11 x64. Conversion itself works offline.

## What it preserves

- Messages, authors, dates, and line breaks.
- Attachment labels and HTTP(S) links when present in the export. Attachments appear below their messages.
- Message order across multiple `messages*.html` files, including nested folders.

The app does not download or embed media files. Opening an attachment link may require access to its source site. Repeated conversions keep earlier results and add a numeric suffix to the new HTML and CSS files.

## Run from source

Install Python 3.12 and the dependencies in a project virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe process_all_vk.pyw
```

Settings are stored in `%APPDATA%\VK-message-history\ChatConverter_settings.json`. See [DEVELOPER.md](DEVELOPER.md) for build and test instructions.

## License

The project's own code is licensed under [MIT](LICENSE). Dependencies retain their respective licenses.
