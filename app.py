from flask import Flask, render_template, jsonify
from datetime import datetime
import yfinance as yf
import pandas as pd
import pytz
import os
import requests
import warnings

warnings.filterwarnings('ignore')

app = Flask(__name__)

# Din bhar ka data save rakhne ke liye list
daily_data_history = []
tz = pytz.timezone('Asia/Kolkata')

# Yahoo Finance ko block hone se rokne ke liye Fake Browser Session
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify(daily_data_history)

# Yeh link aapke saare active scanners ek sath chalayega
@app.route('/trigger-scanner')
def run_scanner():
    global daily_data_history
    file_name = "watchlist.csv"
    
    # Aaj ki current date (IST ke hisaab se)
    today_date_str = datetime.now(tz).strftime("%Y-%m-%d")

    # Purana data saaf karna taaki sirf aaj ka fresh data rahe
    if daily_data_history:
        daily_data_history = [item for item in daily_data_history if item.get('time', '').startswith(today_date_str)]

    new_signals_count = 0

    if not os.path.exists(file_name):
        return jsonify({"status": "Error", "message": "watchlist.csv not found", "signals_added": 0})

    try:
        watchlist_df = pd.read_csv(file_name)
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e), "signals_added": 0})

    # -------------------------------------------------------------------------
    # SCANNER 1: First 05 min 1% Wick Reversal or Any Time
    # -------------------------------------------------------------------------
    if 'Symbol' in watchlist_df.columns:
        stocks_list_5m = watchlist_df['Symbol'].dropna().tolist()
        min_price_5m = 100
        
        for symbol in stocks_list_5m:
            clean_name = symbol.replace(".NS", "")
            try:
                df_5m = yf.download(symbol, period="1d", interval="5m", progress=False, session=session)
                if not df_5m.empty:
                    if isinstance(df_5m.columns, pd.MultiIndex):
                        df_5m.columns = df_5m.columns.get_level_values(0)
                    df_5m.dropna(inplace=True)
                    df_5m.reset_index(inplace=True)
                    
                    time_col_5 = 'Datetime' if 'Datetime' in df_5m.columns else 'index'
                    if df_5m[time_col_5].dt.tz is None:
                        df_5m[time_col_5] = df_5m[time_col_5].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                    else:
                        df_5m[time_col_5] = df_5m[time_col_5].dt.tz_convert('Asia/Kolkata')
                        
                    today_filter_date = datetime.now(tz).date()
                    df_5m['Just_Date'] = df_5m[time_col_5].dt.date
                    today_5m = df_5m[df_5m['Just_Date'] == today_filter_date].copy()
                    
                    if not today_5m.empty and float(today_5m['Close'].iloc[-1]) >= min_price_5m:
                        today_5m['Max_OC'] = today_5m[['Open', 'Close']].max(axis=1)
                        today_5m['Min_OC'] = today_5m[['Open', 'Close']].min(axis=1)
                        today_5m['Upper_Wick'] = today_5m['High'] - today_5m['Max_OC']
                        today_5m['Lower_Wick'] = today_5m['Min_OC'] - today_5m['Low']
                        today_5m['Upper_Pct'] = (today_5m['Upper_Wick'] / today_5m['Close']) * 100
                        today_5m['Lower_Pct'] = (today_5m['Lower_Wick'] / today_5m['Close']) * 100
                        
                        buy_wicks_5 = today_5m[today_5m['Lower_Pct'] >= 1.0]
                        sell_wicks_5 = today_5m[today_5m['Upper_Pct'] >= 1.0]
                        
                        for _, row in buy_wicks_5.iterrows():
                            t_str = row[time_col_5].strftime("%Y-%m-%d %H:%M")
                            sig_id = f"05m_{clean_name}_{t_str}_BUY"
                            if not any(item.get('id') == sig_id for item in daily_data_history):
                                daily_data_history.insert(0, {
                                    "id": sig_id,
                                    "time": t_str,
                                    "symbol": clean_name,
                                    "price": round(row['Close'], 2),
                                    "signal": f"<span style='color:green;font-weight:bold;'>BUY 05m (Low Wick {round(row['Lower_Pct'], 2)}%)</span>",
                                    "source": "scanner_05m_wick"
                                })
                                new_signals_count += 1
                                
                        for _, row in sell_wicks_5.iterrows():
                            t_str = row[time_col_5].strftime("%Y-%m-%d %H:%M")
                            sig_id = f"05m_{clean_name}_{t_str}_SELL"
                            if not any(item.get('id') == sig_id for item in daily_data_history):
                                daily_data_history.insert(0, {
                                    "id": sig_id,
                                    "time": t_str,
                                    "symbol": clean_name,
                                    "price": round(row['Close'], 2),
                                    "signal": f"<span style='color:red;font-weight:bold;'>SELL 05m (Up Wick {round(row['Upper_Pct'], 2)}%)</span>",
                                    "source": "scanner_05m_wick"
                                })
                                new_signals_count += 1
            except Exception as e:
                continue

    # -------------------------------------------------------------------------
    # SCANNER 2: MTF time (15 Minute) 1% Wick Reversal
    # -------------------------------------------------------------------------
    if 'Symbol' in watchlist_df.columns:
        stocks_list_15m = watchlist_df['Symbol'].dropna().tolist()
        min_price_15m = 100
        
        for symbol in stocks_list_15m:
            clean_name = symbol.replace(".NS", "")
            try:
                df_15m = yf.download(symbol, period="1d", interval="15m", progress=False, session=session)
                if not df_15m.empty:
                    if isinstance(df_15m.columns, pd.MultiIndex):
                        df_15m.columns = df_15m.columns.get_level_values(0)
                    df_15m.dropna(inplace=True)
                    df_15m.reset_index(inplace=True)
                    
                    time_col_15 = 'Datetime' if 'Datetime' in df_15m.columns else 'index'
                    if df_15m[time_col_15].dt.tz is None:
                        df_15m[time_col_15] = df_15m[time_col_15].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                    else:
                        df_15m[time_col_15] = df_15m[time_col_15].dt.tz_convert('Asia/Kolkata')
                        
                    today_filter_date = datetime.now(tz).date()
                    df_15m['Just_Date'] = df_15m[time_col_15].dt.date
                    today_15m = df_15m[df_15m['Just_Date'] == today_filter_date].copy()
                    
                    if not today_15m.empty and float(today_15m['Close'].iloc[-1]) >= min_price_15m:
                        today_15m['Max_OC'] = today_15m[['Open', 'Close']].max(axis=1)
                        today_15m['Min_OC'] = today_15m[['Open', 'Close']].min(axis=1)
                        today_15m['Upper_Wick'] = today_15m['High'] - today_15m['Max_OC']
                        today_15m['Lower_Wick'] = today_15m['Min_OC'] - today_15m['Low']
                        today_15m['Upper_Pct'] = (today_15m['Upper_Wick'] / today_15m['Close']) * 100
                        today_15m['Lower_Pct'] = (today_15m['Lower_Wick'] / today_15m['Close']) * 100
                        
                        buy_wicks = today_15m[today_15m['Lower_Pct'] >= 1.0]
                        sell_wicks = today_15m[today_15m['Upper_Pct'] >= 1.0]
                        
                        for _, row in buy_wicks.iterrows():
                            t_str = row[time_col_15].strftime("%Y-%m-%d %H:%M")
                            sig_id = f"15m_{clean_name}_{t_str}_BUY_WICK"
                            if not any(item.get('id') == sig_id for item in daily_data_history):
                                daily_data_history.insert(0, {
                                    "id": sig_id,
                                    "time": t_str,
                                    "symbol": clean_name,
                                    "price": round(row['Close'], 2),
                                    "signal": f"<span style='color:green;font-weight:bold;'>BUY 15m (Low Wick {round(row['Lower_Pct'], 2)}%)</span>",
                                    "source": "scanner_15m_wick"
                                })
                                new_signals_count += 1
                                
                        for _, row in sell_wicks.iterrows():
                            t_str = row[time_col_15].strftime("%Y-%m-%d %H:%M")
                            sig_id = f"15m_{clean_name}_{t_str}_SELL_WICK"
                            if not any(item.get('id') == sig_id for item in daily_data_history):
                                daily_data_history.insert(0, {
                                    "id": sig_id,
                                    "time": t_str,
                                    "symbol": clean_name,
                                    "price": round(row['Close'], 2),
                                    "signal": f"<span style='color:red;font-weight:bold;'>SELL 15m (Up Wick {round(row['Upper_Pct'], 2)}%)</span>",
                                    "source": "scanner_15m_wick"
                                })
                                new_signals_count += 1
            except Exception as e:
                continue

    # -------------------------------------------------------------------------
    # SCANNER 3: Hourly (1h) 1.5% Wick Reversal
    # -------------------------------------------------------------------------
    if 'Symbol' in watchlist_df.columns:
        hourly_stocks = watchlist_df['Symbol'].dropna().tolist()
        wick_threshold = 1.5
        min_price_1h = 100
        min_mcap_cr = 30000

        for symbol in hourly_stocks:
            clean_name = symbol.replace(".NS", "")
            try:
                df_1h = yf.download(symbol, period="5d", interval="1h", progress=False, session=session)
                if df_1h.empty:
                    continue

                if isinstance(df_1h.columns, pd.MultiIndex):
                    df_1h.columns = df_1h.columns.get_level_values(0)

                df_1h.dropna(inplace=True)
                df_1h.reset_index(inplace=True)

                time_col_1h = 'Datetime' if 'Datetime' in df_1h.columns else 'index'
                if df_1h[time_col_1h].dt.tz is None:
                    df_1h[time_col_1h] = df_1h[time_col_1h].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df_1h[time_col_1h] = df_1h[time_col_1h].dt.tz_convert('Asia/Kolkata')

                today_filter_date = datetime.now(tz).date()
                df_1h['Just_Date'] = df_1h[time_col_1h].dt.date
                today_1h = df_1h[df_1h['Just_Date'] == today_filter_date].copy()

                if today_1h.empty:
                    continue

                current_price_1h = float(today_1h['Close'].iloc[-1])
                if current_price_1h < min_price_1h:
                    continue

                today_1h['Max_Open_Close'] = today_1h[['Open', 'Close']].max(axis=1)
                today_1h['Min_Open_Close'] = today_1h[['Open', '
