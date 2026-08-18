import os
import pandas as pd
from .config import PROVINCE_MAP, OUTPUT_DIR

def transform_data(raw):
    # ---------------------------------------------------------
    # 1. Clean Customers
    # ---------------------------------------------------------
    df_cust = raw["customers"].copy()
    df_cust = df_cust.drop_duplicates(subset=["customer_id"])
    
    def clean_province(val):
        if pd.isna(val):
            return "Unknown"
        val_str = str(val).strip()
        if val_str.lower() in ["nan", "none", "null", ""]:
            return "Unknown"
        return PROVINCE_MAP.get(val_str.lower(), val_str.title())

    if "province" in df_cust.columns:
        df_cust["province"] = df_cust["province"].apply(clean_province)
    else:
        df_cust["province"] = "Unknown"
        
    df_cust["name"] = df_cust["name"].fillna("Unknown") if "name" in df_cust.columns else "Unknown"
    df_cust["email"] = df_cust["email"].fillna("Unknown") if "email" in df_cust.columns else "Unknown"

    # ---------------------------------------------------------
    # 2. Clean Products
    # ---------------------------------------------------------
    df_prod = raw["products"].copy()
    
    # Rename columns based on normalized JSON fields or legacy naming
    rename_map = {
        "category.name": "category",
        "pricing.price": "price",
        "id": "product_id",
        "prod_id": "product_id",
        "unit_price": "price",
        "cost": "price",
        "price_thb": "price"
    }
    df_prod = df_prod.rename(columns=rename_map)
    
    # Check if category wasn't mapped due to single level
    if "category.name" not in raw["products"].columns and "category" not in df_prod.columns:
        df_prod["category"] = "Unknown"

    # Clean price
    if "price" in df_prod.columns:
        df_prod["price"] = df_prod["price"].astype(str).str.replace(",", "").str.strip()
        df_prod["price"] = pd.to_numeric(df_prod["price"], errors="coerce")
    else:
        df_prod["price"] = 0.0

    # Clean category missing
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
    
    df_orders["order_date"] = pd.to_datetime(df_orders["order_date"], errors="coerce", format="mixed")
    df_orders["status"] = df_orders["status"].astype(str).str.strip().str.lower()
    
    df_orders["qty"] = pd.to_numeric(df_orders["qty"], errors="coerce")
    df_orders["unit_price"] = pd.to_numeric(df_orders["unit_price"], errors="coerce")
    df_orders["discount_pct"] = pd.to_numeric(df_orders["discount_pct"], errors="coerce")

    # Reject conditions
    cond_valid_qty = df_orders["qty"].notna() & (df_orders["qty"] > 0)
    cond_valid_price = df_orders["unit_price"].notna() & (df_orders["unit_price"] > 0)
    cond_valid_discount = df_orders["discount_pct"].notna() & (df_orders["discount_pct"] >= 0) & (df_orders["discount_pct"] <= 100)
    cond_valid_date = df_orders["order_date"].notna()
    cond_valid_status = df_orders["status"].isin(["paid", "completed"])

    valid_customer_ids = set(df_cust["customer_id"].dropna())
    valid_product_ids = set(df_prod["product_id"].dropna())
    
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
    # 4. Calculate Sales
    # ---------------------------------------------------------
    df_valid_orders["gross_amount"] = df_valid_orders["qty"] * df_valid_orders["unit_price"]
    df_valid_orders["discount_amount"] = df_valid_orders["gross_amount"] * df_valid_orders["discount_pct"] / 100.0
    df_valid_orders["sales_amount"] = df_valid_orders["gross_amount"] - df_valid_orders["discount_amount"]

    # ---------------------------------------------------------
    # 5. Save rejects.csv
    # ---------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_rejects.to_csv(OUTPUT_DIR / "rejects.csv", index=False)

    return df_cust, df_prod, df_valid_orders, df_rejects