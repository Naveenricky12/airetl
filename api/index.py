import sys
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text

# Add the parent and src directory to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

# Now we can import the pipeline components
try:
    from config import Config
    import extract
    import transform
    import load
except ImportError as e:
    # Fallback/Mock config if importing fails locally
    class Config:
        VISUALCROSSING_API_KEY = os.getenv("VISUALCROSSING_API_KEY")
        AIRVISUAL_API_KEY = os.getenv("AIRVISUAL_API_KEY")
        DATABASE_URL = os.getenv("DATABASE_URL")
        DEFAULT_CITY = "ioannina"
        DEFAULT_STATE = "epirus"
        DEFAULT_COUNTRY = "greece"
        DEFAULT_START_DATE = "2026-05-01"
        DEFAULT_END_DATE = "2026-05-20"

app = FastAPI()

# Setup templates directory
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Helper to check if credentials are set
def has_real_credentials():
    vc_key = Config.VISUALCROSSING_API_KEY
    av_key = Config.AIRVISUAL_API_KEY
    
    # Check if empty, None, or placeholder
    if not vc_key or not av_key:
        return False
    if "your_" in vc_key or "<" in vc_key or "your_" in av_key or "<" in av_key:
        return False
    return True

# Helper to check if database is set
def has_real_database():
    db_url = Config.DATABASE_URL
    if not db_url:
        return False
    if "postgresql://" not in db_url or "username" in db_url or "<" in db_url:
        return False
    return True

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def get_status():
    is_prod = has_real_credentials() and has_real_database()
    
    # Check keys
    vc_status = "configured" if (Config.VISUALCROSSING_API_KEY and "your_" not in Config.VISUALCROSSING_API_KEY and "<" not in Config.VISUALCROSSING_API_KEY) else "not_configured"
    av_status = "configured" if (Config.AIRVISUAL_API_KEY and "your_" not in Config.AIRVISUAL_API_KEY and "<" not in Config.AIRVISUAL_API_KEY) else "not_configured"
    
    db_status = "not_configured"
    if has_real_database():
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            db_status = "failed_connection"

    return {
        "mode": "production" if is_prod else "simulation",
        "keys": {
            "visual_crossing": vc_status,
            "air_visual": av_status
        },
        "database": db_status
    }

@app.post("/api/run")
async def run_pipeline():
    logs = []
    
    # Setup VERCEL environment output directory
    output_dir = "/tmp" if os.environ.get("VERCEL") else "."
    
    try:
        if has_real_credentials():
            logs.append("Running in Production Mode with live APIs.")
            # Run extract
            extract.main()
            logs.append("Extraction completed successfully.")
            # Run transform
            transform.main()
            logs.append("Transformation completed successfully.")
            
            # Run load if DB is set
            if has_real_database():
                load.main()
                logs.append("Loading to PostgreSQL completed successfully.")
            else:
                logs.append("Skipping database load: DATABASE_URL not configured.")
        else:
            logs.append("Running in Simulation Mode (Credentials missing/placeholders).")
            # Generate simulated weather data
            simulated_days = []
            start_date = datetime.now() - timedelta(days=15)
            for i in range(15):
                curr_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                simulated_days.append({
                    "datetime": curr_date,
                    "temp": round(15.0 + (i * 0.7) % 15.0, 1),
                    "feelslike": round(14.5 + (i * 0.8) % 15.0, 1),
                    "humidity": round(50.0 + (i * 3) % 40.0, 1),
                    "precip": round((i * 1.2) % 4.0, 2) if i % 4 == 0 else 0.0,
                    "windspeed": round(10.0 + (i * 1.5) % 25.0, 1)
                })
            
            weather_data = {
                "address": "Simulated City",
                "days": simulated_days
            }
            
            # Save raw data
            weather_path = os.path.join(output_dir, "weather_data.json")
            with open(weather_path, "w") as file:
                json.dump(weather_data, file, indent=4)
            logs.append(f"Simulated weather data written to {weather_path}")
            
            # Run the transform component
            transform.main()
            logs.append("Simulated transformation completed successfully.")
            
            # Handle DB or local csv simulation
            if has_real_database():
                load.main()
                logs.append("Loaded simulated data into PostgreSQL.")
            else:
                logs.append("Skipping DB load: DATABASE_URL not configured. Data saved locally in /tmp.")
                
        return {"status": "success", "message": "ETL pipeline execution succeeded.", "logs": logs}
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(e), "logs": logs}
        )

@app.get("/api/cron")
async def cron_endpoint():
    # Route for automatic Vercel cron triggers
    res = await run_pipeline()
    return res

@app.get("/api/data")
async def get_data():
    # Fetch data either from DB or the local transformed CSV
    output_dir = "/tmp" if os.environ.get("VERCEL") else "."
    csv_path = os.path.join(output_dir, "transformed_weather_data.csv")
    
    # 1. Try PostgreSQL if configured
    if has_real_database():
        try:
            engine = create_engine(Config.DATABASE_URL)
            df = pd.read_sql_table("weather_data", engine)
            # Convert date to string format YYYY-MM-DD
            if 'date' in df.columns:
                df['date'] = df['date'].astype(str)
            records = df.to_dict(orient="records")
            return records
        except Exception as e:
            # Fallback to local CSV if DB fetch fails
            pass
            
    # 2. Try CSV from disk
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            # Ensure dates are strings
            if 'date' in df.columns:
                df['date'] = df['date'].astype(str)
            return df.to_dict(orient="records")
        except Exception:
            pass
            
    # 3. Fallback mock data if nothing exists
    mock_records = []
    start_date = datetime.now() - timedelta(days=10)
    for i in range(10):
        curr_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        mock_records.append({
            "date": curr_date,
            "temperature": round(20.5 + (i * 0.5), 1),
            "feels_like": round(21.0 + (i * 0.4), 1),
            "humidity": 65 - i,
            "precipitation": 0.0 if i != 3 else 1.5,
            "wind_speed": 12.0 + i
        })
    return mock_records
