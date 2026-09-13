# ui/workers.py
# -*- coding: utf-8 -*-

"""
ماژول ورکرهای پس‌زمینه برنامه Option Strategy Scanner
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QThread,
    QTimer,
    Signal,
)

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
    برای جلوگیری از افت فریم رابط کاربری هنگام پردازش حجم بالای اطلاعات.

    الگو: صف thread-safe + تایمر Qt برای تخلیه دوره‌ای.
    """

    batch_ready = Signal(list)  # ارسال بسته‌ای از آیتم‌ها برای رندر در جدول

    def __init__(
        self,
        interval_ms: int = 150,
        max_batch_size: int = 100,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._max_batch_size = max(1, int(max_batch_size))

        self._timer = QTimer(self)
        self._timer.setInterval(max(10, int(interval_ms)))
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
        """پاک‌سازی صف جاری بدون دستکاری mutex خصوصی پایتون"""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def stop(self) -> None:
        """توقف تایمر و پاک‌سازی صف (برای فراخوانی هنگام بستن برنامه)"""
        self._timer.stop()
        self.clear()

    def _flush(self) -> None:
        """تخلیه صف و ارسال داده‌ها به صورت پکیج به UI"""
        if self._queue.empty():
            return

        batch: list[Any] = []
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

    ویژگی‌ها:
    - اندازه‌گیری پینگ TCP به سرور TSETMC
    - پایش مصرف RAM با psutil (اختیاری)
    - توقف پاسخ‌دهنده در گام‌های ۱۰۰ms
    - مقاوم در برابر خطاهای psutil.Process

    Signals:
        telemetry_updated: دیکشنری حاوی ping_ms, connected, ram_usage_mb, timestamp
        status_changed: پیام وضعیت (در حال حاضر استفاده نمی‌شود)
    """

    telemetry_updated = Signal(dict)
    status_changed = Signal(str)

    def __init__(
        self,
        host: str = "tsetmc.com",
        port: int = 80,
        interval_sec: float = 2.0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.port = int(port)
        self.interval_sec = max(0.5, float(interval_sec))
        self._is_running = False
        self._mutex = QMutex()

    # ──────────────────────────────────────────────────────────────
    # Thread Entrypoint
    # ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        with QMutexLocker(self._mutex):
            self._is_running = True

        # راه‌اندازی ایمن psutil.Process
        process = None
        if HAS_PSUTIL:
            try:
                process = psutil.Process()
            except Exception as e:
                logger.warning(f"Failed to access psutil.Process: {e}")
                process = None

        while True:
            with QMutexLocker(self._mutex):
                if not self._is_running:
                    break

            # محاسبه پینگ واقعی TCP به سرور
            ping_ms = self._measure_ping(self.host, self.port)

            # محاسبه مصرف حافظه رم
            ram_mb = 0.0
            if process is not None:
                try:
                    ram_mb = process.memory_info().rss / (1024 * 1024)
                except Exception:
                    ram_mb = 0.0

            telemetry_data = {
                "ping_ms": ping_ms,
                "connected": ping_ms >= 0,
                "ram_usage_mb": ram_mb,
                "timestamp": datetime.now(),
            }

            try:
                self.telemetry_updated.emit(telemetry_data)
            except RuntimeError:
                # آبجکت Qt ممکن است هنگام بسته شدن برنامه حذف شده باشد
                break

            # توقف پاسخ‌دهنده (پاسخ سریع به سیگنال توقف در گام‌های ۱۰۰ms)
            steps = int(self.interval_sec * 10)
            for _ in range(max(steps, 1)):
                with QMutexLocker(self._mutex):
                    if not self._is_running:
                        break
                self.msleep(100)

    # ──────────────────────────────────────────────────────────────
    # Ping Helper
    # ──────────────────────────────────────────────────────────────

    def _measure_ping(self, host: str, port: int) -> int:
        """
        بررسی زمان تأخیر اتصال به سرور مقصد با socket TCP.

        Returns:
            زمان تأخیر به میلی‌ثانیه یا -1 در صورت خطا/عدم اتصال.
        """
        sock: Optional[socket.socket] = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            start = time.perf_counter()
            sock.connect((host, port))
            return int((time.perf_counter() - start) * 1000)
        except Exception:
            return -1
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────────
    # Stop
    # ──────────────────────────────────────────────────────────────

    def stop(self, wait: bool = True, timeout_ms: int = 1500) -> None:
        """
        توقف ایمن ترد پایش.

        Args:
            wait: انتظار برای پایان واقعی ترد.
            timeout_ms: مهلت انتظار به میلی‌ثانیه.
        """
        with QMutexLocker(self._mutex):
            self._is_running = False

        if wait and not self.wait(timeout_ms):
            logger.warning(
                f"TelemetryWorker did not stop within {timeout_ms}ms. "
                "Forcing termination."
            )
            self.terminate()
            self.wait(500)


# =========================================================================
# ۳. ورکر اسکنر بازار (Scanner Worker)
# =========================================================================

class ScannerWorker(QThread):
    """
    ورکر پس‌زمینه برای اجرای اسکنر بازار بدون هنگ کردن UI.

    ویژگی‌ها:
    - پشتیبانی از timeout خودکار (auto_stop_timeout)
    - قطع‌پذیری از طریق _should_stop flag
    - تبدیل خطاهای فنی به پیام‌های کاربرپسند
    - ارسال پیشرفت به UI از طریق progress_updated

    Signals:
        scan_finished: نتایج اسکن (لیست Opportunity)
        scan_failed: پیام خطای کاربرپسند
        progress_updated: (درصد, متن وضعیت)
        status_changed: پیام وضعیت عمومی
    """

    scan_finished = Signal(object)
    scan_failed = Signal(str)
    progress_updated = Signal(int, str)
    status_changed = Signal(str)

    def __init__(
        self,
        scanner_engine: Any,
        parent: Optional[QObject] = None,
        auto_stop_timeout: int = 300,
    ) -> None:
        super().__init__(parent)
        self.scanner_engine = scanner_engine
        self.auto_stop_timeout = max(10, int(auto_stop_timeout))

        self._is_running = False
        self._should_stop = False
        self._mutex = QMutex()
        self._auto_stop_event = threading.Event()

        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    # ──────────────────────────────────────────────────────────────
    # Properties
    # ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """بررسی ایمن وضعیت اجرای ورکر"""
        with QMutexLocker(self._mutex):
            return self._is_running

    @property
    def execution_time(self) -> Optional[float]:
        """مدت زمان اجرا به ثانیه (None اگر شروع یا پایان ثبت نشده باشد)"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    # ──────────────────────────────────────────────────────────────
    # Stop
    # ──────────────────────────────────────────────────────────────

    def stop(self, wait: bool = False, timeout_ms: int = 3000) -> None:
        """
        درخواست توقف اسکن.

        Args:
            wait: انتظار برای پایان واقعی ترد.
            timeout_ms: مهلت انتظار به میلی‌ثانیه.
        """
        with QMutexLocker(self._mutex):
            self._should_stop = True

        self._auto_stop_event.set()  # آزادسازی thread timeout در صورت انتظار

        try:
            self.status_changed.emit("⏹️ توقف درخواست شد...")
        except RuntimeError:
            pass

        logger.info("Scan stop request registered")

        if wait and not self.wait(timeout_ms):
            logger.warning(
                f"ScannerWorker did not stop within {timeout_ms}ms. "
                "User should close application manually or wait."
            )

    # ──────────────────────────────────────────────────────────────
    # Thread Entrypoint
    # ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.start_time = datetime.now()

        with QMutexLocker(self._mutex):
            if self._is_running:
                logger.warning("Scan is already running")
                return
            self._is_running = True
            self._should_stop = False

        # تایمر توقف خودکار (در ترد جداگانه)
        auto_stop_thread: Optional[threading.Thread] = None
        if self.auto_stop_timeout > 0:
            self._auto_stop_event.clear()
            auto_stop_thread = threading.Thread(
                target=self._auto_stop_loop,
                daemon=True,
                name="ScannerAutoStopTimer",
            )
            auto_stop_thread.start()

        try:
            logger.info("Background scan process started")
            self._safe_emit_status("🔄 اسکن بازار در حال انجام...")
            self._safe_emit_progress(0, "آماده‌سازی برای اسکن...")

            if self._check_stop():
                self._handle_stop_request()
                return

            results = self._run_with_progress()

            if self._check_stop():
                self._handle_stop_request()
                return

            self.end_time = datetime.now()
            exec_time = self.execution_time or 0.0

            if results is not None and len(results) > 0:
                logger.info(f"Scan complete - {len(results)} result(s) found")
                self._safe_emit_status(
                    f"✅ اسکن کامل شد ({len(results)} نتیجه)")
                self._safe_emit_progress(
                    100, f"اسکن کامل شد - {exec_time:.1f} ثانیه"
                )
                self.scan_finished.emit(results)
            else:
                logger.warning("Scan complete, but no results found")
                self._safe_emit_status("⚠️ هیچ نتیجه‌ای یافت نشد")
                self.scan_finished.emit([])

        except Exception as e:
            self._handle_error(e)
        finally:
            # آزادسازی تایمر توقف خودکار
            self._auto_stop_event.set()
            if auto_stop_thread is not None and auto_stop_thread.is_alive():
                auto_stop_thread.join(timeout=1.0)

            with QMutexLocker(self._mutex):
                self._is_running = False
            logger.info("Background scan process finished")

    # ──────────────────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────────────────

    def _auto_stop_loop(self) -> None:
        """
        ترد جانبی برای توقف خودکار اسکن پس از auto_stop_timeout.
        با threading.Event قابل لغو است.
        """
        if self._auto_stop_event.wait(timeout=self.auto_stop_timeout):
            # رویداد توسط finally یا stop() تنظیم شده؛ یعنی توقف عادی
            return

        # اگر به اینجا برسیم یعنی timeout شده
        with QMutexLocker(self._mutex):
            if not self._is_running or self._should_stop:
                return
            self._should_stop = True

        logger.warning(
            f"Scan auto-stopped after {self.auto_stop_timeout}s timeout"
        )
        self._safe_emit_status(
            f"⏱️ توقف خودکار اسکن پس از {self.auto_stop_timeout} ثانیه"
        )

    def _safe_emit_status(self, msg: str) -> None:
        """ارسال ایمن سیگنال وضعیت (مقاوم در برابر حذف شدن آبجکت)"""
        try:
            self.status_changed.emit(msg)
        except RuntimeError:
            pass

    def _safe_emit_progress(self, percent: int, status: str = "") -> None:
        """ارسال ایمن سیگنال پیشرفت"""
        try:
            self.progress_updated.emit(percent, status)
        except RuntimeError:
            pass

    def _run_with_progress(self) -> Any:
        """اجرای اسکن بر اساس متدهای موجود در موتور اسکنر"""
        engine = self.scanner_engine

        if hasattr(engine, "run_scan_with_progress"):
            return engine.run_scan_with_progress(
                progress_callback=self._update_progress,
                stop_check_callback=self._check_stop,
            )

        if hasattr(engine, "run_scan"):
            return engine.run_scan()

        raise AttributeError(
            "موتور اسکنر باید یکی از متدهای 'run_scan' یا "
            "'run_scan_with_progress' را پیاده‌سازی کند."
        )

    def _update_progress(self, percent: int, status: str = "") -> None:
        """به‌روزرسانی پیشرفت (توسط اسکنر صدا زده می‌شود)"""
        if self._check_stop():
            return
        self._safe_emit_progress(min(max(percent, 0), 100), status)
        self._safe_emit_status(status)

    def _check_stop(self) -> bool:
        """بررسی ایمن درخواست توقف"""
        with QMutexLocker(self._mutex):
            return self._should_stop

    def _handle_stop_request(self) -> None:
        """مدیریت درخواست توقف (ارسال پیام نهایی)"""
        logger.info("Scan stopped by user or timeout")
        self._safe_emit_progress(0, "⏹️ اسکن متوقف شد")
        self._safe_emit_status("⏹️ اسکن متوقف شد")
        try:
            self.scan_failed.emit("اسکن توسط کاربر متوقف شد")
        except RuntimeError:
            pass

    def _handle_error(self, error: Exception) -> None:
        """مدیریت خطاهای رخ‌داده در اسکن"""
        error_msg = str(error)
        error_trace = traceback.format_exc()

        logger.error(f"Error during scan: {error_msg}")
        logger.debug(f"Traceback: {error_trace}")

        friendly_error = self._get_friendly_error(error)
        try:
            self.scan_failed.emit(friendly_error)
        except RuntimeError:
            pass
        self._safe_emit_status(f"❌ {friendly_error}")

    def _get_friendly_error(self, error: Exception) -> str:
        """تبدیل خطای فنی به پیام کاربرپسند"""
        error_msg = str(error).lower()

        if isinstance(error, TimeoutError) or "timeout" in error_msg:
            return "⏱️ زمان اسکن به پایان رسید. لطفاً مجدداً تلاش کنید."
        if "connection" in error_msg or "network" in error_msg:
            return "🌐 مشکل در اتصال به شبکه/اینترنت. اتصال خود را بررسی کنید."
        if "api" in error_msg or "key" in error_msg:
            return "🔑 خطا در احراز هویت API. تنظیمات را بررسی کنید."
        if "permission" in error_msg or "access" in error_msg:
            return "🔒 خطای دسترسی. مجوزهای لازم را بررسی کنید."
        if "no module" in error_msg or "import" in error_msg:
            return f"📦 خطای وابستگی: {error}"
        return f"خطا: {error}"


# =========================================================================
# ۴. ورکر ورود به کارگزاری (Broker Login Worker)
# =========================================================================

class BrokerLoginWorker(QThread):
    """
    ورکر پس‌زمینه برای باز کردن مرورگر کارگزاری و انتظار برای ورود کاربر.
    UI را بلاک نمی‌کند.

    نکات ایمنی:
    - در صورت درخواست توقف، مرورگر به صورت ایمن بسته می‌شود.
    - اگر broker متد close_browser نداشته باشد، نادیده گرفته می‌شود.

    Signals:
        login_success:  پس از ورود موفق کاربر emit می‌شود
        login_failed:   پس از خطا یا timeout emit می‌شود (پیام خطا)
        status_changed: پیام وضعیت برای نوار status
    """

    login_success = Signal()
    login_failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, broker: Any, parent: Optional[QObject] = None) -> None:
        """
        Args:
            broker: نمونه OmexKhobreganBroker (یا هر بروکر با API مشابه)
        """
        super().__init__(parent)
        self.broker = broker
        self._should_stop = False
        self._stop_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────
    # Stop
    # ──────────────────────────────────────────────────────────────

    def stop(self, wait: bool = True, timeout_ms: int = 2000) -> None:
        """
        درخواست توقف ورود به کارگزاری.

        Args:
            wait: انتظار برای پایان ترد.
            timeout_ms: مهلت انتظار به میلی‌ثانیه.
        """
        with self._stop_lock:
            self._should_stop = True

        # تلاش برای بستن مرورگر به صورت ایمن
        self._safe_close_browser()

        if wait and not self.wait(timeout_ms):
            logger.warning(
                f"BrokerLoginWorker did not stop within {timeout_ms}ms"
            )

    def _is_stopped(self) -> bool:
        with self._stop_lock:
            return self._should_stop

    def _safe_close_browser(self) -> None:
        """بستن ایمن مرورگر (در صورت پشتیبانی بروکر)"""
        if self.broker is None:
            return
        try:
            if hasattr(self.broker, "close_browser"):
                self.broker.close_browser()
        except Exception as e:
            logger.debug(f"Error closing broker browser: {e}")

    def _safe_emit_status(self, msg: str) -> None:
        try:
            self.status_changed.emit(msg)
        except RuntimeError:
            pass

    # ──────────────────────────────────────────────────────────────
    # Thread Entrypoint
    # ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._safe_emit_status("🌐 در حال باز کردن مرورگر...")

            if self._is_stopped():
                return

            if self.broker is None:
                self.login_failed.emit("بروکر مقداردهی نشده است")
                return

            # باز کردن مرورگر
            if not self.broker.open_browser():
                self.login_failed.emit(
                    "خطا در باز کردن مرورگر. Firefox نصب است؟"
                )
                return

            if self._is_stopped():
                self._safe_close_browser()
                return

            self._safe_emit_status(
                "⌨️ لطفاً کپچا را حل کرده و وارد سامانه شوید..."
            )

            # انتظار برای ورود (با امکان قطع‌پذیری)
            wait_fn = getattr(self.broker, "wait_for_login", None)
            if wait_fn is None:
                self.login_failed.emit(
                    "متد wait_for_login در بروکر پیاده‌سازی نشده است"
                )
                return

            # اگر متد از stop_check پشتیبانی می‌کند، پاس بده
            success = self._call_wait_for_login(wait_fn, timeout=180)

            if self._is_stopped():
                self._safe_close_browser()
                return

            if success:
                self._safe_emit_status("✅ اتصال به کارگزاری برقرار شد")
                self.login_success.emit()
            else:
                self.login_failed.emit("زمان انتظار برای ورود به پایان رسید")

        except Exception as e:
            logger.error(f"Error in BrokerLoginWorker: {e}", exc_info=True)
            self.login_failed.emit(f"خطا در اتصال به کارگزاری: {e}")

    def _call_wait_for_login(
        self, wait_fn: Callable[..., bool], timeout: int = 180
    ) -> bool:
        """
        فراخوانی wait_for_login با پشتیبانی از stop_check در صورت وجود.

        روش: بررسی امضای تابع با inspect و پاس دادن stop_check در صورت امکان.
        """
        import inspect

        try:
            sig = inspect.signature(wait_fn)
            params = sig.parameters
        except (ValueError, TypeError):
            params = {}

        # اگر stop_check یا callback مشابه پشتیبانی می‌شود، پاس بده
        kwargs: dict = {}
        if "stop_check" in params:
            kwargs["stop_check"] = self._is_stopped
        elif "stop_callback" in params:
            kwargs["stop_callback"] = self._is_stopped

        if "timeout" in params:
            kwargs["timeout"] = timeout

        try:
            return bool(wait_fn(**kwargs))
        except TypeError:
            # اگر امضای تابع دقیقاً مطابق نبود، با آرگومان‌های پیش‌فرض صدا بزن
            try:
                return bool(wait_fn(timeout))
            except TypeError:
                return bool(wait_fn())


# =========================================================================
# ۵. ورکر اجرای سفارش کارگزاری (Broker Execution Worker)
# =========================================================================

class BrokerExecutionWorker(QThread):
    """
    ورکر پس‌زمینه برای ارسال (پیش‌پرکردن فرم برآورد) یک استراتژی به کارگزاری.

    ⚠️ نکته‌ی مهم امنیتی:
        OmexKhobreganBroker.submit_strategy() صرفاً فرم «برآورد جدید» را پر
        می‌کند (سطرها، بازه‌ی نمودار، عنوان) و در کل مسیر اجرا هیچ دکمه‌ی
        «ارسال/ثبت نهایی سفارش»ی کلیک نمی‌شود — تأیید نهایی همیشه دستی و
        توسط خودِ کاربر در مرورگر انجام می‌شود.

    Signals:
        status_changed:     پیام وضعیت میانی برای نوار status
        execution_finished: (success, message) پس از پایان عملیات
    """

    status_changed = Signal(str)
    execution_finished = Signal(bool, str)

    def __init__(
        self,
        broker: Any,
        positions_text: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.broker = broker
        self.positions_text = positions_text
        self._should_stop = False
        self._stop_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────
    # Stop
    # ──────────────────────────────────────────────────────────────

    def stop(self, wait: bool = True, timeout_ms: int = 2000) -> None:
        with self._stop_lock:
            self._should_stop = True
        if wait and not self.wait(timeout_ms):
            logger.warning(
                f"BrokerExecutionWorker did not stop within {timeout_ms}ms"
            )

    def _is_stopped(self) -> bool:
        with self._stop_lock:
            return self._should_stop

    def _safe_emit_status(self, msg: str) -> None:
        try:
            self.status_changed.emit(msg)
        except RuntimeError:
            pass

    def _safe_emit_finished(self, success: bool, message: str) -> None:
        try:
            self.execution_finished.emit(success, message)
        except RuntimeError:
            pass

    # ──────────────────────────────────────────────────────────────
    # Thread Entrypoint
    # ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            if self.broker is None:
                self._safe_emit_finished(
                    False, "بروکر مقداردهی نشده است"
                )
                return

            self._safe_emit_status(
                "🔎 در حال بررسی موقعیت‌های باز کارگزاری..."
            )

            # استخراج موقعیت‌های موجود (در صورت پشتیبانی)
            existing: Any = []
            if hasattr(self.broker, "extract_open_positions"):
                try:
                    existing = self.broker.extract_open_positions() or []
                except Exception as e:
                    logger.warning(f"extract_open_positions failed: {e}")
                    existing = []

            if self._is_stopped():
                self._safe_emit_finished(False, "عملیات لغو شد")
                return

            self._safe_emit_status(
                "⏳ در حال پر کردن فرم برآورد در کارگزاری..."
            )

            result = self.broker.submit_strategy(
                self.positions_text, existing
            )

            if self._is_stopped():
                self._safe_emit_finished(False, "عملیات لغو شد")
                return

            # محافظت در برابر پاسخ‌های غیردیکشنری
            if not isinstance(result, dict):
                logger.error(
                    f"Broker returned unexpected result type: {type(result)}"
                )
                self._safe_emit_finished(
                    False, "پاسخ نامعتبر از کارگزاری دریافت شد"
                )
                return

            success = bool(result.get("success", False))
            default_msg = (
                "سفارش با موفقیت ثبت شد"
                if success
                else "خطا در ثبت سفارش"
            )
            message = str(result.get("message", default_msg))
            self._safe_emit_finished(success, message)

        except Exception as e:
            logger.error(
                f"خطا در اجرای BrokerExecutionWorker: {e}", exc_info=True
            )
            self._safe_emit_finished(
                False, f"خطا در ارتباط با کارگزاری: {e}"
            )
