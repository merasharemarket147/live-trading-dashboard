from flask import Flask, render_template, jsonify
from datetime import datetime
import yfinance as yf
import pandas as pd
import pytz
import os
import requests

app = Flask(__name__)

# दिन भर का डेटा सेव रखने के लिए लिस्ट
daily_data_history = []
tz = pytz.timezone('Asia/Kolkata')

# Yahoo Finance को ब्लॉक करने से रोकने के लिए Fake Browser Session
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

# यह लिंक आपके तीनों स्कैनर्स एक साथ चलाएगा
@app.route('/trigger-scanner')
def run_scanner():
    file_name = "watchlist.csv"
    
    if os.path.exists(file_name):
        watchlist_df = pd.read_csv(file_name)
        stocks_list = watchlist_df['Symbol'].dropna().tolist()
    else:
        stocks_list = ["NIFTY 50.NS", "RELIANCE.NS", "HDFCBANK.NS"]

    min_price = 100           
    new_signals_count = 0

    for symbol in stocks_list:
        clean_name = symbol.replace(".NS", "")
        
        try:
            # ---------------------------------------------------------
            # 1. 15-Minute Data Fetch (For Wick Reversal & 15m Candle)
            # ---------------------------------------------------------
            df_15m = yf.download(symbol, period="5d", interval="15m", progress=False, session=session)
            
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
                    
                df_15m['Just_Date'] = df_15m[time_col_15].dt.date
                latest_date_15 = df_15m['Just_Date'].iloc[-1]
                today_15m = df_15m[df_15m['Just_Date'] == latest_date_15].copy()
                
                if not today_15m.empty and float(today_15m['Close'].iloc[-1]) >= min_price:
                    
                    # --- Scanner A: First 15-Min Candle 1.4% Breakout ---
                    first_c_15 = today_15m.iloc[0]
                    o_15, c_15 = float(first_c_15['Open']), float(first_c_15['Close'])
                    time_15 = first_c_15[time_col_15].strftime("%Y-%m-%d %H:%M")
                    pct_15 = ((c_15 - o_15) / o_15) * 100
                    
                    if abs(pct_15) >= 1.4:
                        sig_id = f"{clean_name}_{time_15}_15m_1.4pct"
                        if not any(item.get('id') == sig_id for item in daily_data_history):
                            arrow = "🚀" if pct_15 > 0 else "🩸"
                            col = "#00b894" if pct_15 > 0 else "#d63031"
                            daily_data_history.insert(0, {
                                "id": sig_id,
                                "time": time_15,
                                "symbol": clean_name,
                                "price": round(c_15, 2),
                                "signal": f"<span style='color:{col};font-weight:bold;'>{arrow} 1st Candle (15m): {round(pct_15, 2)}%</span>",
                                "source": "scanner_15m_candle"
                            })
                            new_signals_count += 1

                    # --- Scanner B: MTF 15-Min 1% Wick Reversal ---
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
                        sig_id = f"{clean_name}_{t_str}_BUY_WICK"
                        if not any(item.get('id') == sig_id for item in daily_data_history):
                            daily_data_history.insert(0, {
                                "id": sig_id,
                                "time": t_str,
                                "symbol": clean_name,
                                "price": round(row['Close'], 2),
                                "signal": f"<span style='color:green;font-weight:bold;'>BUY (Low Wick {round(row['Lower_Pct'], 2)}%)</span>",
                                "source": "scanner_15m_wick"
                            })
                            new_signals_count += 1
                            
                    for _, row in sell_wicks.iterrows():
                        t_str = row[time_col_15].strftime("%Y-%m-%d %H:%M")
                        sig_id = f"{clean_name}_{t_str}_SELL_WICK"
                        if not any(item.get('id') == sig_id for item in daily_data_history):
                            daily_data_history.insert(0, {
                                "id": sig_id,
                                "time": t_str,
                                "symbol": clean_name,
                                "price": round(row['Close'], 2),
                                "signal": f"<span style='color:red;font-weight:bold;'>SELL (Up Wick {round(row['Upper_Pct'], 2)}%)</span>",
                                "source": "scanner_15m_wick"
                            })
                            new_signals_count += 1

            # ---------------------------------------------------------
            # 2. 5-Minute Data Fetch (For First 05-Min Candle Scanner)[cite: 19]
            # ---------------------------------------------------------
            df_5m = yf.download(symbol, period="5d", interval="5m", progress=False, session=session)
            
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
                    
                df_5m['Just_Date'] = df_5m[time_col_5].dt.date
                latest_date_5 = df_5m['Just_Date'].iloc[-1]
                today_5m = df_5m[df_5m['Just_Date'] == latest_date_5]
                
                if not today_5m.empty:
                    first_c_5 = today_5m.iloc[0]
                    o_5, c_5 = float(first_c_5['Open']), float(first_c_5['Close'])
                    time_5 = first_c_5[time_col_5].strftime("%Y-%m-%d %H:%M")
                    
                    if o_5 >= min_price:
                        pct_5 = ((c_5 - o_5) / o_5) * 100
                        if abs(pct_5) >= 1.0:
                            sig_id = f"{clean_name}_{time_5}_5m_1pct"
                            if not any(item.get('id') == sig_id for item in daily_data_history):
                                arrow = "🚀" if pct_5 > 0 else "🩸"
                                col = "#00b894" if pct_5 > 0 else "#d63031"
                                daily_data_history.insert(0, {
                                    "id": sig_id,
                                    "time": time_5,
                                    "symbol": clean_name,
                                    "price": round(c_5, 2),
                                    "signal": f"<span style='color:{col};font-weight:bold;'>{arrow} 1st Candle (05m): {round(pct_5, 2)}%</span>",
                                    "source": "scanner_05m_candle"
                                })
                                new_signals_count += 1

        except Exception as e:
            continue

    # मेमोरी बचाने के लिए सिर्फ लेटेस्ट 300 सिग्नल रखना
    while len(daily_data_history) > 300:
        daily_data_history.pop()

    return jsonify({"status": "Scan Complete", "signals_added": new_signals_count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
