import json
import sqlite3
import pandas as pd
from pathlib import Path
from .config import RAW_DIR, SOURCE_DB

def extract_data():
    """
    TODO 1
    Extract data from:
      - customers.csv
      - orders.csv
      - products.json
      - stores table in store.db
    Return a dictionary of DataFrames.
    """

    raw_path = Path(RAW_DIR)

    # 1. อ่านไฟล์ CSV
    df_customers = pd.read_csv(raw_path / "customers.csv")
    df_orders = pd.read_csv(raw_path / "orders.csv")

    # 2. อ่านไฟล์ products.json และทำ flatten ด้วย pd.json_normalize()[cite: 1]
    with open(raw_path / "products.json", "r", encoding="utf-8") as f:
        products_data = json.load(f)
    df_products = pd.json_normalize(products_data)

    # 3. อ่านตาราง stores จาก store.db[cite: 1]
    conn = sqlite3.connect(SOURCE_DB)
    df_stores = pd.read_sql_query("SELECT * FROM stores", conn)
    conn.close()

    # 4. รวมเป็น Dictionary ตามข้อกำหนด[cite: 1]
    raw = {
        "customers": df_customers,
        "orders": df_orders,
        "products": df_products,
        "stores": df_stores
    }

    # Checkpoint ตรวจสอบข้อมูลเบื้องต้น[cite: 1]
    print("=== Extract Completed ===")
    for name, df in raw.items():
        print(f"  - {name}: {df.shape[0]} rows, {df.shape[1]} columns")

    return raw
    raise NotImplementedError