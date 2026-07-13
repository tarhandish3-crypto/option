import sys
import os
import requests
import numpy as np
import datetime
import time
import pandas as pd
from persiantools.jdatetime import JalaliDate
from fake_useragent import UserAgent
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QLabel, QComboBox, QSplitter, QHBoxLayout
from PyQt5.QtCore import QAbstractTableModel, Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
import jdatetime
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def days_difference(start_persian_date, end_persian_date):
    if start_persian_date and end_persian_date:
        try:
            # Processing start_persian_date
            if len(start_persian_date) == 8 and '/' not in start_persian_date:
                start_jalali_date = jdatetime.date(int(start_persian_date[:4]), int(
                    start_persian_date[4:6]), int(start_persian_date[6:]))
            elif len(start_persian_date) == 6 and '/' not in start_persian_date:
                start_jalali_date = jdatetime.date(int(
                    start_persian_date[:2]) + 1400, int(start_persian_date[2:4]), int(start_persian_date[4:]))
            elif len(start_persian_date) == 8:
                start_jalali_date = jdatetime.date(int(
                    start_persian_date[:2]) + 1400, int(start_persian_date[3:5]), int(start_persian_date[6:]))
            elif len(start_persian_date) == 10:
                start_jalali_date = jdatetime.date(int(start_persian_date[:4]), int(
                    start_persian_date[5:7]), int(start_persian_date[8:]))
            else:
                print("Invalid start date format.")
                return None

            # Processing end_persian_date
            if len(end_persian_date) == 8 and '/' not in end_persian_date:
                end_jalali_date = jdatetime.date(int(end_persian_date[:4]), int(
                    end_persian_date[4:6]), int(end_persian_date[6:]))
            elif len(end_persian_date) == 6 and '/' not in end_persian_date:
                end_jalali_date = jdatetime.date(int(
                    end_persian_date[:2]) + 1400, int(end_persian_date[2:4]), int(end_persian_date[4:]))
            elif len(end_persian_date) == 8:
                end_jalali_date = jdatetime.date(int(
                    end_persian_date[:2]) + 1400, int(end_persian_date[3:5]), int(end_persian_date[6:]))
            elif len(end_persian_date) == 10:
                end_jalali_date = jdatetime.date(int(end_persian_date[:4]), int(
                    end_persian_date[5:7]), int(end_persian_date[8:]))
            else:
                print("Invalid end date format.")
                return None

            # Calculating difference
            difference = end_jalali_date - start_jalali_date
            return abs(difference.days)
        except ValueError:
            print("Date conversion error.")
            return None
    else:
        print("Date conversion failed.")
        return None


def clean_string(s):
    if isinstance(s, str):
        return unicodedata.normalize('NFKC', s).strip()
    return s

# Worker thread to fetch and process data


class DataFetcher(QThread):
    data_fetched = pyqtSignal(pd.DataFrame)

    def run(self):
        data = self.get_data()
        if data:
            df = self.process_data(data)
            if df is not None:
                self.data_fetched.emit(df)

    def get_data(self):
        headers = {'user-agent': UserAgent().random}
        try:
            response = requests.get(
                'http://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx', headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException:
            return None

    def process_data(self, main_text):
        # تقسیم بر اساس @
        parts = main_text.split('@')
        
        # بخش اول: اطلاعات کلی
        header_parts = parts[0].split(',')
        
        # پیدا کردن بخش داده‌های اصلی
        # بخش دوم شامل تاریخ و اطلاعات دیگر است
        data_section = None
        for i, part in enumerate(parts):
            if ';' in part and len(part) > 100:  # بخش داده‌ها
                data_section = part
                break
        
        if not data_section:
            return pd.DataFrame()
        
        # داده‌ها را با ; جدا کنید
        data_rows = data_section.split(';')
        
        # ایجاد لیست برای ذخیره داده‌ها
        all_data = []
        for row in data_rows:
            if row.strip():
                # هر ردیف با , جدا شده
                cols = row.split(',')
                if len(cols) >= 22:  # حداقل تعداد ستون‌ها
                    all_data.append(cols)
        
        if not all_data:
            return pd.DataFrame()
        
        # ایجاد DataFrame
        Mkt_df = pd.DataFrame(all_data)

        Mkt_df.columns = [
            'WEB-ID', 'Ticker-Code', 'Ticker', 'Name', 'Time', 'Open', 'Final', 'Close', 'No', 'Volume', 'Value',
            'Low', 'High', 'Y-Final', 'EPS', 'Base-Vol', 'Unknown1', 'Unknown2', 'Sector', 'Day_UL', 'Day_LL',
            'Share-No', 'Mkt-ID', 'Unknown3', 'Unknown4', 'Unknown6']

        Mkt_df['Market'] = Mkt_df['Mkt-ID'].map({
            '300': 'بورس', '303': 'فرابورس', '305': 'صندوق', '311': 'اختیار خرید', '312': 'اختیار فروش'})
        num_cols = ['Open', 'Final', 'Close', 'No', 'Volume', 'Value', 'Low', 'High', 'Y-Final', 'EPS', 'Base-Vol',
                    'Day_UL', 'Day_LL', 'Share-No']
        Mkt_df[num_cols] = Mkt_df[num_cols].apply(pd.to_numeric)
        Mkt_df['Time'] = Mkt_df['Time'].str[:-4] + ':' + \
            Mkt_df['Time'].str[-4:-2] + ':' + Mkt_df['Time'].str[-2:]
        Mkt_df['Ticker'] = Mkt_df['Ticker'].str.replace(
            'ي', 'ی').replace('ك', 'ک')
        Mkt_df['Name'] = Mkt_df['Name'].str.replace(
            'ي', 'ی').replace('ك', 'ک').str.replace('\u200c', ' ')
        Mkt_df['Close(%)'] = (
            (Mkt_df['Close'] - Mkt_df['Y-Final']) / Mkt_df['Y-Final'] * 100).round(2)
        Mkt_df['Final(%)'] = (
            (Mkt_df['Final'] - Mkt_df['Y-Final']) / Mkt_df['Y-Final'] * 100).round(2)
        Mkt_df['Market Cap'] = (
            Mkt_df['Share-No'] * Mkt_df['Final']).round(2)
        Mkt_df['Identifier'] = Mkt_df['Ticker-Code'].str[4:8]
        Mkt_df['WEB-ID'] = Mkt_df['WEB-ID'].str.strip()
        Mkt_df = Mkt_df.set_index('WEB-ID')

        OB_df = pd.DataFrame(parts[3].split(
            ';')).iloc[:, 0].str.split(",", expand=True)
        OB_df.columns = ['WEB-ID', 'OB-Depth', 'Sell-No', 'Buy-No',
                            'Buy-Price', 'Sell-Price', 'Buy-Vol', 'Sell-Vol']
        OB_df = OB_df[OB_df['OB-Depth'] ==
                        '1'].drop(columns=['OB-Depth']).set_index('WEB-ID')
        OB_df[['Sell-No', 'Sell-Vol', 'Sell-Price', 'Buy-Price', 'Buy-Vol', 'Buy-No']] = OB_df[
            ['Sell-No', 'Sell-Vol', 'Sell-Price',
                'Buy-Price', 'Buy-Vol', 'Buy-No']
        ].apply(pd.to_numeric)
        Mkt_df = Mkt_df.join(OB_df)
        Mkt_df['BQ-Value'] = np.where(Mkt_df['Buy-Price'] ==
                                        Mkt_df['Day_UL'], Mkt_df['Buy-Vol'] * Mkt_df['Buy-Price'], 0)
        Mkt_df['SQ-Value'] = np.where(Mkt_df['Sell-Price'] == Mkt_df['Day_LL'],
                                        Mkt_df['Sell-Vol'] * Mkt_df['Sell-Price'], 0)
        Mkt_df['BQPC'] = np.where((Mkt_df['BQ-Value'] != 0) & (
            Mkt_df['Buy-No'] != 0), (Mkt_df['BQ-Value'] / Mkt_df['Buy-No']).round(), 0)
        Mkt_df['SQPC'] = np.where((Mkt_df['SQ-Value'] != 0) & (
            Mkt_df['Sell-No'] != 0), (Mkt_df['SQ-Value'] / Mkt_df['Sell-No']).round(), 0)

        call = Mkt_df[Mkt_df['Name'].str.startswith('اختیارخ')].copy()
        call[['Option Name', 'Strike Price', 'Strike Date']
                ] = call['Name'].str.split('-', expand=True)
        call['Und Asset'] = call['Option Name'].str.replace(
            'اختیارخ', '').str.strip()
        call['Und Asset'] = call['Und Asset'].apply(
            lambda x: x + ' اهرم' if x == 'نارنج' else x)
        call['Und Asset'] = call['Und Asset'].apply(lambda x: x.replace(
            'فارماكیان', 'فارما کیان') if 'فارماكیان' in x else x)
        call['Days Remaining'] = call['Strike Date'].apply(
            lambda x: days_difference(JalaliDate.today().strftime('%Y/%m/%d'), x))
        numeric_cols = ['Strike Price', 'Sell-Price', 'Buy-Price']
        call[numeric_cols] = call[numeric_cols].apply(
            pd.to_numeric, errors='coerce')

        call['Und Asset'] = call['Und Asset'].apply(clean_string)
        call['Ticker'] = call['Ticker'].apply(clean_string)
        Mkt_df['Ticker'] = Mkt_df['Ticker'].apply(clean_string)

        # Create a dictionary to map 'Ticker' to 'Sell-Price'
        und_asset_sell = Mkt_df.set_index('Ticker')['Sell-Price'].to_dict()
        und_asset_buy = Mkt_df.set_index('Ticker')['Buy-Price'].to_dict()
        und_asset_close = Mkt_df.set_index('Ticker')['Close'].to_dict()

        # Map 'Und Asset' to 'Sell-Price' from Mkt_df
        call['Und Asset Sell-Price'] = call['Und Asset'].map(
            und_asset_sell)
        call['Und Asset Sell-Price'] = pd.to_numeric(
            call['Und Asset Sell-Price'], errors='coerce').fillna(0).astype(int)
        call['Und Asset Buy-Price'] = call['Und Asset'].map(und_asset_buy)
        call['Und Asset Buy-Price'] = pd.to_numeric(
            call['Und Asset Buy-Price'], errors='coerce').fillna(0).astype(int)
        call['Und Asset Close'] = call['Und Asset'].map(und_asset_close)
        call['Und Asset Close'] = pd.to_numeric(
            call['Und Asset Close'], errors='coerce').fillna(0).astype(int)

        call['Debit'] = call['Und Asset Close'] - call['Sell-Price']
        call['Return'] = (
            (call['Strike Price'] - call['Debit']) / call['Debit']).round(4)
        call['Monthly Return'] = (
            np.power((1 + call['Return']), (30 / call['Days Remaining'])) - 1).round(4)
        call['YTM Return'] = (
            np.power((1 + call['Return']), (365 / call['Days Remaining'])) - 1).round(4)
        call['OTM Cov Call'] = (
            call['Buy-Price'] / call['Und Asset Close']).round(4)
        call['Monthly Return'] = call['Monthly Return'].fillna(-1)
        call['I/O'] = np.select(
            [(call['Strike Price'] > call['Und Asset Close']),
                (call['Strike Price'] == call['Und Asset Close'])],
            ['OTM', 'ATM'], default='ITM'
        )

        # Historical Data Processing
        EXCEL_PATH = os.path.join(SCRIPT_DIR, 'opt hist.xlsx')
        hist = pd.read_excel(EXCEL_PATH)
        hist['Pos Days Remaining'] = hist.apply(
            lambda row: days_difference(row['Pos Date'], row['Strike Date']), axis=1)
        opt_hist = hist.merge(call, on='Ticker', how='inner')

        opt_hist['Pos Debit'] = opt_hist['Und Asset Price'] - \
            opt_hist['Premium']
        opt_hist['Capital'] = opt_hist['Num'] * \
            opt_hist['Pos Debit'] * opt_hist['Num Coef']
        opt_hist['Pos OTM Cov Call'] = (
            (opt_hist['Und Asset Price'] / opt_hist['Premium']) / 100).round(3)
        opt_hist['Pos Return'] = (
            (opt_hist['Strike Price'] - opt_hist['Pos Debit']) / opt_hist['Pos Debit']).round(3)
        opt_hist['Pos Monthly Return'] = (
            (1 + opt_hist['Pos Return']) ** (30 / opt_hist['Pos Days Remaining']) - 1).round(3)
        opt_hist['Pos YTM Return'] = (
            (1 + opt_hist['Pos Return']) ** (365 / opt_hist['Pos Days Remaining']) - 1).round(3)

        opt_hist['Today Return'] = (
            (opt_hist['Debit'] - opt_hist['Pos Debit']) / opt_hist['Pos Debit']).round(3)
        opt_hist['Today Monthly Return'] = (
            (1 + opt_hist['Today Return']) ** (30 / opt_hist['Days Remaining']) - 1).round(3)
        opt_hist['Today YTM Return'] = (
            (1 + opt_hist['Today Return']) ** (365 / opt_hist['Days Remaining']) - 1).round(3)
        opt_hist['Profit'] = (opt_hist['Capital'] *
                                opt_hist['Pos Return']).round(3)
        opt_hist['Signal'] = np.where(opt_hist['Today Monthly Return'].astype(
            float) > opt_hist['Monthly Return'].astype(float), 1, 0)

        opt_hist = opt_hist.drop(['Strike Date_x'], axis=1).rename(
            columns={'Strike Date_y': 'Strike Date'})

        opt_hist = opt_hist[['Ticker', 'Und Asset', 'Strike Price', 'Strike Date', 'Num', 'Premium', 'Und Asset Price', 'Days Remaining', 'Pos Date',
                                'Pos Debit', 'Pos OTM Cov Call', 'Buy-Price', 'Und Asset Close', 'Debit', 'Pos Return', 'Pos Monthly Return',
                                'Pos YTM Return', 'Today Return', 'Today Monthly Return', 'Today YTM Return', 'Return', 'Monthly Return',
                                'YTM Return', 'Pos Days Remaining', 'Capital', 'Profit', 'Signal']]
        opt_hist = opt_hist.rename(
            columns={'Buy-Price': 'Call Premium Now', 'Und Asset Last': 'Und Asset Buy-Price'})

        # Transpose DataFrame
        transposed_df = opt_hist.transpose()

        return transposed_df if 'transposed_df' in locals() else None

# Model for displaying DataFrame in a QTableView


class PandasModel(QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df

    def rowCount(self, parent=None):
        return self._df.shape[0]

    def columnCount(self, parent=None):
        return self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self._df.iloc[index.row(), index.column()])
            elif role == Qt.BackgroundRole:
                if index.row() == len(self._df) - 1 and self._df.iloc[index.row(), index.column()] == 1:
                    # Highlight last row if value is 1
                    return QBrush(QColor(144, 238, 144))  # Light Green
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self._df.columns[section] if orientation == Qt.Horizontal else str(self._df.index[section])
        return None

    def sort(self, column, order):
        if not self._df.empty and column < self._df.shape[1]:
            colname = self._df.columns[column]
            self.layoutAboutToBeChanged.emit()
            self._df.sort_values(colname, ascending=order ==
                                 Qt.AscendingOrder, inplace=True)
            self.layoutChanged.emit()

# Main application window


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Market Watch")
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)

        self.refresh_label = QLabel("Last Refreshed: Never", self)
        self.layout.addWidget(self.refresh_label)

        self.table_view = QTableView(self)
        self.layout.addWidget(self.table_view)

        self.model = PandasModel()
        self.table_view.setModel(self.model)
        self.table_view.setSortingEnabled(True)

        self.data_fetcher = DataFetcher()
        self.data_fetcher.data_fetched.connect(self.update_table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_data_fetch)
        self.timer.start(5000)  # Refresh every 5 seconds

        self.sort_column = None
        self.sort_order = Qt.AscendingOrder

        self.table_view.horizontalHeader().sortIndicatorChanged.connect(
            self.handle_sort_indicator_change)

    def handle_sort_indicator_change(self, column, order):
        self.sort_column = column
        self.sort_order = order

    def start_data_fetch(self):
        if not self.data_fetcher.isRunning():
            self.data_fetcher.start()

    def update_table(self, df):
        self.model = PandasModel(df)
        self.table_view.setModel(self.model)
        if not df.empty and self.sort_column is not None:
            self.table_view.sortByColumn(self.sort_column, self.sort_order)

        self.refresh_label.setText(
            f"Last Refreshed: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Save DataFrame to Excel file including index
        
        EXCEL_PATH_updated = os.path.join(SCRIPT_DIR, 'opt_hist_updated.xlsx')
        df.to_excel(EXCEL_PATH_updated, index=True)


# Run the application
app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec_())
