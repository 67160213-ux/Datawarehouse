import json
import os
import sqlite3
import pandas as pd
from .config import WAREHOUSE_DB, OUTPUT_DIR

def validate_data(source_sales):
    # 1. อ่านข้อมูลจากตาราง fact_sales ใน SQLite Warehouse
    conn = sqlite3.connect(WAREHOUSE_DB)
    df_wh = pd.read_sql_query("SELECT * FROM fact_sales", conn)
    conn.close()

    # 2. คำนวณค่าสถานะต่างๆ ตามที่โจทย์กำหนด
    source_valid_rows = int(len(source_sales))
    warehouse_rows = int(len(df_wh))
    
    # นับจำนวน order_id ที่ซ้ำใน warehouse
    duplicate_order_ids = int(df_wh["order_id"].duplicated().sum())

    # คำนวณยอดขายรวม (แปลงเป็น float และปัดเศษ 2 ตำแหน่ง)
    source_total_sales = round(float(source_sales["sales_amount"].sum()), 2)
    warehouse_total_sales = round(float(df_wh["sales_amount"].sum()), 2)

    # 3. ประเมินผล PASS / FAIL
    is_rows_match = (source_valid_rows == warehouse_rows)
    is_no_duplicates = (duplicate_order_ids == 0)
    is_sales_match = (abs(source_total_sales - warehouse_total_sales) < 0.01)

    status = "PASS" if (is_rows_match and is_no_duplicates and is_sales_match) else "FAIL"

    # 4. สร้าง Dictionary ผลการตรวจสอบ
    validation_result = {
        "source_valid_rows": source_valid_rows,
        "warehouse_rows": warehouse_rows,
        "duplicate_order_ids": duplicate_order_ids,
        "source_total_sales": source_total_sales,
        "warehouse_total_sales": warehouse_total_sales,
        "status": status
    }

    # 5. บันทึกผลลัพธ์ลงไฟล์ output/validation.json
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "validation.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, indent=4)

    print("=== Validation Completed ===")
    print(f"  - Status : {status}")
    print(f"  - Result Saved to : {json_path}")

    return validation_result
