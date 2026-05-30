import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- CẤU HÌNH CƠ SỞ DỮ LIỆU ---
DB_NAME = "logistic_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Bảng lưu thông tin chung hợp đồng
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
    # Bảng lưu trạng thái các bước check-list
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
    conn.commit()
    conn.close()

def get_active_shipments():
    conn = sqlite3.connect(DB_NAME)
    # Lấy các hợp đồng chưa hoàn thành HOẶC đã hoàn thành nhưng chưa quá 3 ngày
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    query = f"""
        SELECT * FROM shipments 
        WHERE is_completed = 0 
        OR (is_completed = 1 AND completed_date >= '{three_days_ago}')
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def create_shipment(contract_name, cargo_name, booking, vessel, eta):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO shipments (contract_name, cargo_name, booking_no, vessel, eta) VALUES (?, ?, ?, ?, ?)", 
                  (contract_name, cargo_name, booking, vessel, eta))
        
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
    new_name = st.text_input("Tên hàng hóa *:")
    new_booking = st.text_input("Số Booking / B/L (Nếu có):")
    new_vessel = st.text_input("Tên Tàu / Số chuyến:")
    new_eta = st.date_input("Ngày dự kiến đến (ETA):", datetime.now())
    submit_btn = st.form_submit_button("Tạo hợp đồng")
    
    if submit_btn:
        if new_contract and new_name:
            if create_shipment(new_contract, new_name, new_booking, new_vessel, new_eta.strftime('%Y-%m-%d')):
                st.sidebar.success(f"Đã thêm hợp đồng: {new_contract}")
                st.rerun()
            else:
                st.sidebar.error("Tên Hợp Đồng này đã tồn tại trên hệ thống!")
        else:
            st.sidebar.error("Vui lòng nhập Tên hợp đồng và Tên hàng!")

# --- MÀN HÌNH CHÍNH ---
shipments_df = get_active_shipments()

if shipments_df.empty:
    st.info("Hiện tại không có hợp đồng nào đang xử lý.")
else:
    st.subheader("📋 Danh sách hợp đồng đang thực hiện")
    
    conn = sqlite3.connect(DB_NAME)
    display_data = []
    
    for _, row in shipments_df.iterrows():
        ct = row['contract_name']
        categories = ["Kiểm dịch thực vật", "Làm SI VGM", "Certificate of Origin (C/O)", "Gửi chứng từ"]
        status_colors = {}
        
        for cat in categories:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tasks WHERE contract_name = ? AND category = ? AND is_done = 0", (ct, cat))
            not_done_count = c.fetchone()[0]
            status_colors[cat] = "🟢 Xong" if not_done_count == 0 else "🔴 Chưa xong"
            
        display_data.append({
            "Tên Hợp Đồng": ct,
            "Tên Hàng": row['cargo_name'],
            "Số Booking": row['booking_no'],
            "Tên Tàu": row['vessel'],
            "Ngày ETA": row['eta'],
            "Kiểm Dịch": status_colors["Kiểm dịch thực vật"],
            "SI VGM": status_colors["Làm SI VGM"],
            "C/O": status_colors["Certificate of Origin (C/O)"],
            "Chứng Từ": status_colors["Gửi chứng từ"],
            "Trạng thái": "✅ Hoàn tất" if row['is_completed'] == 1 else "⏳ Đang chạy"
        })
    conn.close()
    
    st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)

    # --- PHẦN XỬ LÝ CHI TIẾT VÀ TỰ THÊM MỤC ---
    st.markdown("---")
    st.subheader("🔍 Cập nhật & Tự thêm bước tiến độ")
    
    selected_contract = st.selectbox("Chọn Hợp Đồng cần cập nhật hoặc thêm mục:", shipments_df['contract_name'].tolist())
    
    if selected_contract:
        shipment_info = shipments_df[shipments_df['contract_name'] == selected_contract].iloc[0]
        st.markdown(f"Đang xem: **{selected_contract}** ({shipment_info['cargo_name']}) | Tàu: **{shipment_info['vessel']}** | ETA: **{shipment_info['eta']}**")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        categories = ["Kiểm dịch thực vật", "Làm SI VGM", "Certificate of Origin (C/O)", "Gửi chứng từ"]
        
        # Form chính quản lý checklist
        with st.form("checklist_form"):
            all_checkboxes = {}
            
            for cat in categories:
                with st.expander(f"📁 Hạng mục: {cat}"):
                    # Lấy danh sách các task hiện tại (gồm cả các task tự thêm sau này)
                    c.execute("SELECT id, task_name, is_done FROM tasks WHERE contract_name = ? AND category = ?", (selected_contract, cat))
                    tasks = c.fetchall()
                    
                    if tasks:
                        for task_id, task_name, is_done in tasks:
                            all_checkboxes[task_id] = st.checkbox(task_name, value=bool(is_done), key=f"task_{task_id}")
                    else:
                        st.write("*Chưa có bước nào trong mục này.*")
                        
            save_changes = st.form_submit_button("💾 Lưu cập nhật tiến độ")
            
            if save_changes:
                for t_id, checked in
