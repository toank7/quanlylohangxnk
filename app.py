import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

# --- CẤU HÌNH CƠ SỞ DỮ LIỆU ---
DB_NAME = "logistic_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. Tạo bảng shipments nếu chưa có
    c.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_name TEXT UNIQUE,
            cargo_name TEXT,
            booking_no TEXT,
            vessel TEXT,
            eta DATE,
            is_completed INTEGER DEFAULT 0,
            completed_date DATE
        )
    ''')
    
    # 2. Tạo bảng tasks nếu chưa có
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_name TEXT,
            category TEXT,
            task_name TEXT,
            is_done INTEGER DEFAULT 0,
            FOREIGN KEY(contract_name) REFERENCES shipments(contract_name) ON DELETE CASCADE
        )
    ''')
    
    # 3. TỰ ĐỘNG ĐỒNG BỘ NÂNG CẤP CẤU TRÚC ĐỂ THÊM CÁC CỘT THÔNG TIN MỚI
    columns_to_add = {
        "ha_cont": "TEXT",
        "contract_date": "DATE",
        "customs_declaration_no": "TEXT",
        "bill_no": "TEXT"
    }
    
    for col_name, col_type in columns_to_add.items():
        try:
            c.execute(f"SELECT {col_name} FROM shipments LIMIT 1")
        except sqlite3.OperationalError:
            c.execute(f"ALTER TABLE shipments ADD COLUMN {col_name} {col_type}")
            
    conn.commit()
    conn.close()

def get_active_shipments():
    conn = sqlite3.connect(DB_NAME)
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    query = f"""
        SELECT * FROM shipments 
        WHERE is_completed = 0 
        OR (is_completed = 1 AND completed_date >= '{three_days_ago}')
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_categories_for_contract(contract_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM tasks WHERE contract_name = ?", (contract_name,))
    cats = [r[0] for r in c.fetchall()]
    conn.close()
    
    default_cats = ["Kiểm dịch thực vật", "Làm SI VGM", "Certificate of Origin (C/O)", "Gửi chứng từ"]
    for dc in default_cats:
        if dc not in cats:
            cats.append(dc)
    return cats

def create_shipment(contract_name, cargo_name, booking, vessel, eta, ha_cont, contract_date, customs_no, bill_no):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO shipments 
            (contract_name, cargo_name, booking_no, vessel, eta, ha_cont, contract_date, customs_declaration_no, bill_no) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (contract_name, cargo_name, booking, vessel, eta, ha_cont, contract_date, customs_no, bill_no))
        
        # Tạo quy trình tiến độ mặc định
        default_tasks = {
            "Kiểm dịch thực vật": ["Đăng ký KDTV", "Đi kiểm", "Làm chứng thư nháp", "Đã có chứng thư", "Đã lấy chứng thư"],
            "Làm SI VGM": ["Gửi thông tin SI", "Xác nhận SI nháp", "Cân VGM", "Submit VGM lên hãng tàu"],
            "Certificate of Origin (C/O)": ["Chuẩn bị hồ sơ", "Khai báo VĐ/Ecosys", "Xét duyệt nháp", "Đã cấp C/O", "Đi lấy C/O"],
            "Gửi chứng từ": ["Thu thập đủ bộ gốc", "Scan lưu hệ thống", "Gửi DHL/FedEx cho khách", "Khách xác nhận đã nhận"]
        }
        
        for category, task_list in default_tasks.items():
            for task in task_list:
                c.execute("INSERT INTO tasks (contract_name, category, task_name, is_done) VALUES (?, ?, ?, 0)",
                          (contract_name, category, task))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_shipment_details(contract_name, customs_no, bill_no):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        UPDATE shipments 
        SET customs_declaration_no = ?, bill_no = ? 
        WHERE contract_name = ?
    """, (customs_no, bill_no, contract_name))
    conn.commit()
    conn.close()

def add_custom_task(contract_name, category, task_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (contract_name, category, task_name, is_done) VALUES (?, ?, ?, 0)",
              (contract_name, category, task_name))
    conn.commit()
    conn.close()

# --- KHỞI TẠO ỨNG DỤNG ---
init_db()
st.set_page_config(page_title="Logistics Checklist", layout="wide")
st.title("🚢 Quản Lý Tiến Độ Theo Hợp Đồng Xuất Nhập Khẩu")

# --- SIDEBAR: THÊM HỢP ĐỒNG MỚI ---
st.sidebar.header("➕ Thêm Hợp Đồng Mới")
with st.sidebar.form("new_shipment_form", clear_on_submit=True):
    new_contract = st.text_input("Tên/Số Hợp Đồng *:")
    new_contract_date = st.date_input("Ngày Hợp Đồng:", datetime.now())
    
    # Chọn Tên hàng hóa linh hoạt
    hang_options = [
        "Gạo (Rice)", 
        "Nông sản (Agricultural Products)", 
        "Bún khô / Phở khô", 
        "Hạt điều (Cashew)", 
        "Hạt tiêu (Pepper)",
        "Thủy hải sản (Seafood)",
        "Gỗ & Sản phẩm từ gỗ",
        "Hàng may mặc (Garment)",
        "Khác (Nhập tay bên dưới)"
    ]
    selected_cargo = st.selectbox("Chọn Tên hàng hóa *:", hang_options)
    custom_cargo = st.text_input("Nếu chọn 'Khác', nhập tên hàng hóa vào đây:")
    final_cargo_name = custom_cargo.strip() if selected_cargo == "Khác (Nhập tay bên dưới)" else selected_cargo

    new_booking = st.text_input("Số Booking / B/L (Nếu có):")
    new_bill_no = st.text_input("Số Bill (Vận đơn):")
    new_customs_no = st.text_input("Số Tờ Khai Hải Quan:")
    new_vessel = st.text_input("Tên Tàu / Số chuyến:")
    
    # Chọn Nơi hạ Cont linh hoạt
    cang_options = ["Cát Lái", "SPITC", "Hiệp Phước", "Tân Cảng Hiệp Phước", "Đà Nẵng", "Hải Phòng", "Khác (Nhập tay bên dưới)"]
    selected_cang = st.selectbox("Chọn Cảng hạ Cont:", cang_options)
    custom_cang = st.text_input("Nếu chọn 'Khác', nhập tên cảng vào đây:")
    final_ha_cont = custom_cang.strip() if selected_cang == "Khác (Nhập tay bên dưới)" else selected_cang

    new_eta = st.date_input("Ngày dự kiến đến (ETA):", datetime.now())
    submit_btn = st.form_submit_button("Tạo hợp đồng")
    
    if submit_btn:
        if new_contract and final_cargo_name:
            if create_shipment(
                new_contract, final_cargo_name, new_booking, new_vessel, 
                new_eta.strftime('%Y-%m-%d'), final_ha_cont, 
                new_contract_date.strftime('%Y-%m-%d'), new_customs_no, new_bill_no
            ):
                st.sidebar.success(f"Đã thêm hợp đồng: {new_contract}")
                st.rerun()
            else:
                st.sidebar.error("Tên Hợp Đồng này đã tồn tại trên hệ thống!")
        else:
            st.sidebar.error("Vui lòng nhập Tên hợp đồng và Tên hàng hóa!")

# --- MÀN HÌNH CHÍNH ---
shipments_df = get_active_shipments()

if shipments_df.empty:
    st.info("Hiện tại không có hợp đồng nào đang xử lý. Bạn hãy thêm hợp đồng mới ở thanh bên trái nhé!")
else:
    st.subheader("📋 Bảng Tổng Hợp Dữ Liệu & Tiến Độ Các Lô Hàng")
    
    conn = sqlite3.connect(DB_NAME)
    display_data = []
    
    if 'contract_name' in shipments_df.columns:
        for _, row in shipments_df.iterrows():
            ct = row['contract_name'] if row['contract_name'] else f"Chưa rõ ({row['id']})"
            categories = get_categories_for_contract(ct)
            status_list = []
            
            for cat in categories:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM tasks WHERE contract_name = ? AND category = ? AND is_done = 0", (ct, cat))
                not_done_count = c.fetchone()[0]
                if not_done_count > 0:
                    status_list.append(f"{cat}: 🔴")
                else:
                    status_list.append(f"{cat}: 🟢")
                    
            status_string = " | ".join(status_list)
            
            # Đọc các trường dữ liệu bổ sung an toàn
            c_date = row['contract_date'] if ('contract_date' in row and row['contract_date']) else "---"
            cust_no = row['customs_declaration_no'] if ('customs_declaration_no' in row and row['customs_declaration_no']) else "---"
            b_no = row['bill_no'] if ('bill_no' in row and row['bill_no']) else "---"
            
            row_data = {
                "Tên Hợp Đồng": ct,
                "Ngày Hợp Đồng": c_date,
                "Số Tờ Khai HQ": cust_no,
                "Số Bill (B/L)": b_no,
                "Tên Hàng": row['cargo_name'] if 'cargo_name' in row else "---",
                "Tên Tàu": row['vessel'] if 'vessel' in row else "---",
                "Nơi Hạ Cont": row['ha_cont'] if ('ha_cont' in row and row['ha_cont']) else "---",
                "Ngày ETA": row['eta'] if 'eta' in row else "---",
                "Tiến độ các Hạng mục": status_string,
                "Trạng thái": "✅ Hoàn tất" if row['is_completed'] == 1 else "⏳ Đang chạy"
            }
            display_data.append(row_data)
    
    conn.close()
    
    if display_data:
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
    else:
        st.warning("Vui lòng thêm một hợp đồng mới để đồng bộ và hiển thị dữ liệu!")

    # --- PHẦN XỬ LÝ CHI TIẾT VÀ TỰ THÊM MỤC CHÍNH/PHỤ ---
    st.markdown("---")
    st.subheader("🔍 Cập Nhật Tiến Độ & Thông Tin Chi Tiết Lô Hàng")
    
    if 'contract_name' in shipments_df.columns and not shipments_df.empty:
        contract_list = [r for r in shipments_df['contract_name'].tolist() if r]
        selected_contract = st.selectbox("Chọn Hợp Đồng cần xử lý:", contract_list)
        
        if selected_contract:
            shipment_info = shipments_df[shipments_df['contract_name'] == selected_contract].iloc[0]
            info_ha_cont = shipment_info['ha_cont'] if ('ha_cont' in shipment_info and shipment_info['ha_cont']) else "---"
            info_c_date = shipment_info['contract_date'] if ('contract_date' in shipment_info and shipment_info['contract_date']) else "---"
            
            st.markdown(f"Đang xử lý: Hợp đồng **{selected_contract}** (Ngày: {info_c_date}) | Hàng: **{shipment_info['cargo_name']}** | Nơi Hạ Cont: **{info_ha_cont}**")
            
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            # PHẦN MỚI: Cho phép cập nhật trực tiếp Số tờ khai và Số bill bất cứ lúc nào
            st.write("✏️ **Cập nhật thông tin mã định danh lô hàng:**")
            curr_cust_no = shipment_info['customs_declaration_no'] if ('customs_declaration_no' in shipment_info and shipment_info['customs_declaration_no']) else ""
            curr_bill_no = shipment_info['bill_no'] if ('bill_no' in shipment_info and shipment_info['bill_no']) else ""
            
            col_b1, col_b2, col_b3 = st.columns([2, 2, 1])
            with col_b1:
                input_bill_no = st.text_input("Nhập/Sửa Số Bill (B/L):", value=curr_bill_no, key="edit_bill_no")
            with col_b2:
                input_cust_no = st.text_input("Nhập/Sửa Số Tờ Khai Hải Quan:", value=curr_cust_no, key="edit_cust_no")
            with col_b3:
                st.write("##")
                btn_update_codes = st.button("💾 Lưu mã lô hàng")
                
            if btn_update_codes:
                update_shipment_details(selected_contract, input_cust_no.strip(), input_bill_no.strip())
                st.success("Đã cập nhật Số Bill và Số Tờ khai mới lên bảng tổng hợp!")
                st.rerun()
                
            st.write("---")
            categories = get_categories_for_contract(selected_contract)
            
            # Form quản lý checklist
            with st.form("checklist_form"):
                all_checkboxes = {}
                
                for cat in categories:
                    with st.expander(f"📁 Hạng mục lớn: {cat}"):
                        c.execute("SELECT id, task_name, is_done FROM tasks WHERE contract_name = ? AND category = ?", (selected_contract, cat))
                        tasks = c.fetchall()
                        
                        if tasks:
                            for task_id, task_name, is_done in tasks:
                                all_checkboxes[task_id] = st.checkbox(task_name, value=bool(is_done), key=f"task_{task_id}")
                        else:
                            st.write("*Hạng mục này chưa có bước thực hiện nào.*")
                            
                save_changes = st.form_submit_button("💾 Lưu cập nhật tiến độ công việc")
                
                if save_changes:
                    for t_id, checked in all_checkboxes.items():
                        c.execute("UPDATE tasks SET is_done = ? WHERE id = ?", (1 if checked else 0, t_id))
                    
                    c.execute("SELECT COUNT(*) FROM tasks WHERE contract_name = ? AND is_done = 0", (selected_contract,))
                    remaining_tasks = c.fetchone()[0]
                    
                    if remaining_tasks == 0 and len(all_checkboxes) > 0:
                        if shipment_info['is_completed'] == 0:
                            today = datetime.now().strftime('%Y-%m-%d')
                            c.execute("UPDATE shipments SET is_completed = 1, completed_date = ? WHERE contract_name = ?", (today, selected_contract))
                            st.success("🎉 Xuất sắc! Hợp đồng này đã hoàn tất toàn bộ quy trình.")
                    else:
                        c.execute("UPDATE shipments SET is_completed = 0, completed_date = NULL WHERE contract_name = ?", (selected_contract,))
                        st.success("🔄 Đã cập nhật trạng thái tiến độ thành công!")
                    
                    conn.commit()
                    st.rerun()

            # Khu vực thêm hạng mục linh hoạt
            st.write("🛠️ **Khu vực quản lý bổ sung mục (Dành riêng cho hợp đồng này):**")
            tab1, tab2 = st.tabs(["➕ Thêm Bước nhỏ (vào mục có sẵn)", "🗂️ Thêm Hạng mục LỚN hoàn toàn mới"])
            
            with tab1:
                col1, col2 = st.columns([2, 1])
                with col1:
                    target_cat = st.selectbox("Chọn hạng mục lớn muốn thêm bước:", categories, key="target_cat")
                    new_task_name = st.text_input("Tên bước cần thêm (Ví dụ: Đã nộp lệ phí...):", key="new_task_name")
                with col2:
                    st.write("##")
                    add_task_btn = st.button("Thêm bước nhỏ", key="add_task_btn")
                    
                if add_task_btn and new_task_name.strip():
                    add_custom_task(selected_contract, target_cat, new_task_name.strip())
                    st.success(f"Đã thêm bước nhỏ thành công!")
                    st.rerun()
                    
            with tab2:
                col1, col2 = st.columns([2, 1])
                with col1:
                    new_main_cat = st.text_input("Nhập tên Hạng Mục Lớn mới (Ví dụ: Khai hải quan...):", key="new_main_cat")
                    first_task = st.text_input("Tạo bước công việc đầu tiên cho mục này:", value="Bắt đầu triển khai", key="first_task")
                with col2:
                    st.write("##")
                    st.write("##")
                    add_cat_btn = st.button("Tạo Hạng Mục Lớn", key="add_cat_btn")
                    
                if add_cat_btn and new_main_cat.strip() and first_task.strip():
                    add_custom_task(selected_contract, new_main_cat.strip(), first_task.strip())
                    st.success(f"Đã tạo thành công Hạng mục lớn mới!")
                    st.rerun()
                    
            conn.close()
