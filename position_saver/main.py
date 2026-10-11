# position_saver/main.py
# -*- coding: utf-8 -*-

"""
نقطه ورود مستقل + کارخانه‌ی ویجت.

نحوه استفاده:
    # ۱. اجرای مستقل
    python -m position_saver.main

    # ۲. الحاق به برنامه‌ی مادر
    from position_saver import (
        create_position_saver_widget,
        set_snapshot_provider,
    )
    set_snapshot_provider(get_market_snapshot)
    widget = create_position_saver_widget(parent=self)
    tabs.addTab(widget, "مدیریت موقعیت‌ها")
"""


# ═══════════════════════════════════════════════════
# ۱. sys.path
# ═══════════════════════════════════════════════════

import os
import sys
import logging
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


logger = logging.getLogger("PositionSaver")


# ═══════════════════════════════════════════════════
# ۲. Providerها (delegate به providers.py)
# ═══════════════════════════════════════════════════

from position_saver.providers import (
    set_snapshot_provider,
    set_bale_provider,
    set_settings_provider,
    get_market_snapshot,
    get_bale_notifier,
    get_setting,
    get_commission_rate,
)


# ═══════════════════════════════════════════════════
# ۳. Widget Factory
# ═══════════════════════════════════════════════════

def create_position_saver_widget(
    parent=None,
    storage_path: Optional[str] = None,
    auto_start_monitor: bool = True,
):
    """
    ساخت ویجت Position Saver برای الحاق به برنامه‌ی مادر.

    Args:
        parent: والد Qt
        storage_path: مسیر فایل JSON (اختیاری)
        auto_start_monitor: شروع خودکار ترد پس‌زمینه

    Returns:
        PositionSaverWidget
    """
    from position_saver.ui.main_widget import PositionSaverWidget
    from position_saver.storage import PositionStorage

    storage = (PositionStorage(storage_path) if storage_path
               else PositionStorage())

    return PositionSaverWidget(
        parent=parent,
        storage=storage,
        auto_start_monitor=auto_start_monitor,
    )


# ═══════════════════════════════════════════════════
# ۴. logging
# ═══════════════════════════════════════════════════

def _setup_logging() -> None:
    log_level = logging.INFO
    if os.environ.get("POSITION_SAVER_DEBUG"):
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ═══════════════════════════════════════════════════
# ۵. importهای standalone با پیام خطای دقیق
# ═══════════════════════════════════════════════════

def _import_standalone_dependencies() -> Optional[dict]:
    """
    importهای لازم برای حالت standalone.
    در صورت خطا، پیام دقیق می‌دهد.
    """
    errors = []

    # ─── PySide6 ───
    try:
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QStatusBar, QMessageBox,
        )
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
    except ImportError as e:
        errors.append(f"PySide6: {e}")
        return _report_import_errors(errors)

    # ─── main_widget (نقطه‌ی اصلی دیباگ) ───
    try:
        from position_saver.ui.main_widget import PositionSaverWidget
    except ImportError as e:
        errors.append(f"position_saver.ui.main_widget: {e}")
        return _report_import_errors(errors)

    # ─── theme ───
    try:
        from position_saver.theme import QSS
    except ImportError:
        QSS = ""
        logger.warning("theme.py یافت نشد — استایل پیش‌فرض")

    return {
        "QApplication": QApplication,
        "QMainWindow": QMainWindow,
        "QStatusBar": QStatusBar,
        "QMessageBox": QMessageBox,
        "Qt": Qt,
        "QFont": QFont,
        "PositionSaverWidget": PositionSaverWidget,
        "QSS": QSS,
    }


def _report_import_errors(errors: list):
    """نمایش خطای دقیق import"""
    print("=" * 60)
    print("❌ خطا در import ماژول‌ها")
    print("=" * 60)
    for err in errors:
        print(f"\n  • {err}")

    print("\n" + "-" * 60)
    print("راهنما:")
    print("  • برای دیدن جزئیات کامل، اجرا کنید:")
    print("      python -c \"from position_saver.ui.main_widget import PositionSaverWidget\"")
    print("  • بررسی نصب کتابخانه‌ها:")
    print("      pip install PySide6 pandas openpyxl jdatetime")
    print("=" * 60)
    return None


# ═══════════════════════════════════════════════════
# ۶. پنجره‌ی standalone
# ═══════════════════════════════════════════════════

def _build_standalone_window(deps: dict):
    """ساخت کلاس پنجره‌ی مستقل با وابستگی‌های داده‌شده"""
    QMainWindow = deps["QMainWindow"]
    QStatusBar = deps["QStatusBar"]
    Qt = deps["Qt"]
    PositionSaverWidget = deps["PositionSaverWidget"]

    class StandalonePositionSaverWindow(QMainWindow):
        WINDOW_TITLE = "مدیریت و ثبت موقعیت‌های استراتژی آپشن"

        def __init__(self):
            super().__init__()
            self.setWindowTitle(self.WINDOW_TITLE)
            self.setLayoutDirection(Qt.RightToLeft)
            self.setMinimumSize(1000, 600)

            status_bar = QStatusBar()
            status_bar.setSizeGripEnabled(True)
            self.setStatusBar(status_bar)
            status_bar.showMessage("🟢 آماده — برنامه راه‌اندازی شد")

            self.main_widget = PositionSaverWidget(self)
            self.setCentralWidget(self.main_widget)

            self._restore_window_geometry()

        def _geometry_file(self):
            return _HERE / "window_geometry.json"

        def _save_window_geometry(self):
            try:
                import json
                with open(self._geometry_file(), "w",
                          encoding="utf-8") as f:
                    json.dump({
                        "x": self.x(), "y": self.y(),
                        "width": self.width(), "height": self.height(),
                        "is_maximized": self.isMaximized(),
                    }, f)
            except Exception:
                pass

        def _restore_window_geometry(self):
            try:
                import json
                gf = self._geometry_file()
                if not gf.exists():
                    return
                with open(gf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not data.get("is_maximized", False):
                    w = data.get("width", 1200)
                    h = data.get("height", 700)
                    if w >= 800 and h >= 500:
                        self.setGeometry(
                            data.get("x", 100),
                            data.get("y", 100), w, h)
            except Exception:
                pass

        def closeEvent(self, event):
            try:
                if hasattr(self, 'main_widget'):
                    self.main_widget.stop_monitor()
            except Exception as e:
                logger.warning(f"Error stopping monitor: {e}")
            self._save_window_geometry()
            event.accept()

    return StandalonePositionSaverWindow


# ═══════════════════════════════════════════════════
# ۷. High DPI
# ═══════════════════════════════════════════════════

def _setup_high_dpi(QApplication, Qt) -> None:
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# ۸. main() — اجرای مستقل
# ═══════════════════════════════════════════════════

def main() -> int:
    _setup_logging()
    logger.info("=" * 60)
    logger.info("Starting Position Saver (Standalone)")
    logger.info("=" * 60)

    # ─── importها ───
    deps = _import_standalone_dependencies()
    if deps is None:
        return 1

    QApplication = deps["QApplication"]
    QMessageBox = deps["QMessageBox"]
    Qt = deps["Qt"]
    QFont = deps["QFont"]
    QSS = deps["QSS"]

    # ─── High DPI ───
    _setup_high_dpi(QApplication, Qt)

    # ─── QApplication ───
    app = QApplication(sys.argv)
    app.setApplicationName("Position Saver")
    app.setOrganizationName("OptionScanner")
    app.setApplicationDisplayName(
        "مدیریت و ثبت موقعیت‌های استراتژی آپشن")

    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)

    # ─── QSS ───
    if QSS:
        try:
            app.setStyleSheet(QSS)
            logger.info("Theme applied")
        except Exception as e:
            logger.warning(f"Theme apply failed: {e}")

    # ─── فونت ───
    try:
        app.setFont(QFont("Tahoma", 9))
    except Exception:
        pass

    # ─── پنجره ───
    try:
        WindowClass = _build_standalone_window(deps)
        window = WindowClass()
        window.showMaximized()
        window.statusBar().showMessage(
            "✅ برنامه با موفقیت راه‌اندازی شد", 5000)
    except Exception as e:
        logger.exception(f"Failed to create window: {e}")
        QMessageBox.critical(
            None, "خطای راه‌اندازی",
            f"خطا در ساخت پنجره اصلی:\n\n{e}")
        return 1

    # ─── پاکسازی هنگام خروج ───
    def _on_about_to_quit():
        try:
            if hasattr(window, 'main_widget'):
                window.main_widget.stop_monitor()
        except Exception as e:
            logger.warning(f"Error on quit: {e}")

    app.aboutToQuit.connect(_on_about_to_quit)

    logger.info("Entering event loop")
    exit_code = app.exec()
    logger.info(f"Exiting with code {exit_code}")
    return exit_code


# ═══════════════════════════════════════════════════
# ۹. اجرای مستقیم
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[PositionSaver] Interrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\n[PositionSaver] Fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)