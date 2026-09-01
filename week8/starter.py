from pathlib import Path
import json
import pandas as pd

# กำหนด Path ของไดเรกทอรี data และ output
DATA = Path(__file__).parent / "data"
OUTPUT = Path(__file__).parent / "output"
OUTPUT.mkdir(exist_ok=True)

def run_etl_pipeline():
    # TODO 1: Extract ข้อมูลจาก CSV, Excel และ JSON
    print("--- TODO 1: Extracting Data ---")
    orders_jan = pd.read_csv(DATA / 'orders_2026_01.csv')
    orders_feb = pd.read_csv(DATA / 'orders_2026_02.csv')
    customers_crm = pd.read_csv(DATA / 'customers_crm.csv')
    product_master = pd.read_excel(DATA / 'product_master.xlsx')
    
    with open(DATA / 'payments.json', 'r', encoding='utf-8') as f:
        payments_data = json.load(f)
        
    payments_list = []
    for p in payments_data:
        payments_list.append({
            'payment_id': p.get('payment_id'),
            'order_id': p.get('order_id'),
            'payment_method': p.get('payment', {}).get('method'),
            'payment_status': p.get('payment', {}).get('status'),
            'paid_at': p.get('paid_at')
        })
    df_payments = pd.DataFrame(payments_list)

    # TODO 2: ทำ schema alignment ของไฟล์ orders สองเดือน แล้ว concat
    print("\n--- TODO 2: Schema Alignment & Combining Orders ---")
    orders_feb_aligned = orders_feb.rename(columns={
        'ordered_at': 'order_date',
        'qty': 'quantity',
        'discount_pct': 'discount'
    }).copy()
    
    # แปลงส่วนลดของเดือน ก.พ. จาก string (เช่น '5%') เป็น float decimal (0.05)
    orders_feb_aligned['discount'] = (
        orders_feb_aligned['discount']
        .astype(str)
        .str.rstrip('%')
        .astype(float) / 100.0
    )

    orders_combined = pd.concat([orders_jan, orders_feb_aligned], ignore_index=True)
    total_raw_orders = len(orders_combined)

    # TODO 3: Clean/standardize/deduplicate และสร้าง data quality report
    print("\n--- TODO 3: Cleaning, Standardizing & Deduplicating ---")
    
    # 3.1 Deduplication & Comparisons
    orders_dedup = orders_combined.drop_duplicates(subset=['order_id'], keep='last').copy()
    dedup_orders_count = len(orders_dedup)

    dim_customer = customers_crm.drop_duplicates(subset=['customer_id'], keep='last').copy()
    dim_product = product_master.drop_duplicates(subset=['product_id'], keep='last').copy()
    payments_dedup = df_payments.drop_duplicates(subset=['payment_id'], keep='last').copy()

    # พิมพ์ตารางเปรียบเทียบก่อน-หลัง Deduplicate ทุกไฟล์
    print("\n[ DEDUPLICATION SUMMARY COMPARISON ]")
    print(f"- Orders combined: Before = {len(orders_combined)} | After = {dedup_orders_count} | Removed = {len(orders_combined) - dedup_orders_count}")
    print(f"- Customers CRM:   Before = {len(customers_crm)} | After = {len(dim_customer)} | Removed = {len(customers_crm) - len(dim_customer)}")
    print(f"- Payments Data:   Before = {len(df_payments)} | After = {len(payments_dedup)} | Removed = {len(df_payments) - len(payments_dedup)}")
    print(f"- Product Master:  Before = {len(product_master)} | After = {len(dim_product)} | Removed = {len(product_master) - len(dim_product)}")

    # Range Check Validation
    valid_orders = orders_dedup[
        (orders_dedup['quantity'] > 0) & 
        (orders_dedup['unit_price'] > 0) & 
        (orders_dedup['discount'] >= 0) & 
        (orders_dedup['discount'] <= 1)
    ].copy()

    # Standardize Customers CRM
    dim_customer['email'] = dim_customer['email'].astype(str).str.strip().str.lower()
    dim_customer['province'] = dim_customer['province'].astype(str).str.strip()
    
    province_mapping = {
        'Chonburi': 'ชลบุรี',
        'Bangkok': 'กรุงเทพมหานคร',
        'กทม.': 'กรุงเทพมหานคร',
        'กทม': 'กรุงเทพมหานคร',
        'BKK': 'กรุงเทพมหานคร',
        'Chiang Mai': 'เชียงใหม่',
        'Chiangmai': 'เชียงใหม่',
        'Phuket': 'ภูเก็ต',
        'Khon Kaen': 'ขอนแก่น',
        'Khonkaen': 'ขอนแก่น',
        'ขอนเเก่น': 'ขอนแก่น',
        'Rayong': 'ระยอง',
        'Korat': 'นครราชสีมา',
        'Nakhon Ratchasima': 'นครราชสีมา'
    }
    dim_customer['province'] = dim_customer['province'].replace(province_mapping)

    # Filter PAID payments
    paid_payments = payments_dedup[payments_dedup['payment_status'] == 'PAID'].copy()

    # TODO 4 & TODO 5: Enrich ข้อมูล และ Validate business rules
    print("\n--- TODO 4 & 5: Enriching, Validating & Calculating Sales ---")
    missing_cust_orders = valid_orders[~valid_orders['customer_id'].isin(dim_customer['customer_id'])]
    missing_prod_orders = valid_orders[~valid_orders['product_id'].isin(dim_product['product_id'])]

    orders_matched = valid_orders[
        valid_orders['customer_id'].isin(dim_customer['customer_id']) & 
        valid_orders['product_id'].isin(dim_product['product_id'])
    ].copy()

    fact_sales = orders_matched.merge(
        paid_payments[['order_id', 'payment_id', 'payment_method', 'payment_status', 'paid_at']], 
        on='order_id', 
        how='inner'
    )
    
    fact_sales['net_sales'] = fact_sales['quantity'] * fact_sales['unit_price'] * (1.0 - fact_sales['discount'])

    # TODO 6: Load dim_customer.csv, dim_product.csv และ fact_sales.csv
    print("\n--- TODO 6: Exporting Output Files ---")
    dim_customer.to_csv(OUTPUT / 'dim_customer.csv', index=False, encoding='utf-8-sig')
    dim_product.to_csv(OUTPUT / 'dim_product.csv', index=False, encoding='utf-8-sig')
    fact_sales.to_csv(OUTPUT / 'fact_sales.csv', index=False, encoding='utf-8-sig')

    # Data Quality Report แบบละเอียด
    dq_data = [
        {'step': 'Combine Orders', 'metric': 'Raw Orders Count', 'value': total_raw_orders},
        {'step': 'Deduplication', 'metric': 'Deduplicated Orders Count', 'value': dedup_orders_count},
        {'step': 'Range Check', 'metric': 'Valid Price/Qty/Discount Orders', 'value': len(valid_orders)},
        {'step': 'Referential Integrity', 'metric': 'Unmatched Customer ID', 'value': len(missing_cust_orders)},
        {'step': 'Referential Integrity', 'metric': 'Unmatched Product ID', 'value': len(missing_prod_orders)},
        {'step': 'Payment Validation', 'metric': 'Final PAID & Matched Sales Transactions', 'value': len(fact_sales)}
    ]
    pd.DataFrame(dq_data).to_csv(OUTPUT / 'data_quality_report.csv', index=False, encoding='utf-8-sig')

    # ตารางสรุปคุณภาพข้อมูลรายขั้นตอน (Pipeline Stage Summary Table)
    pipeline_summary_data = [
        {
            'ขั้นตอนกระบวนการ (Pipeline Stage)': '1. Raw Combined Orders',
            'จำนวนแถวที่เหลือ': total_raw_orders,
            'จำนวนแถวที่ถูกคัดออก': '-'
        },
        {
            'ขั้นตอนกระบวนการ (Pipeline Stage)': '2. Deduplication',
            'จำนวนแถวที่เหลือ': dedup_orders_count,
            'จำนวนแถวที่ถูกคัดออก': total_raw_orders - dedup_orders_count
        },
        {
            'ขั้นตอนกระบวนการ (Pipeline Stage)': '3. Range Check',
            'จำนวนแถวที่เหลือ': len(valid_orders),
            'จำนวนแถวที่ถูกคัดออก': dedup_orders_count - len(valid_orders)
        },
        {
            'ขั้นตอนกระบวนการ (Pipeline Stage)': '4. Referential Integrity',
            'จำนวนแถวที่เหลือ': len(orders_matched),
            'จำนวนแถวที่ถูกคัดออก': len(valid_orders) - len(orders_matched)
        },
        {
            'ขั้นตอนกระบวนการ (Pipeline Stage)': '5. Final Integrated Sales',
            'จำนวนแถวที่เหลือ': len(fact_sales),
            'จำนวนแถวที่ถูกคัดออก': len(orders_matched) - len(fact_sales)
        }
    ]
    df_pipeline_summary = pd.DataFrame(pipeline_summary_data)
    df_pipeline_summary.to_csv(OUTPUT / 'data_quality_summary.csv', index=False, encoding='utf-8-sig')

    # TODO 7: สร้าง summary_by_province.csv และ summary_by_category.csv
    print("\n--- TODO 7: Generating Summaries ---")
    df_merged = fact_sales.merge(dim_customer, on='customer_id', how='left').merge(dim_product, on='product_id', how='left')
    
    summary_prov = df_merged.groupby('province')['net_sales'].sum().reset_index().sort_values(by='net_sales', ascending=False)
    summary_prov.to_csv(OUTPUT / 'summary_by_province.csv', index=False, encoding='utf-8-sig')

    summary_cat = df_merged.groupby('category')['net_sales'].sum().reset_index().sort_values(by='net_sales', ascending=False)
    summary_cat.to_csv(OUTPUT / 'summary_by_category.csv', index=False, encoding='utf-8-sig')

    # แสดงผลสรุปคำตอบทั้ง 6 ข้อออกทาง Terminal
    top_province = summary_prov.iloc[0]
    top_category = summary_cat.iloc[0]

    print("\n==========================================================================================")
    print("                           DATA QUALITY PIPELINE STAGE SUMMARY                            ")
    print("==========================================================================================")
    print(df_pipeline_summary.to_string(index=False))
    
    print("\n==========================================================================================")
    print("                                     FINAL RESULTS                                        ")
    print("==========================================================================================")
    print(f"1. จำนวนแถวหลังรวมไฟล์ orders: {total_raw_orders} แถว (มกราคม {len(orders_jan)} แถว + กุมภาพันธ์ {len(orders_feb)} แถว)")
    print(f"   จำนวนแถวหลังลบ Duplicate: {dedup_orders_count} แถว")
    print(f"2. จำนวนแถวที่ไม่พบใน Master Data:")
    print(f"   - customer_id ที่ไม่พบใน CRM Master: {len(missing_cust_orders)} แถว")
    print(f"   - product_id ที่ไม่พบใน Product Master: {len(missing_prod_orders)} แถว")
    print(f"3. จำนวนธุรกรรมที่ใช้ได้จริงและยอดขายสุทธิรวม:")
    print(f"   - จำนวนธุรกรรมที่ใช้ได้จริง: {len(fact_sales)} ธุรกรรม")
    print(f"   - ยอดขายรวม: {fact_sales['net_sales'].sum():,.2f} บาท")
    print(f"4. จังหวัดที่มียอดขายสุทธิสูงสุด:")
    print(f"   - {top_province['province']} มียอดขายสุทธิสูงสุด เป็นจำนวน {top_province['net_sales']:,.2f} บาท")
    print(f"5. หมวดสินค้าที่มียอดขายสุทธิสูงสุด:")
    print(f"   - {top_category['category']} มียอดขายสุทธิสูงสุด เป็นจำนวน {top_category['net_sales']:,.2f} บาท")
    print("6. หากสลับลำดับ merge ก่อน cleaning ผลลัพธ์หรือความเชื่อมั่นของข้อมูลเปลี่ยนอย่างไร?")
    print("   - เกิด Data Explosion : การเชื่อมข้อมูลก่อนลบข้อมูลซ้ำ (Duplicates) ส่งผลให้ตัวเลขยอดขายถูกนับซ้ำ")
    print("   - คำนวณยอดขายผิดพลาด: รายการชำระเงินที่ไม่สำเร็จ (FAILED, CANCELLED), ค่าติดลบ หรือส่วนลดที่ผิดปกติจะถูกดึงเข้ามารวมในรายงานยอดขาย ทำให้นำข้อมูลไปใช้งานไม่ได้")
    print("   - ไม่สามารถตรวจสอบย้อนกลับได้ : ไม่สามารถระบุได้ชัดเจนว่าข้อมูลถูกคัดออกในขั้นตอนใด และทำให้ Data Quality Report ไม่สามารถสะท้อนคุณภาพของข้อมูลดิบได้อย่างแม่นยำ")
    print("==========================================================================================")

if __name__ == '__main__':
    run_etl_pipeline()