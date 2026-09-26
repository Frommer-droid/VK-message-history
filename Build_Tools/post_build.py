# -*- coding: utf-8 -*-
"""
POST-BUILD CLEANUP SCRIPT
Копирует ключевые файлы и убирает временные директории.
"""

import os
import shutil
import sys

# Force UTF-8 for stdout
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

# ========================================================
# 🔧 CONFIGURATION SECTION
# ========================================================
# Имя папки в dist (должно совпадать с именем в .spec файле)
APP_NAME = "VK-message-history"

# Список файлов для копирования в финальную папку приложения
# (исходный_путь_от_корня, имя_файла_в_папке_приложения)
FILES_TO_COPY = [
    ("logo.ico", "logo.ico"),
    ("VERSION", "VERSION"),
    ("LICENSE", "LICENSE"),
]

# ========================================================
def safe_copy(src: str, dst: str, label: str) -> None:
    if os.path.exists(src):
        try:
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            print(f"[OK] Copied {label}")
        except Exception as e:
            print(f"[ERROR] Failed to copy {label}: {e}")
    else:
        print(f"[SKIP] {label} not found at {src}")


def main() -> None:
    print("\n" + "=" * 60)
    print(f"POST-BUILD CLEANUP: {APP_NAME}")
    print("=" * 60)

    script_dir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    dist_app_dir = os.path.join(script_dir, "dist", APP_NAME)
    final_app_dir = os.path.join(project_root, APP_NAME)

    # 1. Переносим собранное приложение
    if os.path.exists(dist_app_dir):
        try:
            if os.path.exists(final_app_dir):
                print(f"[ERROR] Destination already exists: {final_app_dir}")
                print("Inspect and remove the old build before running post_build.py.")
                raise SystemExit(1)
            shutil.move(dist_app_dir, final_app_dir)
            print(f"[OK] Moved to: {final_app_dir}")
        except Exception as e:
            print(f"[ERROR] Failed to move: {e}")
            raise SystemExit(1)
    else:
        print(f"[ERROR] dist/{APP_NAME} not found! Build might have failed.")
        raise SystemExit(1)

    # 2. Копируем дополнительные файлы. Work-файлы остаются для проверки TOC.
    print("\n[COPY] Copying additional files...")
    for src_rel, dst_rel in FILES_TO_COPY:
        src = os.path.join(project_root, src_rel)
        dst = os.path.join(final_app_dir, dst_rel)
        safe_copy(src, dst, src_rel)

    print("\n" + "=" * 60)
    print(f"DONE! App location: {final_app_dir}")
    print("=" * 60)

if __name__ == "__main__":
    main()
