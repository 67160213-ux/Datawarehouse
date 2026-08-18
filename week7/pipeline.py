import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ETL_Pipeline")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class PipelineConfig:
    dataset_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "Python_Data_Pipeline_Lab_Dataset (1).xlsx"))
    db_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "retail_dw.db"))
    quarantine_csv_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "quarantine.csv"))
    run_log_csv_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "pipeline_run_log.csv"))
    batch_list: list = field(default_factory=lambda: ["orders_batch_1", "orders_batch_2", "orders_batch_3"])
    error_mode: str = "quarantine"  # 'quarantine' or 'strict'



class ETLPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(self.config.db_path)

    def init_database(self):
        """Creates Star Schema and pipeline metadata tables if they don't exist."""
        logger.info(f"Initializing database at: {self.config.db_path}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. dim_customer
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_customer (
                customer_key INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT UNIQUE NOT NULL,
                customer_name TEXT,
                province TEXT,
                segment TEXT,
                signup_date TEXT
            );
            """)

            # 2. dim_product
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_product (
                product_key INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT,
                category TEXT,
                unit_price REAL,
                active_flag TEXT
            );
            """)

            # 3. dim_date
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_date (
                date_key INTEGER PRIMARY KEY,
                full_date TEXT UNIQUE NOT NULL,
                day INTEGER,
                month INTEGER,
                quarter INTEGER,
                year INTEGER
            );
            """)

            # 4. fact_sales
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_sales (
                order_id TEXT PRIMARY KEY,
                date_key INTEGER REFERENCES dim_date(date_key),
                customer_key INTEGER REFERENCES dim_customer(customer_key),
                product_key INTEGER REFERENCES dim_product(product_key),
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                discount_pct REAL NOT NULL,
                gross_amount REAL NOT NULL,
                net_amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                sales_channel TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_batch INTEGER NOT NULL
            );
            """)

            # 5. quarantine
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                order_datetime TEXT,
                customer_id TEXT,
                product_id TEXT,
                quantity TEXT,
                unit_price TEXT,
                discount_pct TEXT,
                payment_method TEXT,
                sales_channel TEXT,
                updated_at TEXT,
                source_batch INTEGER,
                reason_code TEXT,
                quarantined_at TEXT
            );
            """)

            # 6. pipeline_run_log
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_run_log (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                rows_read INTEGER NOT NULL,
                rows_valid INTEGER NOT NULL,
                rows_rejected INTEGER NOT NULL,
                rows_duplicated INTEGER NOT NULL,
                rows_loaded INTEGER NOT NULL,
                net_sales_loaded REAL NOT NULL,
                status TEXT NOT NULL
            );
            """)

            conn.commit()
        logger.info("Database schema initialized successfully.")

    def load_dimensions(self):
        """Extracts and populates dim_customer, dim_product, and dim_date from Excel."""
        logger.info("Extracting and loading dimension tables...")
        xl = pd.ExcelFile(self.config.dataset_path)
        
        # Load customers
        cust_df = xl.parse('customers')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _, row in cust_df.iterrows():
                cursor.execute("""
                INSERT OR IGNORE INTO dim_customer (customer_id, customer_name, province, segment, signup_date)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    str(row['customer_id']).strip(),
                    str(row['customer_name']).strip(),
                    str(row['province']).strip(),
                    str(row['segment']).strip(),
                    str(row['signup_date']).strip()
                ))
            conn.commit()

        # Load products
        prod_df = xl.parse('products')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _, row in prod_df.iterrows():
                cursor.execute("""
                INSERT OR IGNORE INTO dim_product (product_id, product_name, category, unit_price, active_flag)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    str(row['product_id']).strip(),
                    str(row['product_name']).strip(),
                    str(row['category']).strip(),
                    float(row['unit_price']),
                    str(row['active_flag']).strip()
                ))
            conn.commit()
            
        logger.info("Dimensions loaded successfully.")

    def _ensure_date_keys(self, date_series):
        """Populates dim_date with any new date values found in orders."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for dt in date_series.dropna().unique():
                if isinstance(dt, str):
                    dt = pd.to_datetime(dt)
                date_key = int(dt.strftime("%Y%m%d"))
                full_date = dt.strftime("%Y-%m-%d")
                day = dt.day
                month = dt.month
                quarter = dt.quarter
                year = dt.year
                cursor.execute("""
                INSERT OR IGNORE INTO dim_date (date_key, full_date, day, month, quarter, year)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (date_key, full_date, day, month, quarter, year))
            conn.commit()

    def process_batch(self, batch_name: str) -> dict:
        """Extracts, transforms, validates, and loads a single batch into DW."""
        start_time = datetime.now()
        started_at_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"--- Starting batch execution: {batch_name} at {started_at_str} ---")

        # 1. EXTRACT
        try:
            xl = pd.ExcelFile(self.config.dataset_path)
            raw_df = xl.parse(batch_name)
        except Exception as e:
            logger.error(f"Failed to read sheet {batch_name}: {e}")
            ended_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._write_run_log(batch_name, started_at_str, ended_at_str, 0, 0, 0, 0, 0, 0.0, "FAILED")
            return {"status": "FAILED", "error": str(e)}

        rows_read = len(raw_df)
        logger.info(f"[{batch_name}] Read {rows_read} raw records.")

        # Load fresh customer and product lookup dictionaries
        with self.get_connection() as conn:
            cust_lookup = dict(conn.execute("SELECT customer_id, customer_key FROM dim_customer").fetchall())
            prod_lookup = dict(conn.execute("SELECT product_id, product_key FROM dim_product").fetchall())

        # 2. TRANSFORM & VALIDATE
        reasons = []
        parsed_order_dts = []
        parsed_updated_ats = []
        clean_quantities = []
        clean_prices = []
        clean_discounts = []
        norm_payments = []
        norm_channels = []

        pm_mapping = {
            'cash': 'Cash',
            'bank transfer': 'Bank Transfer',
            'promptpay': 'PromptPay',
            'credit card': 'Credit Card'
        }

        sc_mapping = {
            'store': 'Store',
            'online': 'Online',
            'marketplace': 'Marketplace',
            'e-commerce': 'Online'
        }

        for idx, row in raw_df.iterrows():
            r_list = []

            # Validate order_datetime
            order_dt = None
            try:
                if pd.notna(row['order_datetime']):
                    order_dt = pd.to_datetime(row['order_datetime'])
                    if pd.isna(order_dt):
                        r_list.append("INVALID_DATETIME")
                else:
                    r_list.append("INVALID_DATETIME")
            except Exception:
                r_list.append("INVALID_DATETIME")
            parsed_order_dts.append(order_dt)

            # Validate updated_at
            updated_dt = None
            try:
                if pd.notna(row['updated_at']):
                    updated_dt = pd.to_datetime(row['updated_at'])
            except Exception:
                pass
            parsed_updated_ats.append(updated_dt)

            # Validate customer_id FK
            cid = str(row['customer_id']).strip() if pd.notna(row['customer_id']) else ''
            if not cid or cid not in cust_lookup:
                r_list.append("INVALID_CUSTOMER_FK")

            # Validate product_id FK
            pid = str(row['product_id']).strip() if pd.notna(row['product_id']) else ''
            if not pid or pid not in prod_lookup:
                r_list.append("INVALID_PRODUCT_FK")

            # Validate quantity (must be numeric integer 1 to 20)
            q_val = None
            try:
                q_num = float(row['quantity'])
                if np.isnan(q_num) or q_num <= 0 or q_num > 20 or q_num % 1 != 0:
                    r_list.append("INVALID_QUANTITY")
                else:
                    q_val = int(q_num)
            except Exception:
                r_list.append("INVALID_QUANTITY")
            clean_quantities.append(q_val)

            # Validate unit_price (> 0)
            p_val = None
            try:
                p_num = float(row['unit_price'])
                if np.isnan(p_num) or p_num <= 0:
                    r_list.append("INVALID_UNIT_PRICE")
                else:
                    p_val = round(p_num, 2)
            except Exception:
                r_list.append("INVALID_UNIT_PRICE")
            clean_prices.append(p_val)

            # Validate discount_pct (0 to 100)
            d_val = None
            try:
                d_num = float(row['discount_pct'])
                if np.isnan(d_num) or d_num < 0 or d_num > 100:
                    r_list.append("INVALID_DISCOUNT")
                else:
                    d_val = round(d_num, 2)
            except Exception:
                r_list.append("INVALID_DISCOUNT")
            clean_discounts.append(d_val)

            # Normalize payment_method
            pm_raw = str(row['payment_method']).strip().lower() if pd.notna(row['payment_method']) else ''
            norm_payments.append(pm_mapping.get(pm_raw, str(row['payment_method']).strip() if pd.notna(row['payment_method']) else 'Unknown'))

            # Normalize sales_channel
            sc_raw = str(row['sales_channel']).strip().lower() if pd.notna(row['sales_channel']) else ''
            norm_channels.append(sc_mapping.get(sc_raw, str(row['sales_channel']).strip() if pd.notna(row['sales_channel']) else 'Unknown'))

            reasons.append("; ".join(r_list))

        # Attach computed arrays
        df_working = raw_df.copy()
        df_working['reason_code'] = reasons
        df_working['parsed_order_dt'] = parsed_order_dts
        df_working['parsed_updated_dt'] = parsed_updated_ats
        df_working['clean_quantity'] = clean_quantities
        df_working['clean_unit_price'] = clean_prices
        df_working['clean_discount_pct'] = clean_discounts
        df_working['norm_payment_method'] = norm_payments
        df_working['norm_sales_channel'] = norm_channels

        # Segregate Clean vs Quarantine
        valid_df = df_working[df_working['reason_code'] == ''].copy()
        quarantine_df = df_working[df_working['reason_code'] != ''].copy()

        rows_valid = len(valid_df)
        rows_rejected = len(quarantine_df)

        logger.info(f"[{batch_name}] Valid rows: {rows_valid}, Rejected rows: {rows_rejected}")
        # Note: Accounting formula verification
        assert rows_read == rows_valid + rows_rejected, "Accounting mismatch: read != valid + rejected"

        # 3. QUARANTINE PROCESSING
        if rows_rejected > 0:
            self._handle_quarantine(quarantine_df, batch_name)

        # 4. DEDUPLICATION (Within valid batch)
        # Deduplicate by order_id keeping latest updated_at
        rows_duplicated = 0
        if rows_valid > 0:
            initial_valid_count = len(valid_df)
            valid_df = valid_df.sort_values('parsed_updated_dt').groupby('order_id').last().reset_index()
            rows_duplicated = initial_valid_count - len(valid_df)
            logger.info(f"[{batch_name}] Deduplicated internal duplicate rows: {rows_duplicated}")

        # 5. DERIVED COLUMNS & DATE KEYS
        if rows_valid > 0:
            valid_df['gross_amount'] = (valid_df['clean_quantity'] * valid_df['clean_unit_price']).round(2)
            valid_df['net_amount'] = (valid_df['gross_amount'] * (1 - valid_df['clean_discount_pct'] / 100.0)).round(2)
            
            # Ensure dim_date records exist
            self._ensure_date_keys(valid_df['parsed_order_dt'])
            valid_df['date_key'] = valid_df['parsed_order_dt'].apply(lambda dt: int(dt.strftime("%Y%m%d")))
            valid_df['customer_key'] = valid_df['customer_id'].astype(str).str.strip().map(cust_lookup)
            valid_df['product_key'] = valid_df['product_id'].astype(str).str.strip().map(prod_lookup)

        # 6. LOAD & IDEMPOTENCY (UPSERT)
        rows_loaded = 0
        net_sales_loaded = 0.0

        if rows_valid > 0:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for _, row in valid_df.iterrows():
                    order_id = str(row['order_id']).strip()
                    updated_at_str = row['parsed_updated_dt'].strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Check if order_id already exists in fact_sales
                    cursor.execute("SELECT updated_at FROM fact_sales WHERE order_id = ?", (order_id,))
                    existing = cursor.fetchone()

                    if existing is None:
                        # INSERT new record
                        cursor.execute("""
                        INSERT INTO fact_sales (
                            order_id, date_key, customer_key, product_key,
                            quantity, unit_price, discount_pct, gross_amount, net_amount,
                            payment_method, sales_channel, updated_at, source_batch
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            order_id,
                            int(row['date_key']),
                            int(row['customer_key']),
                            int(row['product_key']),
                            int(row['clean_quantity']),
                            float(row['clean_unit_price']),
                            float(row['clean_discount_pct']),
                            float(row['gross_amount']),
                            float(row['net_amount']),
                            str(row['norm_payment_method']),
                            str(row['norm_sales_channel']),
                            updated_at_str,
                            int(row['source_batch'])
                        ))
                        rows_loaded += 1
                        net_sales_loaded += float(row['net_amount'])
                    else:
                        # Compare updated_at timestamps
                        existing_updated_at = existing[0]
                        if updated_at_str > existing_updated_at:
                            # UPDATE existing record
                            cursor.execute("""
                            UPDATE fact_sales SET
                                date_key = ?, customer_key = ?, product_key = ?,
                                quantity = ?, unit_price = ?, discount_pct = ?,
                                gross_amount = ?, net_amount = ?, payment_method = ?,
                                sales_channel = ?, updated_at = ?, source_batch = ?
                            WHERE order_id = ?
                            """, (
                                int(row['date_key']),
                                int(row['customer_key']),
                                int(row['product_key']),
                                int(row['clean_quantity']),
                                float(row['clean_unit_price']),
                                float(row['clean_discount_pct']),
                                float(row['gross_amount']),
                                float(row['net_amount']),
                                str(row['norm_payment_method']),
                                str(row['norm_sales_channel']),
                                updated_at_str,
                                int(row['source_batch']),
                                order_id
                            ))
                            rows_loaded += 1
                            net_sales_loaded += float(row['net_amount'])
                        else:
                            # Skip (record in DB is up to date or newer)
                            pass

                conn.commit()

        ended_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS"
        self._write_run_log(batch_name, started_at_str, ended_at_str, rows_read, rows_valid, rows_rejected, rows_duplicated, rows_loaded, round(net_sales_loaded, 2), status)

        logger.info(f"[{batch_name}] Completed! Loaded/Updated: {rows_loaded} rows, Net Sales: ${net_sales_loaded:,.2f}")
        return {
            "batch_name": batch_name,
            "rows_read": rows_read,
            "rows_valid": rows_valid,
            "rows_rejected": rows_rejected,
            "rows_duplicated": rows_duplicated,
            "rows_loaded": rows_loaded,
            "net_sales_loaded": round(net_sales_loaded, 2),
            "status": status
        }

    def _handle_quarantine(self, quarantine_df: pd.DataFrame, batch_name: str):
        """Saves rejected records into database quarantine table and quarantine.csv."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        quarantine_records = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _, row in quarantine_df.iterrows():
                rec = {
                    "order_id": str(row['order_id']) if pd.notna(row['order_id']) else '',
                    "order_datetime": str(row['order_datetime']) if pd.notna(row['order_datetime']) else '',
                    "customer_id": str(row['customer_id']) if pd.notna(row['customer_id']) else '',
                    "product_id": str(row['product_id']) if pd.notna(row['product_id']) else '',
                    "quantity": str(row['quantity']) if pd.notna(row['quantity']) else '',
                    "unit_price": str(row['unit_price']) if pd.notna(row['unit_price']) else '',
                    "discount_pct": str(row['discount_pct']) if pd.notna(row['discount_pct']) else '',
                    "payment_method": str(row['payment_method']) if pd.notna(row['payment_method']) else '',
                    "sales_channel": str(row['sales_channel']) if pd.notna(row['sales_channel']) else '',
                    "updated_at": str(row['updated_at']) if pd.notna(row['updated_at']) else '',
                    "source_batch": int(row['source_batch']) if pd.notna(row['source_batch']) else 0,
                    "reason_code": str(row['reason_code']),
                    "quarantined_at": now_str
                }
                quarantine_records.append(rec)
                
                cursor.execute("""
                INSERT INTO quarantine (
                    order_id, order_datetime, customer_id, product_id, quantity,
                    unit_price, discount_pct, payment_method, sales_channel, updated_at,
                    source_batch, reason_code, quarantined_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rec["order_id"], rec["order_datetime"], rec["customer_id"], rec["product_id"],
                    rec["quantity"], rec["unit_price"], rec["discount_pct"], rec["payment_method"],
                    rec["sales_channel"], rec["updated_at"], rec["source_batch"], rec["reason_code"], rec["quarantined_at"]
                ))
            conn.commit()

        # Write or append to quarantine.csv
        q_export_df = pd.DataFrame(quarantine_records)
        file_exists = os.path.exists(self.config.quarantine_csv_path)
        q_export_df.to_csv(self.config.quarantine_csv_path, mode='a' if file_exists else 'w', index=False, header=not file_exists)
        logger.info(f"Appended {len(q_export_df)} quarantine records to {self.config.quarantine_csv_path}")

    def _write_run_log(self, batch_name, started_at, ended_at, read, valid, rejected, duplicated, loaded, net_sales, status):
        """Logs pipeline metrics to database table and pipeline_run_log.csv."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO pipeline_run_log (
                batch_name, started_at, ended_at, rows_read, rows_valid,
                rows_rejected, rows_duplicated, rows_loaded, net_sales_loaded, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (batch_name, started_at, ended_at, read, valid, rejected, duplicated, loaded, net_sales, status))
            conn.commit()

        log_entry = {
            "batch_name": batch_name,
            "started_at": started_at,
            "ended_at": ended_at,
            "rows_read": read,
            "rows_valid": valid,
            "rows_rejected": rejected,
            "rows_duplicated": duplicated,
            "rows_loaded": loaded,
            "net_sales_loaded": net_sales,
            "status": status
        }
        log_df = pd.DataFrame([log_entry])
        file_exists = os.path.exists(self.config.run_log_csv_path)
        log_df.to_csv(self.config.run_log_csv_path, mode='a' if file_exists else 'w', index=False, header=not file_exists)


def run_pipeline(config: PipelineConfig):
    """Executes the master pipeline workflow across dimensions and batches."""
    logger.info("================ STARTING ETL PIPELINE EXECUTION ================")
    pipeline = ETLPipeline(config)
    pipeline.load_dimensions()

    for batch in config.batch_list:
        pipeline.process_batch(batch)

    logger.info("================ ETL PIPELINE COMPLETED SUCCESSFULLY ================")


def run_acceptance_tests(config: PipelineConfig):
    """Automated Acceptance Test Suite verifying all lab requirements."""
    logger.info("\n================ RUNNING ACCEPTANCE TEST SUITE ================")
    
    # Clean previous run artifacts for a deterministic test
    for path in [config.db_path, config.quarantine_csv_path, config.run_log_csv_path]:
        if os.path.exists(path):
            os.remove(path)

    pipeline = ETLPipeline(config)
    pipeline.load_dimensions()

    # TEST ROUND 1: Run batch_1
    logger.info("--- TEST ROUND 1: Processing orders_batch_1 ---")
    r1 = pipeline.process_batch("orders_batch_1")
    
    # TEST ROUND 2: Re-run batch_1 (Idempotency Check)
    logger.info("--- TEST ROUND 2: Re-running orders_batch_1 (Idempotency Check) ---")
    r2 = pipeline.process_batch("orders_batch_1")

    # TEST ROUND 3: Run batch_2
    logger.info("--- TEST ROUND 3: Processing orders_batch_2 ---")
    r3 = pipeline.process_batch("orders_batch_2")

    # TEST ROUND 4: Run batch_3
    logger.info("--- TEST ROUND 4: Processing orders_batch_3 ---")
    r4 = pipeline.process_batch("orders_batch_3")

    # VERIFICATION & ASSERTIONS
    logger.info("\n--- VERIFYING ACCEPTANCE TEST CRITERIA ---")
    with pipeline.get_connection() as conn:
        cursor = conn.cursor()

        # 1. Total Fact rows and unique order_id check
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT order_id) FROM fact_sales")
        total_fact, unique_fact = cursor.fetchone()
        logger.info(f"Fact Table Total Rows: {total_fact}, Unique order_ids: {unique_fact}")
        assert total_fact == unique_fact, "FAIL: Duplicate order_id found in fact_sales!"
        logger.info("PASS: order_id in fact_sales is 100% unique.")

        # 2. Foreign Key Integrity check
        cursor.execute("""
        SELECT COUNT(*) FROM fact_sales f
        LEFT JOIN dim_customer c ON f.customer_key = c.customer_key
        LEFT JOIN dim_product p ON f.product_key = p.product_key
        LEFT JOIN dim_date d ON f.date_key = d.date_key
        WHERE c.customer_key IS NULL OR p.product_key IS NULL OR d.date_key IS NULL
        """)
        orphans = cursor.fetchone()[0]
        assert orphans == 0, f"FAIL: Found {orphans} orphaned foreign keys in fact_sales!"
        logger.info("PASS: 100% of Foreign Keys in Fact table resolve to Dimension tables.")

        # 3. Numeric range check (quantity > 0, unit_price > 0, net_amount >= 0)
        cursor.execute("""
        SELECT COUNT(*) FROM fact_sales
        WHERE quantity <= 0 OR unit_price <= 0 OR net_amount < 0
        """)
        invalid_numerics = cursor.fetchone()[0]
        assert invalid_numerics == 0, f"FAIL: Found {invalid_numerics} negative/zero values in Fact table!"
        logger.info("PASS: All quantity, unit_price, and net_amount values are strictly positive.")

        # 4. Idempotency Check (Round 2 loaded 0 new rows)
        assert r2['rows_loaded'] == 0, f"FAIL: Re-running batch_1 inserted {r2['rows_loaded']} rows!"
        logger.info("PASS: Idempotency verified. Re-running batch_1 added 0 new rows to DW.")

        # 5. Quarantine Reason Code completeness
        cursor.execute("SELECT COUNT(*) FROM quarantine WHERE reason_code IS NULL OR reason_code = ''")
        unreasoned_quarantine = cursor.fetchone()[0]
        assert unreasoned_quarantine == 0, f"FAIL: Found {unreasoned_quarantine} quarantine records missing reason_code!"
        logger.info("PASS: 100% of quarantined records have explicit reason codes.")

        # 6. Read accounting check (read = valid + rejected)
        cursor.execute("SELECT batch_name, rows_read, rows_valid, rows_rejected FROM pipeline_run_log")
        logs = cursor.fetchall()
        for log in logs:
            bname, read, valid, rejected = log
            assert read == valid + rejected, f"FAIL: Read accounting mismatch for {bname}: {read} != {valid} + {rejected}"
        logger.info("PASS: Run log read accounting equation (rows_read = rows_valid + rows_rejected) holds true for all runs.")

    logger.info("\n================ ALL ACCEPTANCE TESTS PASSED! =================\n")


if __name__ == "__main__":
    config = PipelineConfig()
    run_acceptance_tests(config)
