# รายงานแลป OLTP OLAP และ Pivot

ชื่อ: ณฐกร ขาวใหญ่ รหัส: 67160213  กลุ่ม: 2
## 1 OLTP
![OLTP Run](Screenshot 2026-09-15 130549.png)

## 2 Grain และ Star Schema
![Grain และ Star Schema](Untitled diagram-2026-09-15-061014.png)

1. 1 แถวใน `fact_sales` หมายถึง รายการสินค้า 1 บรรทัด (Line item) ภายใน 1 ออเดอร์ (เช่น ออเดอร์ O1001 ที่มีสินค้าหลายชนิดจะมีหลายแถว)
2. PK: `dim_date.date_key`, `dim_product.product_key`, `dim_store.store_key`, `fact_sales.(order_id, line_no)`
3. FK: `fact_sales.date_key`, `fact_sales.product_key`, `fact_sales.store_key`
4. 3 Dimensions: เวลา (dim_date), สินค้า (dim_product), สถานที่ (dim_store)
5. 2 Measures: quantity, amount (หรือ unit_price)
6. Hierarchy เวลา: date_key -> month -> year | สถานที่: store_name -> province -> region
7. unit_price ไม่ควรนำมาบวกเพราะเป็น Non-additive การบวกราคาสินค้าแต่ละชนิดเข้าด้วยกันไม่สะท้อนยอดขายที่แท้จริง
8. ผล q01: จำนวนรายการ 8, จำนวนออเดอร์ 6, จำนวนชิ้น 23, ยอดขายรวม 1390 บาท

## 3 OLAP
**ผลรัน q02-q07 และ q12:**
```text
(q02)
month	revenue
2026-08	490
2026-09	900

(q03)
month	province	revenue
2026-08	Bangkok	310
2026-08	Chonburi	180
2026-09	Bangkok	540
2026-09	Chonburi	360

(q04)
full_date	revenue
2026-09-09	360
2026-09-10	300
2026-09-11	240

(q05)
province	revenue
Bangkok	540
Chonburi	360

(q06)
province	category	revenue
Bangkok	Drink	300
Chonburi	Drink	200

(q07)
province	revenue
Bangkok	540

(q12)
order_id	line_no	product_name	quantity	amount
O1005	1	Tea	6	300
O1006	1	Cookie	3	240
```
**คำอธิบาย Operation และ WHERE/HAVING:**
- ก. q03 เป็นการเจาะจงมิติสถานที่เพิ่มทำให้ผลลัพธ์กระจายออก (Drill-down ข้ามมิติ/Roll-up แยกกลุ่ม) ส่วน q04 เจาะลึกระดับเวลา (Drill-down) จากรายเดือนเป็นรายวัน 
- ข. q07 ต้องกรองเดือนใน WHERE (ระดับแถว) และกรองยอด 400 ใน HAVING (หลัง aggregate)
- ค. รายการ q12 เมื่อรวมยอด amount จะเท่ากับบรรทัด Bangkok, 2026-09 ใน q03 (540 บาท)

## 4 Pivot
**ผลรัน q08 และการอธิบายผล Assert ก่อนหลังแก้ mean:**
```text
(q08 SQL Pivot)
province	aug	sep	total
Bangkok	310	540	850
Chonburi	180	360	540

(P1 Pivot Province-Month - pandas sum)
month      2026-08  2026-09  Total
province                          
Bangkok        310      540    850
Chonburi       180      360    540
Total          490      900   1390

(P2 Pivot September - Drink Category sum)
province  Bangkok  Chonburi
category                   
Drink         300       200
Food          240       160
```
- ผลการแก้ `aggfunc` ในโค้ด: ตอนลบ `aggfunc` ออก pandas จะใช้ค่าเริ่มต้นคือ `mean` ทำให้ได้ยอดของ Bangkok เดือน 9 เป็น 270 (540 / 2 รายการ) แต่เมื่อแก้กลับมาใส่ `aggfunc='sum'` จะได้ผลลัพธ์ 540 ตรงตามข้อมูลจริง
- `assert pivot_p1.loc['Total', 'Total'] == df['amount'].sum()`: ส่งค่ากลับมาเป็น True (ผ่านโดยไม่มี Error) เนื่องจาก 1390 บาทตรงกันพอดี
- ข้อแตกต่างของ sum กับ mean: sum คือยอดรวมรายได้ทั้งหมด (Revenue) แต่ mean คือค่าเฉลี่ยต่อรายการสินค้า (Average per line item)
- หากเพิ่มเดือนตุลาคม: SQL ต้องเพิ่ม CASE ใหม่เอง แต่ pandas (columns="month") จะแสดงคอลัมน์ใหม่ให้โดยอัตโนมัติ

## 5 ตรวจความถูกต้อง
**ผลรัน q09-q11:**
```text
(q09)
month	revenue
2026-08	490
2026-09	900
ALL	1390

(q10)
revenue	orders	aov	avg_line
1390	6	231.67	173.75

(q11)
stage	row_count	total_amount
Before JOIN (fact)	8	1390
After JOIN (sales)	8	1390
```
**คำอธิบาย:**
- ผล q09: การนำผลรายเดือนมา UNION ALL กับ ALL ทำให้เกิดการนับยอดซ้ำซ้อน (Double counting) ยอดรวมจะกลายเป็น 2 เท่าของความจริง
- AOV เทียบกับ AVG: AOV (231.67 บาท/ออเดอร์) สะท้อนมูลค่าต่อการซื้อ 1 บิลของลูกค้า ส่วน AVG(amount) (173.75 บาท/รายการ) สะท้อนมูลค่าต่อ 1 บรรทัดสินค้า
- ผล q11 ก่อนและหลัง JOIN ได้ 8 แถว ยอดรวม 1390 เท่ากัน หากมี PK ซ้ำใน Dimension จะทำให้ผล JOIN เกิด Cartesian Product แถวและยอดรวมจะเพิ่มขึ้น หาก FK ใน Fact ไม่มีใน Dimension ผล JOIN จะถูกตัดออกและยอดรวมหายไป
- Additive: ยอดขาย (amount) นำมาบวกกันได้ทุกมิติ
- Semi-additive: สต็อกสิ้นวัน บวกข้ามสถานที่ได้ แต่บวกข้ามเวลาไม่ได้
- Non-additive: AOV หรืออุณหภูมิ บวกกันไม่ได้ ต้องคำนวณจากยอดตั้งต้นใหม่ (SUM(amount)/COUNT(DISTINCT order_id))

## 6 สรุป
- ข้อค้นพบ 1: pandas สะดวกกว่า SQL ในการทำ Pivot เมื่อมิติมีจำนวนสมาชิกเพิ่มหรือเปลี่ยนไป เนื่องจากสามารถสร้างคอลัมน์ใหม่ได้แบบอัตโนมัติ
- ข้อค้นพบ 2: AOV เป็น Measure แบบ Non-additive ไม่สามารถหาค่าเฉลี่ยของค่าเฉลี่ยรายเดือนมาบวกกันตรงๆ ได้ ต้องใช้ยอดรวมสุทธิมาหารด้วยออเดอร์สุทธิ
- ข้อจำกัด: การอัปเดตสถานะในระบบ OLTP (เช่น `oltp_demo.py`) จะไม่ส่งผลไปยัง Data Warehouse (เช่น `warehouse.db`) ทันที ระบบจำเป็นต้องมีกระบวนการ ETL ในการดึงข้อมูลไปอัปเดต
- การใช้ AI: นำ AI (Google Gemini) มาประยุกต์ใช้เป็นผู้ช่วยวิเคราะห์ลำดับขั้นตอนการทำงาน และตรวจสอบไวยากรณ์โค้ดเบื้องต้น เพื่อเสริมประสิทธิภาพในการเรียนรู้
  - Prompt สำคัญ: "ให้ทำอะไร" (เพื่อให้ AI ช่วยสกัดประเด็นและสร้างโครงร่างจากโจทย์ที่กำหนด) และ "ขอวิธีรันพร้อมใส่เนื้อหา" (เพื่อขอคำแนะนำในการนำผลลัพธ์จาก Terminal มาจัดรูปแบบลงเอกสารรายงานอย่างเป็นระเบียบ)
  - จุดที่ตรวจแก้ด้วยตนเอง: ได้ทำการรันสคริปต์และจัดเตรียมภาพหน้าจอผลลัพธ์ระบบ OLTP ด้วยตนเอง รวมทั้งเป็น ออกแบบ/วาดแผนภาพ Star Schema และได้ตรวจสอบ/ปรับปรุงความถูกต้องของเนื้อหาในเอกสารรายงานขั้นสุดท้าย