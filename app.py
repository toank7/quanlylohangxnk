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
    
    # 3. Tự động nâng cấp cột ha_cont nếu chưa có
    try:
        c.execute("SELECT ha_cont FROM shipments LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE shipments ADD COLUMN ha_cont TEXT")
        
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

def create_shipment(contract_name, cargo_name, booking, vessel, eta, ha_cont):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO shipments (contract_name, cargo_name, booking_no, vessel, eta, ha_cont) VALUES (?, ?, ?, ?, ?, ?)", 
                  (contract_name, cargo_name, booking, vessel, eta, ha_cont))
        
        # Tự động tạo checklist mặc định ban đầu
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
    
    # THAY ĐỔI LỚN: Menu chọn Tên hàng hóa mặc định linh hoạt
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
    new_vessel = st.text_input("Tên Tàu / Số chuyến:")
    
    # Menu chọn Nơi hạ Cont
    cang_options = ["Cát Lái", "SPITC", "Hiệp Phước", "Tân Cảng Hiệp Phước", "Đà Nẵng", "Hải Phòng", "Khác (Nhập tay bên dưới)"]
    selected_cang = st.selectbox("Chọn Cảng hạ Cont:", cang_options)
    custom_cang = st.text_input("Nếu chọn 'Khác', nhập tên cảng vào đây:")
    
    final_ha_cont = custom_cang.strip() if selected_cang == "Khác (Nhập tay bên dưới)" else selected_cang

    new_eta = st.date_input("Ngày dự kiến đến (ETA):", datetime.now())
    submit_btn = st.form_submit_button("Tạo hợp đồng")
    
    if submit_btn:
        if new_contract and final_cargo_name:
            if create_shipment(new_contract, final_cargo_name, new_booking, new_vessel, new_eta.strftime('%Y-%m-%d'), final_ha_cont):
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
    st.subheader("📋 Danh sách hợp đồng đang thực hiện")
    
    conn = sqlite3.connect(DB_NAME)
    display_data = []
    
    for _, row in shipments_df.iterrows():
        ct = row['contract_name']
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
            
        display_data.append({
            "Tên Hợp Đồng": ct,
            "Tên Hàng": row['cargo_name'],
            "Số Booking": row['booking_no'],
            "Tên Tàu": row['vessel'],
            "Nơi Hạ Cont": row['ha_cont'] if ('ha_cont' in row and row['ha_cont']) else "---",
            "Ngày ETA": row['eta'],
            "Tiến độ các Hạng mục": status_string,
            "Trạng thái": "✅ Hoàn tất" if row['is_completed'] == 1 else "⏳ Đang chạy"
        })
    conn.close()
    
    st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)

    # --- PHẦN XỬ LÝ CHI TIẾT VÀ TỰ THÊM MỤC CHÍNH/PHỤ ---
    st.markdown("---")
    st.subheader("🔍 Cập nhật & Tự chỉnh sửa cấu trúc tiến độ")
    
    selected_contract = st.selectbox("Chọn Hợp Đồng cần cập nhật hoặc thêm mục:", shipments_df['contract_name'].tolist())
    
    if selected_
