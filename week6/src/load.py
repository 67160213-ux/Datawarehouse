import os
import sqlite3
import pandas as pd
from .config import WAREHOUSE_DB

def load_data(customers, products, sales):
    """
    Load data into SQLite database:
      - dim_customer
      - dim_product
      - fact_sales
    """
    # 1. ตรวจสอบและสร้าง Directory สำหรับ Warehouse หากยังไม่มี
    db_dir = os.path.dirname(WAREHOUSE_DB)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # 2. เชื่อมต่อฐานข้อมูล SQLite
    conn = sqlite3.connect(WAREHOUSE_DB)
    cursor = conn.cursor()

    # 3. สร้างตารางพร้อมกำหนด PRIMARY KEY (UNIQUE constraints)[cite: 1]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            province TEXT,
            email TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id TEXT PRIMARY KEY,
            product_name TEXT,
            category TEXT,
            price REAL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_sales (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT,
            product_id TEXT,
            order_date TEXT,
            qty INTEGER,
            unit_price REAL,
            discount_pct REAL,
            sales_amount REAL,
            FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
            FOREIGN KEY (product_id) REFERENCES dim_product (product_id)
        );
    """)

    # 4. กำหนดและเลือกเฉพาะคอลัมน์ที่ต้องการ เพื่อป้องกันปัญหาคอลัมน์เกิน
    cust_cols = ["customer_id", "name", "province", "email"]
    prod_cols = ["product_id", "product_name", "category", "price"]
    sales_cols = [
        "order_id", "customer_id", "product_id", "order_date", 
        "qty", "unit_price", "discount_pct", "sales_amount"
    ]

    df_cust = customers[cust_cols].drop_duplicates()
    df_prod = products[prod_cols].drop_duplicates()
    df_sales = sales[sales_cols].drop_duplicates().copy()

    # จัดการรูปแบบวันที่ให้เป็น string ก่อนบันทึกลง SQLite
    if pd.api.types.is_datetime64_any_dtype(df_sales["order_date"]):
        df_sales["order_date"] = df_sales["order_date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 5. บันทึกข้อมูลด้วย INSERT OR REPLACE INTO เพื่อป้องกันข้อมูลซ้ำซ้อนเมื่อ rerun[cite: 1]
    cursor.executemany("""
        INSERT OR REPLACE INTO dim_customer (customer_id, name, province, email)
        VALUES (?, ?, ?, ?);
    """, df_cust[cust_cols].values.tolist())

    cursor.executemany("""
        INSERT OR REPLACE INTO dim_product (product_id, product_name, category, price)
        VALUES (?, ?, ?, ?);
    """, df_prod[prod_cols].values.tolist())

    cursor.executemany("""
        INSERT OR REPLACE INTO fact_sales (
            order_id, customer_id, product_id, order_date, qty, unit_price, discount_pct, sales_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, df_sales[sales_cols].values.tolist())

    # Commit การเปลี่ยนแปลงและปิด Connection
    conn.commit()
    conn.close()

    print("=== Load Completed ===")
    print(f"  - Loaded dim_customer : {len(df_cust)} records")
    print(f"  - Loaded dim_product  : {len(df_prod)} records")
    print(f"  - Loaded fact_sales   : {len(df_sales)} records")