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
    watchlist_file = "watchlist.csv"
    zone_file = "zones.csv"
    
    # Aaj ki current date (IST ke hisaab se)
    today_date_str = datetime.now(tz).strftime("%Y-%m-%d")

    # Purana data saaf karna taaki sirf aaj ka fresh data rahe
    if daily_data_history:
        daily_data_history = [item for item in daily_data_history if item.get('time', '').startswith(today_date_str)]

    new_signals_count = 0

    # watchlist.csv check karna pehle 3 scanners ke liye
    stocks_list = []
    if os.path.exists(watchlist_file):
        try:
            watchlist_df = pd.read_csv(watchlist_file)
            if 'Symbol' in watchlist_df.columns:
                stocks_list = watchlist_df['Symbol'].dropna().tolist()
        except Exception as e:
            pass

    # -------------------------------------------------------------------------
    # SCANNER 1: First 05 min 1% Wick Reversal or Any Time
    # -------------------------------------------------------------------------
    if stocks_list:
        for symbol in stocks_list:
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
                    
                    if not today_5m.empty and float(today_5m['Close'].iloc[-1]) >= 100:
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
                                    "id": sig_id, "time": t_str, "symbol": clean_name,
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
                                    "id": sig_id, "time": t_str, "symbol": clean_name,
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
    if stocks_list:
        for symbol in stocks_list:
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
                    
                    if not today_15m.empty and float(today_15m['Close'].iloc[-1]) >= 100:
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
                                    "id": sig_id, "time": t_str, "symbol": clean_name,
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
                                    "id": sig_id, "time": t_str, "symbol": clean_name,
                                    "price": round(row['Close'], 2),
                                    "signal": f"<span style='color:red;font-weight:bold;'>SELL 15m (Up Wick {round(row['Upper_Pct'], 2)}%)</span>",
                                    "source": "scanner_15m_wick"
                                })
                                new_signals_count += 1
            except Exception as e:
                continue

    # -------------------------------------------------------------------------
    # SCANNER 3: Hourly (1h) 1.5% Wick Reversal (Market Cap check removed)
    # -------------------------------------------------------------------------
    if stocks_list:
        wick_threshold = 1.5
        for symbol in stocks_list:
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

                if today_1h.empty or float(today_1h['Close'].iloc[-1]) < 100:
                    continue

                today_1h['Max_OC'] = today_1h[['Open', 'Close']].max(axis=1)
                today_1h['Min_OC'] = today_1h[['Open', 'Close']].min(axis=1)
                today_1h['Upper_Wick'] = today_1h['High'] - today_1h['Max_OC']
                today_1h['Lower_Wick'] = today_1h['Min_OC'] - today_1h['Low']
                today_1h['Upper_Wick_Pct'] = (today_1h['Upper_Wick'] / today_1h['Close']) * 100
                today_1h['Lower_Wick_Pct'] = (today_1h['Lower_Wick'] / today_1h['Close']) * 100

                buy_signals_1h = today_1h[today_1h['Lower_Wick_Pct'] >= wick_threshold]
                sell_signals_1h = today_1h[today_1h['Upper_Wick_Pct'] >= wick_threshold]

                if not buy_signals_1h.empty or not sell_signals_1h.empty:
                    for _, row in buy_signals_1h.iterrows():
                        candle_time = row[time_col_1h].strftime("%Y-%m-%d %H:%M")
                        wick_pct = round(row['Lower_Wick_Pct'], 2)
                        sig_id = f"1h_{clean_name}_{candle_time}_BUY"

                        if not any(item.get('id') == sig_id for item in daily_data_history):
                            daily_data_history.insert(0, {
                                "id": sig_id, "time": candle_time, "symbol": clean_name,
                                "price": round(row['Close'], 2),
                                "signal": f"<span style='color:green;font-weight:bold;'>BUY (1h Lower Wick {wick_pct}%)</span>",
                                "source": "hourly_wick_scanner"
                            })
                            new_signals_count += 1

                    for _, row in sell_signals_1h.iterrows():
                        candle_time = row[time_col_1h].strftime("%Y-%m-%d %H:%M")
                        wick_pct = round(row['Upper_Wick_Pct'], 2)
                        sig_id = f"1h_{clean_name}_{candle_time}_SELL"

                        if not any(item.get('id') == sig_id for item in daily_data_history):
                            daily_data_history.insert(0, {
                                "id": sig_id, "time": candle_time, "symbol": clean_name,
                                "price": round(row['Close'], 2),
                                "signal": f"<span style='color:red;font-weight:bold;'>SELL (1h Upper Wick {wick_pct}%)</span>",
                                "source": "hourly_wick_scanner"
                            })
                            new_signals_count += 1
            except Exception as e:
                continue

    # -------------------------------------------------------------------------
    # SCANNER 4: Normal Zone Alert Scanner (0.50%) - Reads from zones.csv
    # -------------------------------------------------------------------------
    if os.path.exists(zone_file):
        try:
            df_zones = pd.read_csv(zone_file)
            if 'Stock Symbol' in df_zones.columns:
                alert_buffer_pct = 0.50
                for index, row in df_zones.iterrows():
                    try:
                        raw_symbol = str(row['Stock Symbol']).strip().upper()
                        direction = str(row['Direction']).strip().title()
                        entry_price = float(row['Zone Entry Price'])
                        
                        yf_symbol = raw_symbol + ".NS"
                        hist = yf.Ticker(yf_symbol).history(period="1d", interval="1m", session=session)
                        
                        if hist.empty:
                            continue
                            
                        current_price = float(hist['Close'].iloc[-1])
                        price_diff = abs(current_price - entry_price)
                        diff_pct = (price_diff / entry_price) * 100
                        
                        if diff_pct <= alert_buffer_pct:
                            position = "Above Zone" if current_price > entry_price else "Below Zone"
                            sig_color = "green" if direction == "Buy" else "red"
                            
                            sig_text = f"<span style='color:{sig_color};font-weight:bold;'>{direction.upper()} ALERT ({position}) | Target: ₹{entry_price} | Gap: {diff_pct:.2f}%</span>"
                            sig_id = f"zone_{raw_symbol}_{entry_price}_{direction}"
                            current_time_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
                            
                            existing_idx = next((i for i, item in enumerate(daily_data_history) if item.get('id') == sig_id), None)
                            zone_item = {
                                "id": sig_id, "time": current_time_str, "symbol": raw_symbol,
                                "price": round(current_price, 2), "signal": sig_text,
                                "source": "normal_zone_scanner"
                            }
                            
                            if existing_idx is not None:
                                daily_data_history[existing_idx] = zone_item
                            else:
                                daily_data_history.insert(0, zone_item)
                                new_signals_count += 1
                    except Exception as e:
                        continue
        except Exception as e:
            pass

    while len(daily_data_history) > 400:
        daily_data_history.pop()

    return jsonify({"status": "Scan Complete", "signals_added": new_signals_count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
