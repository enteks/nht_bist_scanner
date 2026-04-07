"""
NhT BIST 11-Scanner - Android (Kivy)
tkinter → Kivy dönüşümü
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import get_color_from_hex

import threading
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════
# PURE PANDAS İNDİKATÖRLER
# ═══════════════════════════════════════════

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def sma(series, period):
    return series.rolling(window=period).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def rsi_wilder(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).fillna(0)
    loss = -delta.where(delta < 0, 0).fillna(0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

# ═══════════════════════════════════════════
# VERİ ÇEKME
# ═══════════════════════════════════════════

def fetch_batch_data(symbols, period='1d', lookback_days=60):
    tickers = [f"{s}.IS" if not s.endswith('.IS') else s for s in symbols]
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    try:
        df_all = yf.download(tickers, start=start, end=end, interval=period, progress=False, group_by='ticker')
        results = {}
        for symbol, ticker in zip(symbols, tickers):
            try:
                if isinstance(df_all.columns, pd.MultiIndex):
                    df = df_all[ticker].dropna(how='all')
                else:
                    df = df_all.copy()
                if len(df) > 10:
                    df = df.reset_index()
                    if 'Date' in df.columns:
                        df = df.rename(columns={'Date': 'Datetime'})
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [col[0] if col[0] else col[1] for col in df.columns]
                    results[symbol] = df
            except:
                continue
        return results
    except:
        return fetch_parallel_fallback(symbols, period, lookback_days)

def fetch_parallel_fallback(symbols, period='1d', lookback_days=60, max_workers=10):
    results = {}
    def fetch_one(symbol):
        try:
            ticker = f"{symbol}.IS" if not symbol.endswith('.IS') else symbol
            end = datetime.now()
            start = end - timedelta(days=lookback_days)
            df = yf.download(ticker, start=start, end=end, interval=period, progress=False)
            if len(df) > 10:
                df = df.reset_index()
                if 'Date' in df.columns:
                    df = df.rename(columns={'Date': 'Datetime'})
                return symbol, df
        except:
            pass
        return symbol, None
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, s): s for s in symbols}
        for future in as_completed(futures):
            symbol, df = future.result()
            if df is not None:
                results[symbol] = df
    return results

# ═══════════════════════════════════════════
# SCANNER SINIFLARI (orijinal mantık korundu)
# ═══════════════════════════════════════════

class WaveTrendScanner:
    def __init__(self):
        self.chlen = 10
        self.avg = 21
        self.ob_level2 = 53
        self.os_level2 = -53
        self.trend_filter = True
        self.trend_ma_period = 20

    def _calculate_wavetrend(self, df):
        df = df.copy()
        df['ap'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['esa'] = ema(df['ap'], self.chlen)
        df['d'] = ema(np.abs(df['ap'] - df['esa']), self.chlen)
        df['ci'] = (df['ap'] - df['esa']) / (0.015 * df['d'].replace(0, np.nan))
        df['tci'] = ema(df['ci'], self.avg)
        df['wt1'] = df['tci']
        df['wt2'] = sma(df['tci'], 4)
        return df

    def _detect_signal(self, df):
        if len(df) < 2:
            return None, None, None
        try:
            c1, c2 = df['wt1'].iloc[-1], df['wt2'].iloc[-1]
            p1, p2 = df['wt1'].iloc[-2], df['wt2'].iloc[-2]
            if pd.isna(c1) or pd.isna(c2):
                return None, None, None
            cross_up = (p1 <= p2) and (c1 > c2)
            cross_down = (p1 >= p2) and (c1 < c2)
            if cross_up and c1 < self.os_level2:
                return 'WT AL', 'bull', f'Oversold WT:{c1:.1f}'
            elif cross_down and c1 > self.ob_level2:
                return 'WT SAT', 'bear', f'Overbought WT:{c1:.1f}'
        except:
            pass
        return None, None, None

    def scan_symbol_fast(self, df, symbol):
        try:
            if len(df) < max(self.chlen, self.avg) + 5:
                return None
            df = self._calculate_wavetrend(df)
            signal, sig_type, note = self._detect_signal(df)
            if not signal:
                return None
            if self.trend_filter:
                ma = sma(df['Close'], self.trend_ma_period).iloc[-1]
                if df['Close'].iloc[-1] <= ma:
                    return None
            cp, pc = df['Close'].iloc[-1], df['Close'].iloc[-2]
            return {'symbol': symbol, 'signal': signal, 'price': round(cp, 2),
                    'move_pct': round(((cp - pc) / pc) * 100, 2),
                    'note': note, 'sig_type': sig_type}
        except:
            return None

    def scan_batch_fast(self, data_dict, callback=None):
        results = []
        for i, (symbol, df) in enumerate(data_dict.items()):
            r = self.scan_symbol_fast(df, symbol)
            if r:
                results.append(r)
            if callback and i % 5 == 0:
                callback(i + 1, len(data_dict))
        return results


class RoketTaramaScanner:
    def __init__(self):
        self.ema_length = 10
        self.rsi_length = 14
        self.cci_length = 20
        self.vol_length = 30
        self.trend_filter = True
        self.trend_ma_period = 20

    def _cci_pine_compatible(self, df):
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        tp_sma = sma(tp, self.cci_length)
        mean_dev = sma(np.abs(tp - tp_sma), self.cci_length)
        return (tp - tp_sma) / (0.015 * mean_dev)

    def scan_symbol_fast(self, df, symbol):
        try:
            min_bars = max(self.ema_length, self.rsi_length, self.cci_length, self.vol_length) + 10
            if len(df) < min_bars:
                return None
            ema_val = ema(df['Close'], self.ema_length).iloc[-1]
            rsi_val = rsi_wilder(df['Close'], self.rsi_length).iloc[-1]
            cci_val = self._cci_pine_compatible(df).iloc[-1]
            vol_ma = sma(df['Volume'], self.vol_length).iloc[-1]
            curr_vol = df['Volume'].iloc[-1]
            curr_close = df['Close'].iloc[-1]
            if curr_vol > vol_ma and cci_val >= 0 and curr_close >= ema_val and rsi_val >= 50:
                if self.trend_filter:
                    ma = sma(df['Close'], self.trend_ma_period).iloc[-1]
                    if curr_close <= ma:
                        return None
                vol_ratio = curr_vol / vol_ma if vol_ma > 0 else 0
                cp, pc = df['Close'].iloc[-1], df['Close'].iloc[-2]
                return {'symbol': symbol, 'signal': 'Roket AL', 'price': round(cp, 2),
                        'move_pct': round(((cp - pc) / pc) * 100, 2),
                        'note': f'Vol:{vol_ratio:.1f}x CCI:{cci_val:.1f} RSI:{rsi_val:.1f}',
                        'sig_type': 'bull'}
        except:
            pass
        return None

    def scan_batch_fast(self, data_dict, callback=None):
        results = []
        for i, (symbol, df) in enumerate(data_dict.items()):
            r = self.scan_symbol_fast(df, symbol)
            if r:
                results.append(r)
            if callback and i % 5 == 0:
                callback(i + 1, len(data_dict))
        return results


class BOSBreakoutScanner:
    def __init__(self):
        self.pivot_length = 5
        self.strong_threshold = 3.0
        self.trend_filter = True
        self.trend_ma_period = 20

    def _find_pivot_high(self, highs, idx, plen):
        if idx < plen or idx >= len(highs) - plen:
            return False
        center = highs[idx]
        left = highs[idx - plen:idx]
        right = highs[idx + 1:idx + plen + 1]
        return center > left.max() and center >= right.max()

    def _find_pivot_low(self, lows, idx, plen):
        if idx < plen or idx >= len(lows) - plen:
            return False
        center = lows[idx]
        left = lows[idx - plen:idx]
        right = lows[idx + 1:idx + plen + 1]
        return center < left.min() and center <= right.min()

    def scan_symbol_fast(self, df, symbol):
        try:
            if len(df) < self.pivot_length * 4 + 10:
                return None
            highs, lows, closes = df['High'].values, df['Low'].values, df['Close'].values
            curr_close, prev_close = closes[-1], closes[-2]
            pivot_highs, pivot_lows = [], []
            for i in range(self.pivot_length, len(df) - self.pivot_length):
                if self._find_pivot_high(highs, i, self.pivot_length):
                    pivot_highs.append((i, highs[i]))
                if self._find_pivot_low(lows, i, self.pivot_length):
                    pivot_lows.append((i, lows[i]))
            if len(pivot_highs) < 2 or len(pivot_lows) < 2:
                return None
            last_high_2, last_high_1 = pivot_highs[-2], pivot_highs[-1]
            last_low_2, last_low_1 = pivot_lows[-2], pivot_lows[-1]
            is_uptrend = last_high_1[1] > last_high_2[1] and last_low_1[1] > last_low_2[1]
            is_downtrend = last_high_1[1] < last_high_2[1] and last_low_1[1] < last_low_2[1]
            signal, note = None, None
            if is_uptrend and prev_close <= last_high_1[1] < curr_close:
                pct = ((curr_close - last_high_1[1]) / last_high_1[1]) * 100
                if abs(pct) >= self.strong_threshold:
                    signal = 'Strong BOS AL'
                else:
                    signal = 'BOS AL'
                note = f'HH:{last_high_1[1]:.2f} +%{pct:.2f}'
            elif is_downtrend and prev_close >= last_low_1[1] > curr_close:
                pct = ((curr_close - last_low_1[1]) / last_low_1[1]) * 100
                if abs(pct) >= self.strong_threshold:
                    signal = 'Strong BOS SAT'
                else:
                    signal = 'BOS SAT'
                note = f'LL:{last_low_1[1]:.2f} {pct:.2f}%'
            elif is_downtrend and prev_close <= last_high_1[1] < curr_close:
                pct = ((curr_close - last_high_1[1]) / last_high_1[1]) * 100
                signal = 'CHOCH AL'
                note = f'Trend donusu HH:{last_high_1[1]:.2f}'
            if not signal:
                return None
            if self.trend_filter:
                ma = sma(df['Close'], self.trend_ma_period).iloc[-1]
                if curr_close <= ma:
                    return None
            cp, pc = df['Close'].iloc[-1], df['Close'].iloc[-2]
            return {'symbol': symbol, 'signal': signal, 'price': round(cp, 2),
                    'move_pct': round(((cp - pc) / pc) * 100, 2),
                    'note': note or '', 'sig_type': 'bull' if 'AL' in signal else 'bear'}
        except:
            return None

    def scan_batch_fast(self, data_dict, callback=None):
        results = []
        for i, (symbol, df) in enumerate(data_dict.items()):
            r = self.scan_symbol_fast(df, symbol)
            if r:
                results.append(r)
            if callback and i % 5 == 0:
                callback(i + 1, len(data_dict))
        return results


# ═══════════════════════════════════════════
# BIST HİSSE LİSTESİ
# ═══════════════════════════════════════════

SYMBOLS = [
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "CCOLA", "DOHOL", "EKGYO", "ENKAI",
    "EREGL", "FROTO", "GARAN", "GUBRF", "HALKB", "ISCTR", "KCHOL", "KOZAL",
    "KRDMD", "MGROS", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SKBNK",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TTKOM", "TUPRS", "VAKBN",
    "VESTL", "YKBNK", "AKSEN", "AKSA", "ALARK", "ALKIM", "BRISA", "BTCIM",
    "CIMSA", "CLEBI", "DOAS", "ENJSA", "GWIND", "INDES", "KAREL", "KERVN",
    "LOGO", "MAVI", "NETAS", "OTKAR", "SELEC", "SMART", "SOKM", "TATGD",
    "ULKER", "VESBE", "ZOREN", "AEFES", "AGHOL", "AKGRT", "ALBRK", "ANHYT",
    "ANSGR", "ARSAN", "ASTOR", "ASUZU", "AVOD", "AYDEM", "AYGAZ", "BAGFS",
    "BANVT", "BRKO", "BRSAN", "BRYAT", "BURCE", "CEMTS", "CRDFA", "DEVA",
    "DITAS", "DOAS", "ECILC", "EGEEN", "EKOS", "EMKEL", "ERBOS", "ERSU",
    "GEREL", "GESAN", "HEKTS", "HOROZ", "HUBVC", "IHEVA", "IHLGM", "INGRM",
    "INVEO", "INVES", "ISBIR", "ISCTR", "ISDMR", "ISFIN", "ISGLK", "JANTS",
    "KAREL", "KARSN", "KARTN", "KATMR", "KBORU", "KENT", "KLKIM", "KLMSN",
    "KONKA", "KONTR", "KORDS", "KOTON", "KRDMA", "KRDMB", "KRTEK", "LIDER",
    "LINK", "LKMNH", "MAALT", "MAGEN", "MAKIM", "MANAS", "MARBL", "MARKA",
    "MARTI", "MEDTR", "MEPET", "MERCN", "MERIT", "MERKO", "METRO", "MEYSU",
    "MNDRS", "NATEN", "NETCD", "NIBAS", "NTGAZ", "NUHCM", "OBASE", "ODAS",
    "ORGE", "OSTIM", "OTTO", "OYAKC", "PAMEL", "PARSN", "PATEK", "PENTA",
    "PETUN", "PINSU", "PKART", "POLHO", "PRDGS", "PRKAB", "PRZMA", "QNBFK",
    "QNBTR", "RAYSG", "ROYAL", "RUBNS", "SAFKR", "SAMAT", "SANEL", "SANFM",
    "SARKY", "SAYAS", "SEGMN", "SEKUR", "SELVA", "SERNT", "SILVR", "SKTAS",
    "SNICAS", "SNPAM", "SODSN", "SOKE", "SONME", "SUMAS", "SUNTK", "SUWEN",
    "TATEN", "TBORG", "TDGYO", "TEKTU", "TEZOL", "TGSAS", "TKFEN", "TKNSA",
    "TLMAN", "TMSN", "TOASO", "TRALT", "TRCAS", "TRGYO", "TRHOL", "TRILC",
    "TRMET", "TSKB", "TTRAK", "TUKAS", "TUREX", "ULKER", "ULAS", "ULUFA",
    "ULUSE", "UMPAS", "UNLU", "USAK", "VAKKO", "VBTYZ", "VERTU", "VESBE",
    "VKGYO", "VKING", "YAPRK", "YATAS", "YAYLA", "YKBNK", "YUNSA", "ZEDUR",
]


# ═══════════════════════════════════════════
# KİVY UI
# ═══════════════════════════════════════════

class ResultRow(BoxLayout):
    def __init__(self, result, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(40)
        self.padding = [dp(4), dp(2)]
        self.spacing = dp(4)

        sig_type = result.get('sig_type', 'bull')
        if 'Roket' in result['signal']:
            color = get_color_from_hex('#00ff00')
        elif 'Strong' in result['signal']:
            color = get_color_from_hex('#ff00ff')
        elif 'CHOCH' in result['signal']:
            color = get_color_from_hex('#f39c12')
        elif sig_type == 'bull':
            color = get_color_from_hex('#2ecc71')
        else:
            color = get_color_from_hex('#e74c3c')

        def lbl(text, w, bold=False):
            l = Label(
                text=str(text),
                size_hint_x=None,
                width=dp(w),
                color=color,
                font_size=dp(11),
                bold=bold,
                halign='center',
                valign='middle'
            )
            l.bind(size=l.setter('text_size'))
            return l

        self.add_widget(lbl(result['symbol'], 65, bold=True))
        self.add_widget(lbl(result['signal'], 110))
        self.add_widget(lbl(f"{result['price']:.2f}", 65))
        self.add_widget(lbl(f"{result['move_pct']:+.2f}%", 60))
        self.add_widget(lbl(result.get('note', '')[:40], 200))


class NHTBistApp(App):
    def build(self):
        Window.clearcolor = get_color_from_hex('#000000')

        self.scanners = {
            'Roket Tarama': RoketTaramaScanner(),
            'WaveTrend': WaveTrendScanner(),
            'BOS+CHOCH': BOSBreakoutScanner(),
        }
        self.active_scanner = 'Roket Tarama'

        root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))

        # Başlık
        title = Label(
            text='[b][color=9b59b6]NhT BIST 11-Scanner[/color][/b]',
            markup=True,
            font_size=dp(20),
            size_hint_y=None,
            height=dp(40)
        )
        root.add_widget(title)

        subtitle = Label(
            text='[color=888888]Roket + WaveTrend + BOS/CHOCH[/color]',
            markup=True,
            font_size=dp(11),
            size_hint_y=None,
            height=dp(20)
        )
        root.add_widget(subtitle)

        # Scanner seçici + buton
        top_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8)
        )

        self.scanner_spinner = Spinner(
            text=self.active_scanner,
            values=list(self.scanners.keys()),
            size_hint_x=0.5,
            background_color=get_color_from_hex('#1a1a2e'),
            color=get_color_from_hex('#9b59b6'),
            font_size=dp(13)
        )
        self.scanner_spinner.bind(text=self.on_scanner_change)
        top_bar.add_widget(self.scanner_spinner)

        scan_btn = Button(
            text='[b]TARA[/b]',
            markup=True,
            size_hint_x=0.5,
            background_color=get_color_from_hex('#6c3483'),
            font_size=dp(14)
        )
        scan_btn.bind(on_press=self.start_scan)
        top_bar.add_widget(scan_btn)
        root.add_widget(top_bar)

        # Progress bar
        self.progress = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(10)
        )
        root.add_widget(self.progress)

        # Durum etiketi
        self.status_label = Label(
            text='[color=9b59b6]Hazir | TARA butonuna basin[/color]',
            markup=True,
            font_size=dp(11),
            size_hint_y=None,
            height=dp(24),
            halign='left'
        )
        self.status_label.bind(size=self.status_label.setter('text_size'))
        root.add_widget(self.status_label)

        # Tablo başlıkları
        header = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(32),
            padding=[dp(4), 0],
            spacing=dp(4)
        )
        for text, w in [('SEMBOL', 65), ('SiNYAL', 110), ('FiYAT', 65), ('MOVE%', 60), ('DETAY', 200)]:
            lbl = Label(
                text=f'[b][color=9b59b6]{text}[/color][/b]',
                markup=True,
                size_hint_x=None,
                width=dp(w),
                font_size=dp(11),
                halign='center',
                valign='middle'
            )
            lbl.bind(size=lbl.setter('text_size'))
            header.add_widget(lbl)
        root.add_widget(header)

        # Sonuç listesi
        self.scroll = ScrollView()
        self.results_layout = GridLayout(
            cols=1,
            spacing=dp(2),
            size_hint_y=None
        )
        self.results_layout.bind(minimum_height=self.results_layout.setter('height'))
        self.scroll.add_widget(self.results_layout)
        root.add_widget(self.scroll)

        # Log alanı
        self.log_label = Label(
            text='',
            markup=True,
            font_size=dp(10),
            size_hint_y=None,
            height=dp(40),
            halign='left',
            color=get_color_from_hex('#9b59b6')
        )
        self.log_label.bind(size=self.log_label.setter('text_size'))
        root.add_widget(self.log_label)

        return root

    def on_scanner_change(self, spinner, text):
        self.active_scanner = text

    def update_status(self, text, color='#9b59b6'):
        Clock.schedule_once(lambda dt: setattr(
            self.status_label, 'text',
            f'[color={color}]{text}[/color]'
        ))

    def update_progress(self, val):
        Clock.schedule_once(lambda dt: setattr(self.progress, 'value', val))

    def update_log(self, text):
        Clock.schedule_once(lambda dt: setattr(self.log_label, 'text', text))

    def start_scan(self, instance):
        self.results_layout.clear_widgets()
        self.progress.value = 0
        self.update_status('Veri cekiliyor...', 'f39c12')

        def run():
            start_time = datetime.now()
            data_dict = fetch_batch_data(SYMBOLS, lookback_days=60)
            if not data_dict:
                self.update_status('Veri alinamadi!', 'e74c3c')
                return

            self.update_status(f'{len(data_dict)} hisse yuklendi | Taraniyor...', 'f39c12')
            scanner = self.scanners[self.active_scanner]

            def progress_cb(done, total):
                pct = int((done / total) * 100)
                self.update_progress(pct)

            results = scanner.scan_batch_fast(data_dict, callback=progress_cb)
            elapsed = (datetime.now() - start_time).total_seconds()
            Clock.schedule_once(lambda dt: self.show_results(results, elapsed))

        threading.Thread(target=run, daemon=True).start()

    def show_results(self, results, elapsed):
        self.results_layout.clear_widgets()
        self.progress.value = 100

        if not results:
            self.update_status(f'Sinyal bulunamadi ({elapsed:.1f}sn)', '95a5a6')
            return

        # Sırala
        def sort_key(r):
            s = r['signal']
            if 'Roket' in s: return 0
            if 'Strong' in s: return 1
            if 'CHOCH' in s: return 2
            if 'BOS' in s: return 3
            return 4

        results.sort(key=sort_key)

        for r in results:
            self.results_layout.add_widget(ResultRow(r))

        roket = sum(1 for r in results if 'Roket' in r['signal'])
        self.update_status(f'{len(results)} sinyal | Roket:{roket} | {elapsed:.1f}sn', '2ecc71')
        self.update_log(f'[color=9b59b6]Son tarama: {datetime.now().strftime("%H:%M:%S")} | {len(results)} sinyal bulundu[/color]')


if __name__ == '__main__':
    NHTBistApp().run()
