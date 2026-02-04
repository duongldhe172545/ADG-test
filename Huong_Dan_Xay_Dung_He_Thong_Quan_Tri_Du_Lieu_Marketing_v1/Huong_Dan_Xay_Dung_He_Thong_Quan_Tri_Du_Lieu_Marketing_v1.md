**HƯỚNG DẪN XÂY DỰNG**\


**HỆ THỐNG QUẢN TRỊ DỮ LIỆU\
KHỐI MARKETING ADG**\


*Với NotebookLM + OneDrive/Google Drive*

\
Phiên bản 1.0 - Tháng 02/2026


# **MỤC LỤC**
PHẦN 1: TỔNG QUAN HỆ THỐNG

PHẦN 2: CẤU TRÚC FOLDER TRÊN ONEDRIVE/GOOGLE DRIVE

PHẦN 3: CẤU TRÚC NOTEBOOKLM

PHẦN 4: HƯỚNG DẪN TRIỂN KHAI TỪ BƯỚC 1 ĐẾN BƯỚC 100

PHẦN 5: QUY TẮC VẬN HÀNH & BẢO TRÌ

PHỤ LỤC: MẪU METADATA & CHECKLIST


# **PHẦN 1: TỔNG QUAN HỆ THỐNG**
## **1.1. Mục đích**
Xây dựng hệ thống quản trị dữ liệu/tri thức (Data Governance) cho Khối Marketing ADG với 2 mục tiêu chính:

- **Lưu trữ chuẩn hóa:** Tất cả tài liệu marketing được tổ chức khoa học, dễ tìm, có chủ sở hữu rõ ràng, quản lý phiên bản chặt chẽ
- **Hỏi đáp thông minh:** Nhân viên có thể hỏi NotebookLM về bất kỳ thông tin nào liên quan đến công việc và nhận câu trả lời có trích nguồn
## **1.2. Kiến trúc hệ thống 2 lớp**

|**LỚP**|**CÔNG CỤ**|**CHỨC NĂNG CHÍNH**|**AI QUẢN LÝ**|
| :- | :- | :- | :- |
|**LỚP 1<br>Kho gốc chuẩn**|OneDrive hoặc<br>Google Drive|• Lưu trữ file gốc (.docx, .pdf, .pptx, .xlsx...)<br>• Quản lý phân quyền truy cập<br>• Backup tự động<br>• Lịch sử phiên bản|Nhóm Quản trị Data<br>+ Owner nội dung các phòng|
|**LỚP 2<br>Lớp tri thức**|NotebookLM|• Tổ chức notebook theo phòng ban<br>• Hỏi đáp thông minh (AI)<br>• Tạo Golden Answers<br>• Trích dẫn nguồn tự động|Mọi nhân viên Marketing<br>(theo phân quyền)|
## **1.3. Nguyên tắc vàng (Invariants)**
- **KHÔNG metadata → KHÔNG được ACTIVE**
- **KHÔNG nguồn gốc (provenance) → KHÔNG được publish Golden Answer**
- **CẤM đặt tên file kiểu final\_final2 → BẮT BUỘC versioning (v1.0, v1.1...)**
- **CẤM nạp dữ liệu cá nhân (PII) khi chưa có chính sách rõ ràng**
- **Least Privilege: chỉ cấp quyền tối thiểu cần thiết**


# **PHẦN 2: CẤU TRÚC FOLDER TRÊN ONEDRIVE/GOOGLE DRIVE**
## **2.1. Cấu trúc tổng thể**
**Lưu ý quan trọng:** Bạn chỉ cần tạo 1 trong 2 (OneDrive HOẶC Google Drive). Không cần cả 2.

**Cấu trúc ROOT FOLDER:**

ADG\_Marketing\_Data\_Governance/

├── 00\_HUB\_Governance/          → Tài liệu chuẩn chung toàn Khối

├── 01\_Marketing\_D2Com/         → Phòng Marketing D2Com

├── 02\_Marketing\_B2B/           → Phòng Marketing B2B

├── 03\_Marketing\_S2B2C/         → Phòng Marketing S2B2C

├── 04\_MARCOM/                  → Phòng MARCOM

└── 99\_Archive/                 → Lưu trữ tài liệu cũ
## **2.2. Chi tiết folder 00\_HUB\_Governance**
00\_HUB\_Governance/

├── Glossary\_Taxonomy/

│   ├── ADG\_MKT\_Glossary\_v1.0.docx          → Từ điển thuật ngữ

│   ├── ADG\_MKT\_Taxonomy\_v1.0.xlsx          → Hệ phân loại (tag chuẩn)

│   └── Tag\_Rules\_v1.0.pdf                  → Luật gắn tag

├── Metadata\_Schema/

│   ├── Metadata\_Schema\_v1.0.xlsx           → Bảng siêu dữ liệu bắt buộc

│   ├── Metadata\_Form\_Template.docx         → Mẫu form điền metadata

│   └── Content\_Types\_v1.0.xlsx             → Danh mục loại nội dung

├── SOP\_Lifecycle/

│   ├── Document\_Lifecycle\_SOP\_v1.0.pdf     → Quy trình vòng đời tài liệu

│   ├── Versioning\_Rules\_v1.0.pdf           → Quy tắc quản lý phiên bản

│   └── Retention\_Schedule\_v1.0.xlsx        → Lịch lưu giữ/xóa tài liệu

├── Access\_DLP/

│   ├── Access\_Model\_v1.0.xlsx              → Ma trận phân quyền

│   ├── DLP\_Policy\_v1.0.pdf                 → Chính sách chống rò rỉ

│   └── PII\_Checklist\_v1.0.pdf              → Checklist kiểm tra dữ liệu cá nhân

├── Decision\_Log/

│   └── Decision\_Log\_2026.xlsx              → Nhật ký các quyết định quan trọng

└── Golden\_Answers\_Template/

`    `└── Golden\_Answer\_Template\_v1.0.docx    → Mẫu câu trả lời chuẩn


## **2.3. Chi tiết folder 01\_Marketing\_D2Com**
01\_Marketing\_D2Com/

├── House\_ID\_Development/

│   ├── Strategy\_Plan/

│   │   ├── House\_ID\_Strategy\_2026\_v1.0.docx

│   │   ├── OKR\_Q1\_2026\_v1.0.xlsx

│   │   └── Roadmap\_2026-2028\_v1.0.pptx

│   ├── Insight\_Research/

│   │   ├── Customer\_Journey\_Map\_v2.0.pdf

│   │   ├── Behavior\_Analysis\_Q4\_2025\_v1.0.xlsx

│   │   └── Market\_Research\_Report\_Jan2026\_v1.0.pdf

│   ├── Playbook\_SOP/

│   │   ├── House\_ID\_Activation\_Playbook\_v1.0.docx

│   │   ├── SOP\_Lead\_Nurturing\_v1.0.pdf

│   │   └── Checklist\_Campaign\_Launch\_v1.0.xlsx

│   ├── Campaign\_Reports/

│   │   ├── Campaign\_Jan2026\_Performance\_Report\_v1.0.xlsx

│   │   ├── Post\_Mortem\_Campaign\_Tet2026\_v1.0.docx

│   │   └── Test\_Log\_AB\_Test\_Jan2026\_v1.0.xlsx

│   └── Templates\_Briefs/

│       ├── Campaign\_Brief\_Template\_v1.0.docx

│       ├── Creative\_Brief\_Template\_v1.0.pptx

│       └── Reporting\_Template\_v1.0.xlsx

**Lưu ý:** Cấu trúc 5 folder con (Strategy\_Plan, Insight\_Research, Playbook\_SOP, Campaign\_Reports, Templates\_Briefs) được lặp lại cho:

- • Community\_Activation
- • Product\_Marketing\_Home
- • Product\_Marketing\_Solar


## **2.4. Các phòng còn lại**
02\_Marketing\_B2B có 4 sub-folders:

- • OEM\_Export\_Marketing
- • Industrial\_Solution\_Marketing
- • Key\_Account\_Marketing
- • Solar\_EPC\_Solution\_Marketing

\
03\_Marketing\_S2B2C có 2 sub-folders:

- • Research\_Marketing\_Operation
- • Product\_Marketing\_Door

\
04\_MARCOM có 6 sub-folders:

- • Brand\_CX\_Communication
- • Corporate\_Brand\_Copywriter
- • Event\_Communication\_Copywriter
- • Trade\_Marketing
- • 3D\_Graphic\_Designer
- • Performance\_Marketing

\
**Mỗi sub-folder đều có cấu trúc 5 folder con giống như House\_ID\_Development**


# **PHẦN 3: CẤU TRÚC NOTEBOOKLM**
## **3.1. Tổng quan NotebookLM**
**NotebookLM là gì?** Công cụ AI của Google giúp tổ chức kiến thức từ nhiều nguồn (PDF, DOCX, website...) và trả lời câu hỏi có trích dẫn nguồn.

**Cách hoạt động:**

1. Bạn upload tài liệu vào NotebookLM (hoặc link đến Google Drive)
1. NotebookLM đọc và hiểu nội dung tài liệu
1. Nhân viên hỏi câu hỏi bằng ngôn ngữ tự nhiên
1. NotebookLM trả lời KÈM THEO trích dẫn từ tài liệu gốc
## **3.2. Cấu trúc Notebook**
NotebookLM Structure:

📁 ADG\_Marketing\_SSOT\_Hub (HUB chính)

`   `├── Sources: Link đến folder 00\_HUB\_Governance trên Drive

`   `├── Notes: Index tổng hợp, Decision Log

`   `└── Q&A: FAQs về quy trình, governance

📘 Marketing D2Com (4 notebooks)

`   `├── 📗 House\_ID\_Development

`   `├── 📗 Community\_Activation

`   `├── 📗 Product\_Marketing\_Home

`   `└── 📗 Product\_Marketing\_Solar

📘 Marketing B2B (4 notebooks)

`   `├── 📗 OEM\_Export\_Marketing

`   `├── 📗 Industrial\_Solution\_Marketing

`   `├── 📗 Key\_Account\_Marketing

`   `└── 📗 Solar\_EPC\_Solution\_Marketing

📘 Marketing S2B2C (2 notebooks)

`   `├── 📗 Research\_Marketing\_Operation

`   `└── 📗 Product\_Marketing\_Door

📘 MARCOM (6 notebooks)

`   `├── 📗 Brand\_CX\_Communication

`   `├── 📗 Corporate\_Brand\_Copywriter

`   `├── 📗 Event\_Communication\_Copywriter

`   `├── 📗 Trade\_Marketing

`   `├── 📗 3D\_Graphic\_Designer

`   `└── 📗 Performance\_Marketing


## **3.3. Quy tắc tạo Golden Answers**
**Golden Answer** là câu trả lời chuẩn đã được duyệt, có trích nguồn rõ ràng và được gắn nhãn độ tin cậy.

**Cấu trúc Golden Answer bắt buộc:**

|**THÀNH PHẦN**|**MÔ TẢ**|
| :- | :- |
|**Question (Câu hỏi)**|Câu hỏi mà nhân viên thường hỏi|
|**Answer (Câu trả lời)**|Câu trả lời ngắn gọn, rõ ràng (2-3 đoạn)|
|**Citations (Trích nguồn)**|Link đến tài liệu gốc + trang/section cụ thể|
|**Confidence Label**|VERIFIED / ASSUMPTION / OUTDATED-RISK|
|**Owner**|Người chịu trách nhiệm nội dung|
|**Review Date**|Ngày cần rà soát lại|

\
**Yêu cầu tối thiểu:**

- **Mỗi notebook phải có tối thiểu 20 Golden Answers**
- Mỗi Golden Answer phải được Owner phòng duyệt trước khi publish
- Rà soát lại mỗi 6 tháng hoặc khi có thay đổi lớn


# **PHẦN 4: HƯỚNG DẪN TRIỂN KHAI TỪ BƯỚC 1 ĐẾN BƯỚC 100**
**QUAN TRỌNG: Thực hiện CHÍNH XÁC theo thứ tự từ bước 1 → 100. Không được bỏ qua bất kỳ bước nào.**
## **GIAI ĐOẠN 1: CHUẨN BỊ (Bước 1-5)**
1. Bước 1: Tạo Google Drive hoặc OneDrive cho dự án (chọn 1 trong 2)
1. Bước 2: Tạo root folder: ADG\_Marketing\_Data\_Governance
1. Bước 3: Tạo 6 folder chính theo cấu trúc Phần 2.1
1. Bước 4: Mời Nhóm Quản trị Data vào làm Editor
1. Bước 5: Mời Owner nội dung các phòng vào với quyền Contributor

**📋 Checklist Giai đoạn 1:**

- ☐ Đã tạo root folder và phân quyền đúng
- ☐ Tất cả Owner đã có quyền truy cập
- ☐ Đã test upload 1 file thử để kiểm tra quyền
## **GIAI ĐOẠN 2: XÂY DỰNG HUB GOVERNANCE (Bước 6-50)**
1. Bước 6-15: Tạo folder 00\_HUB\_Governance với đầy đủ sub-folders (xem Phần 2.2)
1. Bước 16-25: Tạo file ADG\_MKT\_Glossary\_v1.0.docx và ADG\_MKT\_Taxonomy\_v1.0.xlsx
1. Bước 26-35: Tạo Metadata\_Schema\_v1.0.xlsx với các trường BẮT BUỘC
1. Bước 36-45: Tạo Document\_Lifecycle\_SOP, Versioning\_Rules, Retention\_Schedule
1. Bước 46-50: Tạo Access\_Model, DLP\_Policy, PII\_Checklist, Decision\_Log

**📋 Checklist Giai đoạn 2:**

- ☐ Tất cả 15+ file trong 00\_HUB\_Governance đã tạo xong
- ☐ Mỗi file đã được Owner phòng review và approve
## **GIAI ĐOẠN 3: XÂY DỰNG CẤU TRÚC 4 PHÒNG (Bước 51-70)**
1. Bước 51-58: Tạo folder 01\_Marketing\_D2Com với 4 sub-folders
1. Bước 59-62: Tạo folder 02\_Marketing\_B2B với 4 sub-folders
1. Bước 63-66: Tạo folder 03\_Marketing\_S2B2C với 2 sub-folders
1. Bước 67-68: Tạo folder 04\_MARCOM với 6 sub-folders
1. Bước 69-70: Tạo folder 99\_Archive và thiết lập auto-archiving
## **GIAI ĐOẠN 4: MIGRATION (Bước 71-85)**
1. Bước 71-75: Thu thập Top 50 tài liệu quan trọng nhất từ mỗi phòng
1. Bước 76-78: DEDUP - Khử trùng lặp và chuẩn hóa tên file
1. Bước 79-81: Điền metadata cho tất cả tài liệu
1. Bước 82-83: Gắn tag và xác định trạng thái (ACTIVE/DEPRECATED/ARCHIVED)
1. Bước 84-85: Upload file và tạo INDEX.xlsx cho mỗi sub-folder

**📋 Checklist Giai đoạn 4:**

- ☐ 200+ tài liệu đã được migrate với đầy đủ metadata
- ☐ Mỗi sub-folder có file INDEX.xlsx
- ☐ Owner đã ký confirm
## **GIAI ĐOẠN 5: THIẾT LẬP NOTEBOOKLM (Bước 86-100)**
1. Bước 86-90: Truy cập notebooklm.google.com và tạo HUB chính
1. Bước 91-95: Link HUB đến folder 00\_HUB\_Governance và tạo 5 Golden Answers đầu tiên
1. Bước 96-100: Tạo 16 Notebook con, mỗi notebook tối thiểu 20 Golden Answers

**📋 Checklist Giai đoạn 5:**

- ☐ 1 HUB + 16 Notebooks đã tạo xong
- ☐ Tổng cộng 320+ Golden Answers (20 x 16)
- ☐ Test: Hỏi 10 câu random, NotebookLM trả lời đúng với citations


# **PHẦN 5: QUY TẮC VẬN HÀNH & BẢO TRÌ**
## **5.1. Quy trình upload tài liệu mới**
1\. Kiểm tra PII: Dùng PII\_Checklist, đảm bảo không có dữ liệu cá nhân

2\. Chuẩn hóa tên file: [ContentType]\_[Subject]\_[Date]\_[Version].[ext]

3\. Điền metadata: Dùng Metadata\_Form\_Template, điền đủ 9 trường bắt buộc

4\. Gắn tag: Tối thiểu 2 tags theo Taxonomy

5\. Set trạng thái: DRAFT → chờ Owner duyệt → ACTIVE

6\. Upload vào đúng folder theo cấu trúc Phần 2

7\. Cập nhật INDEX.xlsx: Thêm 1 dòng mới với thông tin file

8\. NotebookLM tự động sync: Không cần làm gì thêm
## **5.2. Quy trình cập nhật tài liệu**
1\. KHÔNG chỉnh sửa trực tiếp file gốc: Tạo bản copy mới

2\. Tăng version: v1.0 → v1.1 (thay đổi nhỏ) hoặc v2.0 (thay đổi lớn)

3\. Cập nhật Change Log: Ghi rõ ngày, người sửa, nội dung thay đổi

4\. Upload bản mới: Cùng folder với bản cũ

5\. Set bản cũ thành DEPRECATED: Đổi tên thêm \_DEPRECATED

6\. Cập nhật Golden Answers nếu cần
## **5.3. Lịch vận hành định kỳ**

|**TẦN SUẤT**|**CÔNG VIỆC**|**NGƯỜI THỰC HIỆN**|
| :- | :- | :- |
|**Hàng tuần**|• Dọn rác: xóa file duplicate<br>• Kiểm tra file DRAFT quá 1 tuần|Nhóm Quản trị Data|
|**Hàng tháng**|• Cập nhật Taxonomy<br>• Review Golden Answers|Nhóm Quản trị Data + Owner|
|**Hàng quý**|• Audit toàn bộ<br>• Báo cáo KPI lên CMO|Nhóm Quản trị Data|
|**Hàng năm**|• Đánh giá lại cấu trúc<br>• Archive tài liệu > 2 năm|CMO + Nhóm Quản trị Data|
## **5.4. KPI theo dõi**

|**KPI**|**MỤC TIÊU**|**CÁCH ĐO**|
| :- | :- | :- |
|**Time-to-Find**|≤ 5 phút|Thời gian tìm được tài liệu đúng|
|**Metadata Coverage**|≥ 95%|% tài liệu ACTIVE có đủ metadata|
|**DLP Incidents**|= 0|Số sự cố rò rỉ PII|
|**Golden Answers Quality**|≥ 20/notebook|Số lượng GA có đủ citations + label|
|**User Adoption**|≥ 80%|% nhân viên dùng NotebookLM ≥1 lần/tuần|
|**Review On-time**|≥ 90%|% tài liệu được review đúng hạn|


# **PHỤ LỤC: MẪU METADATA & CHECKLIST**
## **A. PII Checklist (10 câu hỏi)**
1. 1. File có chứa họ tên đầy đủ của khách hàng/nhân viên?
1. 2. File có chứa email cá nhân (không phải email công ty)?
1. 3. File có chứa số điện thoại cá nhân?
1. 4. File có chứa địa chỉ nhà riêng?
1. 5. File có chứa số CMND/CCCD/Passport?
1. 6. File có chứa thông tin tài chính cá nhân?
1. 7. File có chứa ảnh chân dung người?
1. 8. File có chứa dữ liệu nhạy cảm về sức khỏe?
1. 9. File có chứa thông tin hợp đồng có tên ký?
1. 10. File có chứa dữ liệu khác có thể định danh cá nhân?

\
**Nếu trả lời CÓ bất kỳ câu nào → DỪNG. Không upload. Liên hệ Legal/Compliance.**


# **KẾT LUẬN**
Bằng cách làm theo đúng 100 bước trong tài liệu này, bạn sẽ có:

- **✅ Kho tài liệu chuẩn hóa** trên OneDrive/Google Drive với cấu trúc rõ ràng, phân quyền chặt chẽ
- **✅ Hệ thống NotebookLM** với 1 HUB + 16 Notebooks, 320+ Golden Answers sẵn sàng phục vụ nhân viên
- **✅ Quy trình vận hành** rõ ràng cho upload, update, review tài liệu
- **✅ KPI đo lường** hiệu quả hệ thống

\
**LƯU Ý QUAN TRỌNG:**

- **• Thời gian triển khai: 14 ngày (2 tuần)**
- **• Yêu cầu nhân sự: Nhóm Quản trị Data (2-3 người) + Owner nội dung 4 phòng (4 người)**
- **• Chi phí: $0 (NotebookLM free, OneDrive/GDrive đã có)**

\
**--- HẾT ---**

*Nếu có thắc mắc, liên hệ Nhóm Quản trị Data hoặc CMO*
