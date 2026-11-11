from flask import Flask, render_template, jsonify
from datetime import datetime
import pytz

app = Flask(__name__)

# दिन भर का डेटा सेव रखने के लिए एक खाली लिस्ट
daily_data_history = []
tz = pytz.timezone('Asia/Kolkata')

# 1. जब आप वेबसाइट खोलेंगे तो यह HTML पेज दिखाएगा
@app.route('/')
def home():
    return render_template('index.html')

# 2. यह वेबसाइट को हिस्ट्री डेटा भेजने का रास्ता है
@app.route('/api/data')
def get_data():
    return jsonify(daily_data_history)

# 3. यह वह लिंक है जिसे हम क्लाउड में हर 5 मिनट में ऑटोमैटिक चलाएंगे
@app.route('/trigger-5min')
def run_5min_scanner():
    now = datetime.now(tz).strftime("%d-%b %H:%M:%S")
    
    # (यहाँ हम बाद में आपका असली yfinance का कोड डालेंगे)
    # अभी के लिए एक डमी डेटा बना रहे हैं:
    new_result = {
        "time": now,
        "symbol": "NIFTY 50",
        "signal": "Testing 5-Min Strategy",
        "price": 22000
    }
    
    # नए डेटा को लिस्ट में सबसे ऊपर जोड़ें
    daily_data_history.insert(0, new_result)
    
    # अगर डेटा बहुत ज्यादा हो जाए तो पुराना डेटा हटा दें (मेमोरी बचाने के लिए)
    if len(daily_data_history) > 200:
        daily_data_history.pop()
        
    return jsonify({"status": "Scanner Run Successfully", "time": now})

if __name__ == '__main__':
    # क्लाउड पर रन करने के लिए
    app.run(host='0.0.0.0', port=10000)
