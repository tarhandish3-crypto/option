# position_saver/main.py
# -*- coding: utf-8 -*-

"""
نقطه ورود مستقل برنامه "مدیریت و ثبت موقعیت‌های استراتژی آپشن".
"""

import os
import sys

# افزودن مسیر ریشه پروژه اصلی به sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

from position_saver.ui.main_widget import PositionSaverWidget


class StandalonePositionSaverWindow(QMainWindow):
    """
    پنجره اصلی برای اجرای مستقل.
    در حالت الحاق به برنامه اصلی، از این کلاس استفاده نمی‌شود.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("مدیریت و ثبت موقعیت‌های استراتژی آپشن")
        self.setLayoutDirection(Qt.RightToLeft)

        # ویجت مرکزی
        self.main_widget = PositionSaverWidget(self)
        self.setCentralWidget(self.main_widget)

    def closeEvent(self, event):
        # توقف ترد پس‌زمینه قبل از بستن
        self.main_widget.stop_monitor()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = StandalonePositionSaverWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()