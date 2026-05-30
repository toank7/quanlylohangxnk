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
        "bill_no": "TEXT",
        "port_of_discharge": "TEXT"
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

def create_shipment(contract_name, cargo_name, booking, vessel, eta, ha_cont, contract_date, customs_no, bill_no, pod):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO shipments 
            (contract_name, cargo_name, booking_no, vessel, eta, ha_cont, contract_date, customs_declaration_no, bill_no, port_of_discharge) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (contract_name, cargo_name, booking, vessel, eta, ha_cont, contract_date, customs_no, bill_no, pod))
        
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

# Hàm cập nhật tất cả thông tin cốt lõi của hợp đồng cũ
def update_full_shipment(old_contract_name, new_contract_name, contract_date, cargo_name, booking, vessel, eta, ha_cont, customs_no, bill_no, pod):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Nếu đổi tên hợp đồng, cần cập nhật bảng liên kết trước do ràng buộc Foreign Key
    if old_contract_name != new_contract_name:
        c.execute("UPDATE tasks SET contract_name = ? WHERE contract_name = ?", (new_contract_name, old_contract_name))
        
    c.execute("""
        UPDATE shipments 
        SET contract_name = ?, contract_date = ?, cargo_name = ?, booking_no = ?, 
            vessel = ?, eta = ?, ha_cont = ?, customs_declaration_no = ?, bill_no = ?, port_of_discharge = ?
        WHERE contract_name = ?
    """, (new_contract_name, contract_date, cargo_name, booking, vessel, eta, ha_cont, customs_no, bill_no, pod, old_contract_name))
    conn.commit()
    conn.close()

def add_custom_task(contract_name, category, task_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (contract_name, category, task_name, is_done) VALUES (?, ?, ?, 0)",
              (contract_name, category, task_name))
    conn.commit()
    conn.close()

# Hàm xóa toàn bộ một hạng mục lớn
def delete_category(contract_name, category):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE contract_name = ? AND category = ?", (contract_name, category))
    conn.commit()
    conn.close()

# Hàm xóa một bước công việc nhỏ
def delete_task_by_id(task_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
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
    
    hang_options = ["Gạo (Rice)", "Nông sản (Agricultural Products)", "Bún khô / Phở khô", "Hạt điều (Cashew)", "Hạt tiêu (Pepper)", "Thủy hải sản (Seafood)", "Gỗ & Sản phẩm từ gỗ", "Hàng may mặc (Garment)", "Khác (Nhập tay bên dưới)"]
    selected_cargo = st.selectbox("Chọn Tên hàng hóa *:", hang_options)
    custom_cargo = st.text_input("Nếu chọn 'Khác', nhập tên hàng hóa vào đây:")
    final_cargo_name = custom_cargo.strip() if selected_cargo == "Khác (Nhập tay bên dưới)" else selected_cargo

    new_booking = st.text_input("Số Booking / B/L (Nếu có):")
    new_bill_no = st.text_input("Số Bill (Vận đơn):")
    new_customs_no = st.text_input("Số Tờ Khai Hải Quan:")
    new_vessel = st.text_input("Tên Tàu / Số chuyến:")
    
    cang_options = ["Cát Lái", "SPITC", "Hiệp Phước", "Tân Cảng Hiệp Phước", "Đà Nẵng", "Hải Phòng", "Khác (Nhập tay bên dưới)"]
    selected_cang = st.selectbox("Chọn Cảng hạ Cont:", cang_options)
    custom_cang = st.text_input("Nếu chọn 'Khác' cảng hạ, nhập vào đây:")
    final_ha_cont = custom_cang.strip() if selected_cang == "Khác (Nhập tay bên dưới)" else selected_cang

    dest_options = ["KWANGYANG", "ULSAN", "INCHEON", "Khác (Nhập tay bên dưới)"]
    selected_dest = st.selectbox("Chọn Cảng Đích (POD):", dest_options)
    custom_dest = st.text_input("Nếu chọn 'Khác' cảng đích, nhập vào đây:")
    final_pod = custom_dest.strip() if selected_dest == "Khác (Nhập tay bên dưới)" else selected_dest

    new_eta = st.date_input("Ngày dự kiến đến (ETA):", datetime.now())
    submit_btn = st.form_submit_button("Tạo hợp đồng")
    
    if submit_btn:
        if new_contract and final_cargo_name:
            if create_shipment(new_contract, final_cargo_name, new_booking, new_vessel, new_eta.strftime('%Y-%m-%d'), final_ha_cont, new_contract_date.strftime('%Y-%m-%d'), new_customs_no, new_bill_no, final_pod):
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
                if c.fetchone()[0] > 0:
                    status_list.append(f"{cat}: 🔴")
                else:
                    status_list.append(f"{cat}: 🟢")
            status_string = " | ".join(status_list)
            
            display_data.append({
                "Tên Hợp Đồng": ct,
                "Ngày Hợp Đồng": row['contract_date'] if ('contract_date' in row and row['contract_date']) else "---",
                "Cảng Đích (POD)": row['port_of_discharge'] if ('port_of_discharge' in row and row['port_of_discharge']) else "---",
                "Số Tờ Khai HQ": row['customs_declaration_no'] if ('customs_declaration_no' in row and row['customs_declaration_no']) else "---",
                "Số Bill (B/L)": row['bill_no'] if ('bill_no' in row and row['bill_no']) else "---",
                "Tên Hàng": row['cargo_name'] if 'cargo_name' in row else "---",
                "Tên Tàu": row['vessel'] if 'vessel' in row else "---",
                "Nơi Hạ Cont": row['ha_cont'] if ('ha_cont' in row and row['ha_cont']) else "---",
                "Ngày ETA": row['eta'] if 'eta' in row else "---",
                "Tiến độ các Hạng mục": status_string,
                "Trạng thái": "✅ Hoàn tất" if row['is_completed'] == 1 else "⏳ Đang chạy"
            })
    conn.close()
    
    if display_data:
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)

    # --- PHẦN XỬ LÝ CHI TIẾT & SỬA / XÓA ---
    st.markdown("---")
    st.subheader("🔍 Quản Lý Chi Tiết, Chỉnh Sửa & Xóa Cấu Trúc")
    
    if 'contract_name' in shipments_df.columns and not shipments_df.empty:
        contract_list = [r for r in shipments_df['contract_name'].tolist() if r]
        selected_contract = st.selectbox("Chọn Hợp Đồng cần xử lý:", contract_list)
        
        if selected_contract:
            shipment_info = shipments_df[shipments_df['contract_name'] == selected_contract].iloc[0]
            
            # TÁCH LÀM 2 TAB: TAB 1 ĐỂ SỬA THÔNG TIN LÔ HÀNG, TAB 2 ĐỂ QUẢN LÝ TIẾN ĐỘ VÀ XÓA MỤC
            tab_info, tab_checklist, tab_structure = st.tabs(["✏️ Chỉnh sửa thông tin hợp đồng cũ", "✅ Cập nhật tiến độ công việc", "🛠️ Thêm / Xóa Hạng mục công việc"])
            
            # --- TAB 1: SỬA HỢP ĐỒNG CŨ ---
            with tab_info:
                st.write("📝 **Thay đổi bất kỳ thông tin nào của hợp đồng này:**")
                with st.form("edit_full_shipment_form"):
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        edit_name = st.text_input("Tên/Số Hợp Đồng:", value=shipment_info['contract_name'])
                        try:
                            curr_c_date = datetime.strptime(shipment_info['contract_date'], '%Y-%m-%d')
                        except:
                            curr_c_date = datetime.now()
                        edit_c_date = st.date_input("Ngày Hợp Đồng:", value=curr_c_date)
                        edit_cargo = st.text_input("Tên hàng hóa:", value=shipment_info['cargo_name'])
                        edit_booking = st.text_input("Số Booking:", value=shipment_info['booking_no'] if shipment_info['booking_no'] else "")
                        edit_vessel = st.text_input("Tên tàu / Số chuyến:", value=shipment_info['vessel'] if shipment_info['vessel'] else "")
                    with col_e2:
                        edit_bill = st.text_input("Số Bill (B/L):", value=shipment_info['bill_no'] if shipment_info['bill_no'] else "")
                        edit_cust = st.text_input("Số Tờ Khai Hải Quan:", value=shipment_info['customs_declaration_no'] if shipment_info['customs_declaration_no'] else "")
                        edit_ha_cont = st.text_input("Nơi hạ Cont:", value=shipment_info['ha_cont'] if shipment_info['ha_cont'] else "")
                        edit_pod = st.text_input("Cảng Đích (POD):", value=shipment_info['port_of_discharge'] if shipment_info['port_of_discharge'] else "")
                        try:
                            curr_eta = datetime.strptime(shipment_info['eta'], '%Y-%m-%d')
                        except:
                            curr_eta = datetime.now()
                        edit_eta = st.date_input("Ngày dự kiến đến (ETA):", value=curr_eta)
                        
                    btn_save_full = st.form_submit_button("💾 Xác nhận lưu thay đổi thông tin hợp đồng")
                    if btn_save_full:
                        update_full_shipment(selected_contract, edit_name.strip(), edit_c_date.strftime('%Y-%m-%d'), edit_cargo.strip(), edit_booking.strip(), edit_vessel.strip(), edit_eta.strftime('%Y-%m-%d'), edit_ha_cont.strip(), edit_cust.strip(), edit_bill.strip(), edit_pod.strip())
                        st.success("Đã lưu toàn bộ thay đổi thông tin thành công!")
                        st.rerun()

            # --- TAB 2: CẬP NHẬT TIẾN ĐỘ VÀ XÓA BƯỚC NHỎ ---
            with tab_checklist:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                categories = get_categories_for_contract(selected_contract)
                
                st.write("📌 Tích chọn công việc đã hoàn thành:")
                with st.form("checklist_progress_form"):
                    all_checkboxes = {}
                    for cat in categories:
                        with st.expander(f"📁 Hạng mục lớn: {cat}"):
                            c.execute("SELECT id, task_name, is_done FROM tasks WHERE contract_name = ? AND category = ?", (selected_contract, cat))
                            tasks = c.fetchall()
                            if tasks:
                                for task_id, task_name, is_done in tasks:
                                    all_checkboxes[task_id] = st.checkbox(task_name, value=bool(is_done), key=f"p_task_{task_id}")
                            else:
                                st.write("*Chưa có bước thực hiện nào.*")
                    save_progress = st.form_submit_button("💾 Lưu tiến độ công việc")
                    if save_progress:
                        for t_id, checked in all_checkboxes.items():
                            c.execute("UPDATE tasks SET is_done = ? WHERE id = ?", (1 if checked else 0, t_id))
                        c.execute("SELECT COUNT(*) FROM tasks WHERE contract_name = ? AND is_done = 0", (selected_contract,))
                        if c.fetchone()[0] == 0 and len(all_checkboxes) > 0:
                            c.execute("UPDATE shipments SET is_completed = 1, completed_date = ? WHERE contract_name = ?", (datetime.now().strftime('%Y-%m-%d'), selected_contract))
                        else:
                            c.execute("UPDATE shipments SET is_completed = 0, completed_date = NULL WHERE contract_name = ?", (selected_contract,))
                        conn.commit()
                        st.success("Đã lưu tiến độ mới!")
                        st.rerun()
                conn.close()

            # --- TAB 3: THÊM / XÓA HẠNG MỤC HOẶC BƯỚC NHỎ ---
            with tab_structure:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                categories = get_categories_for_contract(selected_contract)
                
                st.write("### 🗂️ Quản lý danh sách Hạng mục lớn")
                for cat in categories:
                    col_cat1, col_cat2 = st.columns([5, 1])
                    with col_cat1:
                        st.markdown(f"📂 **Hạng mục:** `{cat}`")
                    with col_cat2:
                        # Nút xóa hạng mục lớn
                        if st.button(f"🗑️ Xóa Mục", key=f"del_cat_{cat}"):
                            delete_category(selected_contract, cat)
                            st.success(f"Đã xóa toàn bộ hạng mục: {cat}")
                            st.rerun()
                            
                    # Quản lý xóa bước nhỏ bên trong hạng mục này
                    c.execute("SELECT id, task_name FROM tasks WHERE contract_name = ? AND category = ?", (selected_contract, cat))
                    sub_tasks = c.fetchall()
                    for t_id, t_name in sub_tasks:
                        col_t1, col_t2 = st.columns([6, 1])
                        with col_t1:
                            st.write(f"└─ 📌 {t_name}")
                        with col_t2:
                            if st.button("❌ Xóa bước", key=f"del_sub_{t_id}"):
                                delete_task_by_id(t_id)
                                st.success("Đã xóa bước công việc!")
                                st.rerun()
                    st.write("---")
                
                st.write("### ➕ Thêm mới hạng mục hoặc bước nhỏ")
                sub_tab1, sub_tab2 = st.tabs(["Bước nhỏ mới", "Hạng mục lớn mới"])
                with sub_tab1:
                    target_cat = st.selectbox("Chọn hạng mục lớn:", categories, key="st_target_cat")
                    new_task_name = st.text_input("Tên công việc cần thêm:", key="st_new_task")
                    if st.button("Xác nhận thêm bước nhỏ"):
                        if new_task_name.strip():
                            add_custom_task(selected_contract, target_cat, new_task_name.strip())
                            st.success("Thêm bước nhỏ thành công!")
                            st.rerun()
                with sub_tab2:
                    new_main_cat = st.text_input("Tên Hạng mục lớn mới:", key="st_new_cat")
                    first_task = st.text_input("Bước công việc đầu tiên:", value="Bắt đầu triển khai", key="st_first_task")
                    if st.button("Xác nhận tạo hạng mục lớn"):
                        if new_main_cat.strip() and first_task.strip():
                            add_custom_task(selected_contract, new_main_cat.strip(), first_task.strip())
                            st.success("Tạo hạng mục lớn mới thành open thành công!")
                            st.rerun()
                conn.close()
