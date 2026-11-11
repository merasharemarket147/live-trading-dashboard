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

# यह लिंक अब आपके दोनों (Wick Reversal + First Candle) स्कैनर एक साथ चलाएगा
@app.route('/trigger-scanner')
def run_scanner():
    file_name = "watchlist.csv"
    
    if os.path.exists(file_name):
        watchlist_df = pd.read_csv(file_name)
        stocks_list = watchlist_df['Symbol'].dropna().tolist()
    else:
        stocks_list = ["NIFTY 50.NS", "RELIANCE.NS", "HDFCBANK.NS"]

    # दोनों स्कैनर्स की सेटिंग्स
    wick_threshold = 1.0      
    first_candle_threshold = 1.4
    min_price = 100           
    new_signals_count = 0

    for symbol in stocks_list:
        clean_name = symbol.replace(".NS", "")
        
        try:
            # 15 Minute डेटा फेच करना (सिर्फ एक बार)
            df = yf.download(symbol, period="5d", interval="15m", progress=False, session=session)
            
            if df.empty:
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df.dropna(inplace=True)
            df.reset_index(inplace=True)
            
            time_col = 'Datetime' if 'Datetime' in df.columns else 'index'
            if df[time_col].dt.tz is None:
                df[time_col] = df[time_col].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            else:
                df[time_col] = df[time_col].dt.tz_convert('Asia/Kolkata')
                
            df['Just_Date'] = df[time_col].dt.date
            latest_date = df['Just_Date'].iloc[-1]
            
            today_df = df[df['Just_Date'] == latest_date].copy()
            if today_df.empty:
                continue
                
            current_price = float(today_df['Close'].iloc[-1])
            if current_price < min_price:
                continue
            
            # =======================================================
            # SCANNER 1: First 15-Min Candle 1.4% Breakout/Breakdown
            # =======================================================
            first_candle = today_df.iloc[0]
            c_open = float(first_candle['Open'])
            c_close = float(first_candle['Close'])
            first_candle_time = first_candle[time_col].strftime("%Y-%m-%d %H:%M")
            
            pct_change = ((c_close - c_open) / c_open) * 100
            
            if abs(pct_change) >= first_candle_threshold:
                fc_signal_id = f"{clean_name}_{first_candle_time}_1stCandle"
                
                if not any(item.get('id') == fc_signal_id for item in daily_data_history):
                    if pct_change > 0:
                        signal_text = f"<span style='color:#00b894;font-weight:bold;'>🚀 1st Candle Rally ({round(pct_change, 2)}%)</span>"
                    else:
                        signal_text = f"<span style='color:#d63031;font-weight:bold;'>🩸 1st Candle Fall ({round(pct_change, 2)}%)</span>"
                    
                    new_result = {
                        "id": fc_signal_id,
                        "time": first_candle_time,
                        "symbol": clean_name,
                        "price": round(c_close, 2),
                        "signal": signal_text
                    }
                    daily_data_history.insert(0, new_result)
                    new_signals_count += 1

            # =======================================================
            # SCANNER 2: MTF 15-Min 1% Wick Reversal
            # =======================================================
            today_df['Max_Open_Close'] = today_df[['Open', 'Close']].max(axis=1)
            today_df['Min_Open_Close'] = today_df[['Open', 'Close']].min(axis=1)
            today_df['Upper_Wick'] = today_df['High'] - today_df['Max_Open_Close']
            today_df['Lower_Wick'] = today_df['Min_Open_Close'] - today_df['Low']
            today_df['Upper_Wick_Pct'] = (today_df['Upper_Wick'] / today_df['Close']) * 100
            today_df['Lower_Wick_Pct'] = (today_df['Lower_Wick'] / today_df['Close']) * 100
            
            buy_signals = today_df[today_df['Lower_Wick_Pct'] >= wick_threshold]
            sell_signals = today_df[today_df['Upper_Wick_Pct'] >= wick_threshold]
            
            if not buy_signals.empty or not sell_signals.empty:
                # Buy Signals
                for idx, row in buy_signals.iterrows():
                    candle_time = row[time_col].strftime("%Y-%m-%d %H:%M")
                    signal_id = f"{clean_name}_{candle_time}_BUY_WICK"
                    
                    if not any(item.get('id') == signal_id for item in daily_data_history):
                        new_result = {
                            "id": signal_id,
                            "time": candle_time,
                            "symbol": clean_name,
                            "price": round(row['Close'], 2),
                            "signal": f"<span style='color:green;font-weight:bold;'>BUY (Low Wick {round(row['Lower_Wick_Pct'], 2)}%)</span>"
                        }
                        daily_data_history.insert(0, new_result)
                        new_signals_count += 1
                        
                # Sell Signals
                for idx, row in sell_signals.iterrows():
                    candle_time = row[time_col].strftime("%Y-%m-%d %H:%M")
                    signal_id = f"{clean_name}_{candle_time}_SELL_WICK"
                    
                    if not any(item.get('id') == signal_id for item in daily_data_history):
                        new_result = {
                            "id": signal_id,
                            "time": candle_time,
                            "symbol": clean_name,
                            "price": round(row['Close'], 2),
                            "signal": f"<span style='color:red;font-weight:bold;'>SELL (Up Wick {round(row['Upper_Wick_Pct'], 2)}%)</span>"
                        }
                        daily_data_history.insert(0, new_result)
                        new_signals_count += 1

        except Exception as e:
            continue

    # मेमोरी बचाने के लिए सिर्फ लेटेस्ट 200 सिग्नल रखना
    while len(daily_data_history) > 200:
        daily_data_history.pop()

    return jsonify({"status": "Scan Complete", "signals_added": new_signals_count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
