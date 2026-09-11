# ui/workers.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import queue
import socket
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, QTimer, Signal

# تلاش برای خواندن مصرف رم با psutil؛ در صورت عدم نصب هندل می‌شود
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger("OptionScanner.UI.Workers")


# =========================================================================
# ۱. مدیریت بروزرسانی دسته‌ای (Batch Updates / Throttling)
# =========================================================================

class BatchUpdateManager(QObject):
    """
    مدیریت صف و بروزرسانی دسته‌ای داده‌های بازار و استراتژی‌ها
    برای جلوگیری از لگ و افت فریم رابط کاربری هنگام پردازش حجم بالای اطلاعات.
    """
    batch_ready = Signal(list)  # ارسال بسته‌ای از آیتم‌ها برای رندر در جدول

    def __init__(
        self, 
        interval_ms: int = 150, 
        max_batch_size: int = 100, 
        parent: Optional[Any] = None
    ):
        super().__init__(parent)
        self._queue: queue.Queue = queue.Queue()
        self._max_batch_size = max_batch_size
        
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    def push(self, item: Any) -> None:
        """افزودن یک آیتم به صف پردازش دسته‌ای"""
        self._queue.put(item)

    def push_many(self, items: list) -> None:
        """افزودن گروهی از آیتم‌ها به صف"""
        for it in items:
            self._queue.put(it)

    def clear(self) -> None:
        """پاک‌سازی صف جاری"""
        with self._queue.mutex:
            self._queue.queue.clear()

    def _flush(self) -> None:
        """تخلیه صف و ارسال داده‌ها به صورت پکیج به UI"""
        if self._queue.empty():
            return
        
        batch = []
        while not self._queue.empty() and len(batch) < self._max_batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
                
        if batch:
            self.batch_ready.emit(batch)


# =========================================================================
# ۲. ورکر تلمتری و پایش وضعیت سیستم و شبکه (Telemetry Worker)
# =========================================================================

class TelemetryWorker(QThread):
    """
    پایشگر پس‌زمینه برای اندازه‌گیری پینگ سرور، وضعیت اتصال و مصرف منابع (RAM).
    """
    telemetry_updated = Signal(dict)
    status_changed = Signal(str)

    def __init__(
        self, 
        host: str = "tsetmc.com", 
        port: int = 80, 
        interval_sec: float = 2.0, 
        parent: Optional[Any] = None
    ):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.interval_sec = interval_sec
        self._is_running = False
        self._mutex = QMutex()

    def run(self) -> None:
        with QMutexLocker(self._mutex):
            self._is_running = True

        process = psutil.Process() if HAS_PSUTIL else None

        while True:
            with QMutexLocker(self._mutex):
                if not self._is_running:
                    break

            # محاسبه پینگ واقعی TCP به سرور
            ping_ms = self._measure_ping(self.host, self.port)
            
            # محاسبه مصرف حافظه رم
            ram_mb = 0.0
            if process:
                try:
                    ram_mb = process.memory_info().rss / (1024 * 1024)
                except Exception:
                    ram_mb = 0.0

            telemetry_data = {
                "ping_ms": ping_ms,
                "connected": ping_ms >= 0,
                "ram_usage_mb": ram_mb,
                "timestamp": datetime.now()
            }

            self.telemetry_updated.emit(telemetry_data)

            # توقف پاسخ‌دهنده (پاسخ سریع به سیگنال توقف در گام‌های ۱۰۰ میلی‌ثانیه‌ای)
            steps = int(self.interval_sec * 10)
            for _ in range(max(steps, 1)):
                with QMutexLocker(self._mutex):
                    if not self._is_running:
                        break
                self.msleep(100)

    def _measure_ping(self, host: str, port: int) -> int:
        """بررسی زمان تاخیر اتصال به سرور مقصد"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            start = time.perf_counter()
            s.connect((host, port))
            latency = int((time.perf_counter() - start) * 1000)
            s.close()
            return latency
        except Exception:
            return -1

    def stop(self) -> None:
        """توقف ایمن ترد پایش"""
        with QMutexLocker(self._mutex):
            self._is_running = False
        self.wait()


# =========================================================================
# ۳. ورکر اسکنر بازار (Scanner Worker)
# =========================================================================

class ScannerWorker(QThread):
    """
    ورکر پس‌زمینه برای اجرای اسکنر بازار بدون هنگ کردن UI
    """
    
    # سیگنال‌ها
    scan_finished = Signal(object)       # ارسال نتایج اسکن
    scan_failed = Signal(str)            # ارسال خطا
    progress_updated = Signal(int, str)  # (درصد, متن وضعیت)
    status_changed = Signal(str)         # تغییر وضعیت
    
    def __init__(
        self, 
        scanner_engine: Any,
        parent: Optional[Any] = None,
        auto_stop_timeout: int = 300  # ۵ دقیقه تایم‌اوت
    ):
        super().__init__(parent)
        self.scanner_engine = scanner_engine
        self.auto_stop_timeout = auto_stop_timeout
        
        # مدیریت توقف و همزمانی
        self._is_running = False
        self._should_stop = False
        self._mutex = QMutex()
        
        # ذخیره زمان شروع و پایان
        self.start_time = None
        self.end_time = None
    
    @property
    def is_running(self) -> bool:
        """بررسی ایمن وضعیت اجرای ورکر"""
        with QMutexLocker(self._mutex):
            return self._is_running
    
    @property
    def execution_time(self) -> Optional[float]:
        """مدت زمان اجرا به ثانیه"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    def stop(self) -> None:
        """درخواست توقف امن اسکن"""
        with QMutexLocker(self._mutex):
            self._should_stop = True
        self.status_changed.emit("⏹️ توقف درخواست شد...")
        logger.info("Scan stop request registered")
    
    def run(self) -> None:
        """اجرای اصلی اسکن در ترد پس‌زمینه"""
        self.start_time = datetime.now()
        
        with QMutexLocker(self._mutex):
            if self._is_running:
                logger.warning("Scan is already running")
                return
            self._is_running = True
            self._should_stop = False
        
        try:
            logger.info("Background scan process started")
            self.status_changed.emit("🔄 اسکن بازار در حال انجام...")
            self.progress_updated.emit(0, "آماده‌سازی برای اسکن...")
            
            # بررسی توقف قبل از شروع
            if self._check_stop():
                self._handle_stop_request()
                return
            
            # اجرای اسکن با نمایش پیشرفت
            results = self._run_with_progress()
            
            # بررسی توقف بعد از اسکن
            if self._check_stop():
                self._handle_stop_request()
                return
            
            # ارسال نتایج
            self.end_time = datetime.now()
            exec_time = self.execution_time or 0.0
            
            if results is not None and len(results) > 0:
                logger.info(f"Scan complete - {len(results)} result(s) found")
                self.status_changed.emit(f"✅ اسکن کامل شد ({len(results)} نتیجه)")
                self.progress_updated.emit(100, f"اسکن کامل شد - {exec_time:.1f} ثانیه")
                self.scan_finished.emit(results)
            else:
                logger.warning("Scan complete, but no results found")
                self.status_changed.emit("⚠️ هیچ نتیجه‌ای یافت نشد")
                self.scan_finished.emit([])
                
        except Exception as e:
            self._handle_error(e)
        finally:
            with QMutexLocker(self._mutex):
                self._is_running = False
            logger.info("Background scan process finished")
    
    def _run_with_progress(self) -> Any:
        """اجرای اسکن بر اساس متدهای موجود در موتور اسکنر"""
        if hasattr(self.scanner_engine, 'run_scan_with_progress'):
            return self.scanner_engine.run_scan_with_progress(
                progress_callback=self._update_progress,
                stop_check_callback=self._check_stop
            )
        
        if hasattr(self.scanner_engine, 'run_scan'):
            return self.scanner_engine.run_scan()
        
        raise AttributeError("scanner_engine باید متد run_scan یا run_scan_with_progress داشته باشد")
    
    def _update_progress(self, percent: int, status: str = "") -> None:
        """به‌روزرسانی پیشرفت"""
        if self._check_stop():
            return
        self.progress_updated.emit(min(max(percent, 0), 100), status)
        self.status_changed.emit(status)
    
    def _check_stop(self) -> bool:
        """بررسی ایمن درخواست توقف"""
        with QMutexLocker(self._mutex):
            return self._should_stop
    
    def _handle_stop_request(self) -> None:
        """مدیریت درخواست توقف"""
        logger.info("Scan stopped by user")
        self.status_changed.emit("⏹️ اسکن متوقف شد")
        self.scan_failed.emit("اسکن توسط کاربر متوقف شد")
    
    def _handle_error(self, error: Exception) -> None:
        """مدیریت خطاهای رخ‌داده"""
        error_msg = str(error)
        error_trace = traceback.format_exc()
        
        logger.error(f"Error during scan: {error_msg}")
        logger.debug(f"Traceback: {error_trace}")
        
        friendly_error = self._get_friendly_error(error)
        self.scan_failed.emit(friendly_error)
        self.status_changed.emit(f"❌ {friendly_error}")
    
    def _get_friendly_error(self, error: Exception) -> str:
        """تبدیل خطا به پیام کاربرپسند"""
        error_msg = str(error).lower()
        
        if "timeout" in error_msg:
            return "⏱️ زمان اسکن به پایان رسید. لطفاً مجدداً تلاش کنید."
        elif "connection" in error_msg or "network" in error_msg:
            return "🌐 مشکل در اتصال به شبکه/اینترنت. اتصال خود را بررسی کنید."
        elif "api" in error_msg or "key" in error_msg:
            return "🔑 خطا در احراز هویت API. تنظیمات را بررسی کنید."
        elif "permission" in error_msg or "access" in error_msg:
            return "🔒 خطای دسترسی. مجوزهای لازم را بررسی کنید."
        else:
            return f"خطا: {str(error)}"




class BrokerLoginWorker(QThread):
    """
    ورکر پس‌زمینه برای باز کردن مرورگر کارگزاری و انتظار برای ورود کاربر.
    UI را بلاک نمی‌کند.

    Signals:
        login_success:  پس از ورود موفق کاربر emit می‌شود
        login_failed:   پس از خطا یا timeout emit می‌شود (پیام خطا)
        status_changed: پیام وضعیت برای نوار status
    """

    login_success  = Signal()       # ورود موفق
    login_failed   = Signal(str)    # پیام خطا
    status_changed = Signal(str)    # وضعیت

    def __init__(self, broker: Any, parent: Optional[Any] = None):
        """
        Args:
            broker: نمونه OmexKhobreganBroker
        """
        super().__init__(parent)
        self.broker = broker
        self._should_stop = False

    def stop(self) -> None:
        self._should_stop = True

    def run(self) -> None:
        try:
            self.status_changed.emit("🌐 در حال باز کردن مرورگر...")

            if not self.broker.open_browser():
                self.login_failed.emit("خطا در باز کردن مرورگر. Firefox نصب است؟")
                return

            if self._should_stop:
                return

            self.status_changed.emit(
                "⌨️ لطفاً کپچا را حل کرده و وارد سامانه شوید..."
            )

            success = self.broker.wait_for_login(timeout=180)

            if self._should_stop:
                return

            if success:
                self.status_changed.emit("✅ اتصال به کارگزاری برقرار شد")
                self.login_success.emit()
            else:
                self.login_failed.emit("زمان انتظار برای ورود به پایان رسید")

        except Exception as e:
            self.login_failed.emit(f"خطا در اتصال به کارگزاری: {e}")


class BrokerExecutionWorker(QThread):
    """
    ورکر پس‌زمینه برای ارسال (پیش‌پرکردن فرم برآورد) یک استراتژی به کارگزاری.

    نکته‌ی مهم درباره‌ی ایمنی معاملاتی: OmexKhobreganBroker.submit_strategy()
    صرفاً فرم «برآورد جدید» را پر می‌کند (سطرها، بازه‌ی نمودار، عنوان) و در
    کل مسیر اجرا هیچ دکمه‌ی «ارسال/ثبت نهایی سفارش»ی کلیک نمی‌شود — این مورد
    مستقیماً در automation/brokers/Omex_khobregan.py بررسی و تأیید شد. یعنی
    تأیید نهایی همیشه دستی و توسط خودِ کاربر در مرورگر انجام می‌شود، و اجرای
    این عملیات در یک Thread جدا هیچ تغییری در رفتار معاملاتی برنامه ایجاد
    نمی‌کند؛ فقط از فریز شدن پنجره‌ی اصلی حین انتظار برای Selenium/شبکه
    جلوگیری می‌کند.

    Signals:
        status_changed:     پیام وضعیت میانی برای نوار status
        execution_finished: (success, message) پس از پایان عملیات
    """

    status_changed = Signal(str)
    execution_finished = Signal(bool, str)

    def __init__(self, broker: Any, positions_text: str, parent: Optional[Any] = None):
        super().__init__(parent)
        self.broker = broker
        self.positions_text = positions_text
        self._should_stop = False

    def stop(self) -> None:
        self._should_stop = True

    def run(self) -> None:
        try:
            self.status_changed.emit("🔎 در حال بررسی موقعیت‌های باز کارگزاری...")
            existing = (
                self.broker.extract_open_positions()
                if hasattr(self.broker, 'extract_open_positions')
                else []
            )

            if self._should_stop:
                return

            self.status_changed.emit("⏳ در حال پر کردن فرم برآورد در کارگزاری...")
            result = self.broker.submit_strategy(self.positions_text, existing)

            if self._should_stop:
                return

            success = bool(result.get('success', False))
            default_msg = 'سفارش با موفقیت ثبت شد' if success else 'خطا در ثبت سفارش'
            message = result.get('message', default_msg)
            self.execution_finished.emit(success, message)

        except Exception as e:
            logger.error(f"خطا در اجرای BrokerExecutionWorker: {e}", exc_info=True)
            self.execution_finished.emit(False, f"خطا در ارتباط با کارگزاری: {e}")