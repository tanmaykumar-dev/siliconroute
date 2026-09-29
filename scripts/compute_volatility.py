from sqlmodel import Session
from app.db import engine
from app.api.analysis import get_session_variability

with Session(engine) as session:
    data = get_session_variability(session)
    print("=== REALIGNED BENCHMARK-GRADE VOLATILITY BANDS ===")
    for item in data["summary"]:
        print(f"Device {item['device_key']} ({item['device_label']}): median={item['volatility_band_pct']:.1f}% ({item['multi_session_configs_count']} configs), max={item['max_volatility_pct']:.1f}%")
