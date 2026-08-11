import os
import pandas as pd

def transform_data(raw):
    # ---------------------------------------------------------
    # 1. Clean Customers
    # ---------------------------------------------------------
    df_cust = raw["customers"].copy()
    df_cust = df_cust.drop_duplicates(subset=["customer_id"])
    
    if "province" in df_cust.columns:
        df_cust["province"] = df_cust["province"].astype(str).str.strip().str.title()
        df_cust["province"] = df_cust["province"].replace({"Nan": "Unknown", "None": "Unknown", "nan": "Unknown"})
    else:
        df_cust["province"] = "Unknown"
        
    df_cust["name"] = df_cust["name"].fillna("Unknown") if "name" in df_cust.columns else "Unknown"
    df_cust["email"] = df_cust["email"].fillna("Unknown") if "email" in df_cust.columns else "Unknown"

    # ---------------------------------------------------------
    # 2. Clean Products
    # ---------------------------------------------------------
    df_prod = raw["products"].copy()
    
    # Flatten คอลัมน์ที่เกิดจาก nested JSON (ดึงเฉพาะชื่อคอลัมน์ตัวหลังสุด)
    df_prod.columns = [str(col).split(".")[-1] for col in df_prod.columns]
    
    # แปลงชื่อคอลัมน์ให้เข้ากับมาตรฐาน
    rename_map = {}
    for col in df_prod.columns:
        if col in ["id", "prod_id"]:
            rename_map[col] = "product_id"
        elif col in ["name", "title"]:
            rename_map[col] = "product_name"
        elif col in ["unit_price", "cost", "price_thb"]:
            rename_map[col] = "price"
            
    df_prod = df_prod.rename(columns=rename_map)
    
    # แปลง price เป็น numeric
    if "price" in df_prod.columns:
        df_prod["price"] = pd.to_numeric(df_prod["price"], errors="coerce")
    else:
        df_prod["price"] = 0.0

    # จัดการ missing category
    if "category" in df_prod.columns:
        df_prod["category"] = df_prod["category"].fillna("Unknown")
    else:
        df_prod["category"] = "Unknown"

    df_prod = df_prod.drop_duplicates(subset=["product_id"])

    # ---------------------------------------------------------
    # 3. Clean Orders & Rejects Filtering
    # ---------------------------------------------------------
    df_orders = raw["orders"].copy()
    df_orders = df_orders.drop_duplicates(subset=["order_id"])
    
    df_orders["order_date"] = pd.to_datetime(df_orders["order_date"], errors="coerce")
    df_orders["status"] = df_orders["status"].astype(str).str.strip().str.lower()
    
    df_orders["qty"] = pd.to_numeric(df_orders["qty"], errors="coerce")
    df_orders["unit_price"] = pd.to_numeric(df_orders["unit_price"], errors="coerce")
    df_orders["discount_pct"] = pd.to_numeric(df_orders["discount_pct"], errors="coerce").fillna(0)

    # กฎการคัดออก (Reject conditions)
    cond_valid_qty = df_orders["qty"] > 0
    cond_valid_price = df_orders["unit_price"] > 0
    cond_valid_discount = (df_orders["discount_pct"] >= 0) & (df_orders["discount_pct"] <= 100)
    cond_valid_date = df_orders["order_date"].notna()
    cond_valid_status = df_orders["status"].isin(["paid", "completed"])

    valid_customer_ids = set(df_cust["customer_id"])
    valid_product_ids = set(df_prod["product_id"])
    
    cond_in_master = (
        df_orders["customer_id"].isin(valid_customer_ids) & 
        df_orders["product_id"].isin(valid_product_ids)
    )

    is_valid = (
        cond_valid_qty & 
        cond_valid_price & 
        cond_valid_discount & 
        cond_valid_date & 
        cond_valid_status & 
        cond_in_master
    )

    df_valid_orders = df_orders[is_valid].copy()
    df_rejects = df_orders[~is_valid].copy()

    # ---------------------------------------------------------
    # 4. คำนวณยอดขาย
    # ---------------------------------------------------------
    df_valid_orders["gross_amount"] = df_valid_orders["qty"] * df_valid_orders["unit_price"]
    df_valid_orders["discount_amount"] = df_valid_orders["gross_amount"] * df_valid_orders["discount_pct"] / 100.0
    df_valid_orders["sales_amount"] = df_valid_orders["gross_amount"] - df_valid_orders["discount_amount"]

    # ---------------------------------------------------------
    # 5. บันทึก rejects.csv
    # ---------------------------------------------------------
    os.makedirs("output", exist_ok=True)
    df_rejects.to_csv("output/rejects.csv", index=False)

    return df_cust, df_prod, df_valid_orders, df_rejects