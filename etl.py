import os
import time
from supabase import create_client, Client
import yfinance as yf

def run_etl():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("Missing Supabase environment variables.")
        
    supabase: Client = create_client(supabase_url, supabase_key)
    
    tickers = ["BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD", "BNB-USD"]
    
    for ticker in tickers:
        try:
            asset = yf.Ticker(ticker)
            info = asset.info
            
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not current_price:
                print(f"Could not fetch price for {ticker}, skipping.")
                continue
                
            data_payload = {
                "symbol": ticker,
                "current_price": current_price,
                "previous_close": info.get("previousClose"),
                "market_cap": info.get("marketCap"),
                "name": info.get("shortName") or info.get("name") or ticker,
                "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            
            response = supabase.table("crypto_data").upsert(data_payload).execute()
            print(f"Upserted {ticker}: {response.data}")
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
        time.sleep(1)   # be polite to Yahoo

if __name__ == "__main__":
    run_etl()