# ui/workers.py
# -*- coding: utf-8 -*-

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
from typing import Optional, Any, Callable
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)


class ScannerWorker(QThread):
    """
    ورکر پس‌زمینه برای اجرای اسکنر بازار بدون هنگ کردن UI
    """
    
    # سیگنال‌ها
    scan_finished = Signal(object)      # ارسال نتایج اسکن
    scan_failed = Signal(str)           # ارسال خطا
    progress_updated = Signal(int, str) # (درصد, متن وضعیت)
    status_changed = Signal(str)        # تغییر وضعیت
    
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
        logger.info("درخواست توقف اسکن ثبت شد")
    
    def run(self) -> None:
        """اجرای اصلی اسکن در ترد پس‌زمینه"""
        self.start_time = datetime.now()
        
        with QMutexLocker(self._mutex):
            if self._is_running:
                logger.warning("اسکن قبلاً در حال اجراست")
                return
            self._is_running = True
            self._should_stop = False
        
        try:
            logger.info("🚀 فرایند اسکن در پس‌زمینه شروع شد...")
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
                logger.info(f"✅ اسکن کامل شد - {len(results)} نتیجه یافت شد")
                self.status_changed.emit(f"✅ اسکن کامل شد ({len(results)} نتیجه)")
                self.progress_updated.emit(100, f"اسکن کامل شد - {exec_time:.1f} ثانیه")
                self.scan_finished.emit(results)
            else:
                logger.warning("⚠️ اسکن کامل شد، اما هیچ نتیجه‌ای یافت نشد")
                self.status_changed.emit("⚠️ هیچ نتیجه‌ای یافت نشد")
                self.scan_finished.emit([])
                
        except Exception as e:
            self._handle_error(e)
        finally:
            with QMutexLocker(self._mutex):
                self._is_running = False
            logger.info("🏁 فرایند اسکن پایان یافت")
    
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
        logger.info("⏹️ اسکن توسط کاربر متوقف شد")
        self.status_changed.emit("⏹️ اسکن متوقف شد")
        self.scan_failed.emit("اسکن توسط کاربر متوقف شد")
    
    def _handle_error(self, error: Exception) -> None:
        """مدیریت خطاهای رخ‌داده"""
        error_msg = str(error)
        error_trace = traceback.format_exc()
        
        logger.error(f"❌ خطا در اسکن: {error_msg}")
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


class AutoScannerWorker(QThread):
    """
    ورکر خودکار برای اجرای دوره‌ای اسکن
    """
    
    scan_requested = Signal()  # درخواست اسکن جدید
    status_changed = Signal(str)
    
    def __init__(
        self,
        interval_minutes: int = 5,
        parent: Optional[Any] = None
    ):
        super().__init__(parent)
        self.interval_minutes = interval_minutes
        self._is_running = False
        self._should_stop = False
        self._mutex = QMutex()
    
    def run(self) -> None:
        """اجرای تایمر خودکار بدون بلوک کردن Thread با msleep"""
        with QMutexLocker(self._mutex):
            self._is_running = True
            self._should_stop = False
        
        logger.info(f"⏱️ تایمر خودکار شروع شد - هر {self.interval_minutes} دقیقه")
        self.status_changed.emit(f"⏱️ اسکن خودکار هر {self.interval_minutes} دقیقه")
        
        while True:
            with QMutexLocker(self._mutex):
                if self._should_stop or not self._is_running:
                    break
            
            # ارسال سیگنال درخواست اسکن
            self.scan_requested.emit()
            
            # منتظر ماندن (بررسی هر ۱۰۰ میلی‌ثانیه برای پاسخ‌دهی سریع به توقف)
            total_ms = self.interval_minutes * 60 * 1000
            elapsed = 0
            while elapsed < total_ms:
                with QMutexLocker(self._mutex):
                    if self._should_stop:
                        break
                self.msleep(100)
                elapsed += 100
        
        logger.info("⏹️ تایمر خودکار متوقف شد")
        self.status_changed.emit("⏹️ اسکن خودکار غیرفعال شد")
    
    def stop(self) -> None:
        """توقف ایمن تایمر خودکار"""
        with QMutexLocker(self._mutex):
            self._should_stop = True
            self._is_running = False
        logger.info("درخواست توقف تایمر خودکار ثبت شد")


class StrategyExecutorWorker(QThread):
    """
    ورکر برای اجرای خودکار یا دستی استراتژی در کارگزاری
    """
    
    execution_finished = Signal(bool, str)  # (موفقیت, پیام)
    progress_updated = Signal(int, str)
    
    def __init__(
        self,
        strategy_data: dict,
        broker_adapter: Any,
        parent: Optional[Any] = None
    ):
        super().__init__(parent)
        self.strategy_data = strategy_data or {}
        self.broker_adapter = broker_adapter
    
    def run(self) -> None:
        """اجرای استراتژی در کارگزاری"""
        try:
            strat_name = self.strategy_data.get('name', self.strategy_data.get('strategy_name', 'Unknown'))
            logger.info(f"🚀 اجرای استراتژی در کارگزاری: {strat_name}")
            self.progress_updated.emit(0, "آماده‌سازی برای اجرا...")
            
            if not self._validate_strategy():
                self.execution_finished.emit(False, "داده‌های استراتژی نامعتبر یا ناقص است")
                return
            
            self.progress_updated.emit(30, "اتصال به کارگزاری...")
            
            result = self.broker_adapter.execute_strategy(self.strategy_data)
            
            if isinstance(result, dict) and result.get('success', False):
                logger.info("✅ استراتژی با موفقیت اجرا شد")
                self.progress_updated.emit(100, "تکمیل اجرا")
                self.execution_finished.emit(True, "استراتژی با موفقیت اجرا شد")
            else:
                error_msg = result.get('error', 'خطای ناشناخته در کارگزاری') if isinstance(result, dict) else str(result)
                logger.error(f"❌ خطا در اجرا: {error_msg}")
                self.execution_finished.emit(False, f"خطا: {error_msg}")
                
        except Exception as e:
            logger.error(f"❌ خطا در اجرای استراتژی: {str(e)}")
            self.execution_finished.emit(False, f"خطا: {str(e)}")
    
    def _validate_strategy(self) -> bool:
        """اعتبارسنجی انعطاف‌پذیر داده‌های استراتژی"""
        if not self.strategy_data:
            return False
            
        required_fields = ['symbol', 'name']
        for field in required_fields:
            if field not in self.strategy_data and not hasattr(self.strategy_data, field):
                # چک کردن نام‌های جایگزین مانند strategy_name
                if field == 'name' and 'strategy_name' in self.strategy_data:
                    continue
                logger.error(f"فیلد {field} در داده‌های استراتژی وجود ندارد")
                return False
        return True


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

    def __init__(self, broker, parent=None):
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
