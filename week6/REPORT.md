# ETL Lab Report

Student ID: 67160213
Name: Natakorn Khawyai

## 1. Data Quality Problems Found

* **Customers Data (`customers.csv`)**:
  * มีข้อมูลซ้ำซ้อนใน `customer_id`
  * ข้อมูลจังหวัด (`province`) สะกดไม่เป็นมาตรฐาน เช่น มีหลายรูปแบบ ("chon buri", "bkk", "กรุงเทพฯ", "จันทบุรี", "RAYONG"), ผสมตัวพิมพ์เล็ก-ใหญ่, และมีค่าเป็นสูญหาย/Null (`NaN`, `None`)
  * มีค่าสูญหาย (`NaN`) ในฟิลด์ `name` และ `email`

* **Products Data (`products.json`)**:
  * ข้อมูลอยู่ในรูปแบบ Nested JSON Structure (`category.name`, `pricing.price`)
  * ข้อมูลราคาบางรายการเป็น String ที่มีเครื่องหมาย Comma (เช่น `"1,299.00"`)
  * มีค่าสูญหาย (`null`) ในฟิลด์ `category.name`

* **Orders Data (`orders.csv`)**:
  * มีข้อมูลซ้ำซ้อนใน `order_id`
  * รูปแบบวันที่ (`order_date`) มีความหลากหลายปะปนกัน (เช่น `YYYY/MM/DD`, `DD/MM/YYYY`, `YYYY-MM-DD`, `DD-Mon-YYYY`) และมีข้อมูลที่ไม่ใช่วันที่ (`not-a-date`)
  * สถานะคำสั่งซื้อ (`status`) ใช้ตัวพิมพ์เล็ก-ใหญ่ไม่เป็นมาตรฐาน (เช่น `"PAID"`, `"paid"`, `"completed"`, `"pending"`, `"cancelled"`)
  * มีข้อมูลตัวเลขผิดปกติ (Invalid Numeric Values): `qty <= 0` (-2), `unit_price <= 0` (-100.0), `discount_pct > 100` (150%)
  * มีคำสั่งซื้อที่อ้างอิงถึง `customer_id` หรือ `product_id` ที่ไม่มีในข้อมูล Master (Foreign Key Integrity Issue)

## 2. Cleaning / Transformation Rules

* **Customers Cleaning**:
  * ลบข้อมูลซ้ำโดยใช้ `customer_id` เป็น Primary Identifier (`drop_duplicates(subset=['customer_id'])`)
  * ปรับมาตรฐานชื่อจังหวัดด้วย `PROVINCE_MAP` ให้เป็นชื่อมาตรฐานภาษาอังกฤษ ("Bangkok", "Chonburi", "Rayong", "Chanthaburi") และเปลี่ยนค่า Null/Missing เป็น `"Unknown"`
  * แทนที่ค่า Null/Missing ใน `name` และ `email` ด้วย `"Unknown"`

* **Products Cleaning**:
  * Flatten Nested JSON ด้วย `pd.json_normalize()` และ Rename คอลัมน์ให้ตรงมาตรฐาน (`category.name` -> `category`, `pricing.price` -> `price`, `product_id`, `product_name`)
  * แปลงคอลัมน์ `price` ให้เป็น Numeric โดยลบเครื่องหมาย Comma ออกก่อน แล้วใช้ `pd.to_numeric(..., errors='coerce')`
  * แทนที่ค่า Missing/Null ใน `category` ด้วย `"Unknown"`
  * ลบข้อมูลซ้ำโดยใช้ `product_id` เป็น Key

* **Orders Cleaning & Filtering**:
  * ลบข้อมูลซ้ำโดยใช้ `order_id` เป็น Key
  * แปลงรูปแบบวันที่ `order_date` ให้เป็นมาตรฐาน ISO DateTime โดยใช้ `pd.to_datetime(..., format="mixed", errors="coerce")`
  * แปลงสถานะ `status` เป็นตัวพิมพ์เล็กทั้งหมด (`lowercase`) และตัดช่องว่างส่วนเกิน
  * กรองคำสั่งซื้อที่ถูกต้อง (Valid Records):
    * `qty > 0`
    * `unit_price > 0`
    * `0 <= discount_pct <= 100`
    * `order_date` ไม่เป็น NaT (วันที่ถูกต้อง)
    * `status` อยู่ในกลุ่ม `['paid', 'completed']`
    * `customer_id` และ `product_id` มีอยู่จริงในข้อมูล Master (`dim_customer` และ `dim_product`)
  * คำนวณยอดขายสุทธิ:
    * `gross_amount = qty * unit_price`
    * `discount_amount = gross_amount * discount_pct / 100.0`
    * `sales_amount = gross_amount - discount_amount`

## 3. Rejected Records

จำนวน: 80 รายการ (จากคำสั่งซื้อทั้งหมด 183 รายการ มี 3 รายการซ้ำซ้อนที่ถูกตัดออก และ 80 รายการที่ไม่ผ่านกฎการตรวจสอบคุณภาพข้อมูลถูกบันทึกลง `output/rejects.csv`)

เหตุผลหลัก:
1. สถานะคำสั่งซื้อไม่ใช่การซื้อขายที่สำเร็จ (`status` ไม่ใช่ `paid` หรือ `completed` เช่น `pending`, `cancelled` จำนวน 77 รายการ)
2. วันที่คำสั่งซื้อไม่ถูกต้อง / ไม่สามารถแปลงเป็นวันที่ได้ (`order_date = 'not-a-date'` จำนวน 1 รายการ)
3. จำนวนสินค้า (`qty`) มีค่าน้อยกว่าหรือเท่ากับ 0 (`qty = -2` จำนวน 1 รายการ)
4. ราคาต่อหน่วย (`unit_price`) มีค่าน้อยกว่าหรือเท่ากับ 0 (`unit_price = -100.0` จำนวน 1 รายการ)
5. ส่วนลด (`discount_pct`) เกิน 100% (`discount_pct = 150%` จำนวน 1 รายการ)
6. อ้างอิง Customer ID หรือ Product ID ที่ไม่มีในฐานข้อมูล Master (อย่างละ 1 รายการ)

## 4. ETL Validation

* Valid transformed rows: 100
* Warehouse rows: 100
* Duplicate order_id: 0
* Source total sales: 192074.66
* Warehouse total sales: 192074.66
* Validation status: PASS

## 5. Idempotency Test

จำนวน fact_sales หลัง run ครั้งที่ 1: 100 records

จำนวน fact_sales หลัง run ครั้งที่ 2: 100 records

อธิบายผล:
Pipeline มีคุณสมบัติ Idempotency (สามารถรันซ้ำกี่ครั้งก็ได้โดยไม่ทำให้เกิดข้อมูลซ้ำซ้อนหรือผลลัพธ์ผิดเพี้ยน) เนื่องจาก:
1. มีการกำหนด Primary Key (`order_id` ใน `fact_sales`, `customer_id` ใน `dim_customer`, `product_id` ใน `dim_product`) ใน SQLite Database Schema
2. ใช้คำสั่ง SQL `INSERT OR REPLACE INTO` ในขั้นตอน Load Data ซึ่งเมื่อรัน ETL ซ้ำ ระบบจะทำการอัปเดตเรคคอร์ดเดิมที่มี Primary Key ตรงกันแทนการแทรกเรคคอร์ดซ้ำ ส่งผลให้จำนวนแถวใน Data Warehouse คงที่อยู่ที่ 100 records เสมอ
