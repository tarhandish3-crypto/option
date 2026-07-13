# option-portfolio-tracker
Covered Call Portfolio Tracker Portfolio Tracker For Tehran Exchange Market Option Traders
option-portfolio-tracker

ردیاب پرتفوی اختیار معامله
این پروژه یک برنامه پایتون جهت بررسی وضعیت کاوردکال های خریداری شده است که داده‌های زنده بازار سهام را نظارت کرده و با استفاده از رابط کاربری PyQt5 نمایش می‌دهد. داده های زنده گرفته شده برای نمایش معیارهای مختلف از جمله گزینه‌های خرید، سرمایه بازار و غیره پردازش می‌شوند.

ویژگی‌ها
دریافت و پردازش داده‌های بازار سهام بصورت زنده
نمایش داده‌ها در یک نمای جدول قابل مرتب‌سازی
برجسته‌سازی معیارهای مهم با کد رنگی
به‌روزرسانی خودکار داده‌ها هر ۵ ثانیه
ذخیره داده‌های به‌روزرسانی شده در یک فایل اکسل (opt_hist_updated.xlsx)
نیازمندی‌ها
پایتون 3.x
pandas
numpy
jdatetime
requests
fake_useragent
PyQt5
نصب
Repo را کلون کنید:
```
git clone https://github.com/Pooria-Moosavi/option-portfolio-tracker.git
cd option-portfolio-tracker
```
بسته‌های مورد نیاز را نصب کنید:
```
pip install pandas numpy jdatetime requests fake_useragent PyQt5 openpyxl
```
مطمئن شوید که یک فایل اکسل با نام opt hist.xlsx در دایرکتوری پروژه با داده‌های تاریخی لازم دارید.

استفاده
برنامه را اجرا کنید:
```
python main.py
```
رابط کاربری داده‌های بازار سهام را در یک جدول نمایش می‌دهد. این داده‌ها هر ۵ ثانیه به‌روزرسانی می‌شوند.

ساختار کد
main.py: کد اصلی برنامه که شامل دریافت داده‌ها، پردازش و راه‌اندازی رابط کاربری است.
days_difference: تابعی برای محاسبه فاصله روزها بین دو تاریخ شمسی.
DataFetcher: کلاسی از QThread برای دریافت و پردازش داده‌های بازار.
PandasModel: زیرکلاسی از QAbstractTableModel برای اتصال pandas DataFrame با PyQt5 TableView.
MainWindow: زیرکلاسی از QMainWindow برای تنظیم رابط کاربری.
مشارکت
برای مشارکت و رفع اشکال لطفا مخزن را فورک کرده و pull request برای هرگونه بهبود یا رفع اشکال ارسال کنید.

مجوز
این پروژه تحت لیسانس GNU V.3 است.

Option Portfolio Tracker
This project is a Python application that monitors stock market data in real-time and displays it using a PyQt5 GUI. The data is fetched from an external API and processed to show various metrics including call options, market cap, and more.

Features
Real-time stock market data fetching and processing
Displays data in a sortable table view
Highlights significant metrics with color coding
Automatically refreshes data every 5 seconds
Saves updated data to an Excel file (opt_hist_updated.xlsx)
Requirements
Python 3.x
pandas
numpy
jdatetime
requests
fake_useragent
PyQt5
Installation
Clone the repository:

```
git clone https://github.com/Pooria-Moosavi/option-portfolio-tracker.git
cd option-portfolio-tracker
```
Install the required packages:

pip install pandas numpy jdatetime requests fake_useragent PyQt5
Ensure you have an Excel file named opt hist.xlsx in the project directory with the necessary historical data.

Usage
Run the application:
```
python main.py
```
The GUI will display the stock market data in a table. It refreshes every 5 seconds.

Code Structure
main.py: Main application code that includes data fetching, processing, and GUI setup.
days_difference: Function to calculate the difference in days between two Persian dates.
DataFetcher: QThread class to fetch and process market data.
PandasModel: QAbstractTableModel subclass to interface pandas DataFrame with PyQt5 TableView.
MainWindow: QMainWindow subclass to set up the GUI.
Contributing
Contributions are welcome! Please fork the repository and submit a pull request for any enhancements or bug fixes.

License
This project is licensed under the GNU V.3 License.
