1. วิธีติดตั้ง (Prerequisites & Installation)
สิ่งที่ต้องเตรียมก่อนติดตั้ง
Python: เวอร์ชัน 3.9 ขึ้นไป  Standard Libraries: sqlite3, dataclasses, logging, datetime, json  Third-party Packages: pandas, openpyxl, numpy  

ขั้นตอนการติดตั้งเปิด Terminal แล้วรัน pip install pandas openpyxl numpy 

2. วิธีรันโปรแกรม
การรันผ่าน python pipeline.py


### 3.ออกแบบ Star Schema
ฐานข้อมูล retail_dw.db ถูกออกแบบและแปลงให้อยู่ในรูปแบบ Star Schema เพื่อประสิทธิภาพในการ Query

                    +-------------------+
                    |   dim_customer    |
                    +-------------------+
                    | PK customer_key   |
                    |    customer_id    |
                    |    customer_name  |
                    |    province       |
                    |    segment        |
                    +---------+---------+
                              | 1
                              |
                              | N
+------------------+ 1      N +-------------------+ N      1 +------------------+
|     dim_date     +----------+    fact_sales     +----------+   dim_product    |
+------------------+          +-------------------+          +------------------+
| PK date_key      |          | PK order_id       |          | PK product_key   |
|    full_date     |          | FK date_key       |          |    product_id    |
|    day, month    |          | FK customer_key   |          |    product_name  |
|    quarter, year |          | FK product_key    |          |    category      |
+------------------+          |    quantity       |          |    unit_price    |
                              |    unit_price     |          |    active_flag   |
                              |    discount_pct   |          +------------------+
                              |    gross_amount   |
                              |    net_amount     |
                              |    payment_method |
                              |    sales_channel  |
                              |    updated_at     |
                              |    source_batch   |
                              +-------------------+

รายละเอียด Grain ของแต่ละตาราง:
fact_sales (Fact Table): มี Grain คือ 1 รายการขายสินค้าที่ผ่านการตรวจสอบ ต่อ 1 order_id

dim_customer (Dimension Table): ข้อมูลลูกค้า 1 แถว ต่อ 1 customer_id (Surrogate Key: customer_key)

dim_product (Dimension Table): ข้อมูลสินค้า 1 แถว ต่อ 1 product_id (Surrogate Key: product_key)

dim_date (Dimension Table): ข้อมูลปฏิทิน 1 แถว ต่อ 1 วัน (Primary Key: date_key รูปแบบ YYYYMMDD)

4. คำตอบ Reflection: Availability vs. Strictness (ความยาว 5-8 บรรทัด)ในระบบ Data Engineering ระดับ Production ความพร้อมใช้งานของข้อมูล (Availability) มักสำคัญกว่าความเข้มงวดเบ็ดเสร็จ (Strictness) เนื่องจากข้อมูลต้นทางจริงมักมีความไม่แน่นอน หากกำหนดให้ Pipeline หยุดทำงานทันที (Pipeline Failure) เพียงเพราะพบข้อมูลผิดพลาดเพียงไม่กี่แถว จะส่งผลให้รายงานและ Dashboard ปลายทางทั้งหมดหยุดชะงักเกิด Down time ทั้งระบบ  การนำเทคนิค Quarantine Pattern ร่วมกับ Idempotent Loading มาใช้ ช่วยให้ข้อมูลส่วนใหญ่ที่ถูกต้องสามารถไหลเข้า Data Warehouse ไปให้ธุรกิจใช้งานได้ทันที ในขณะที่ข้อมูลที่มีปัญหาก็ถูกแยกออกไปพร้อมระบุสาเหตุอย่างชัดเจน วิธีนี้ทำให้สามารถรักษาเสถียรภาพ ความต่อเนื่องของระบบข้อมูล และมาตรฐาน Data Quality ไปพร้อมกันได้อย่างมีประสิทธิภาพ
