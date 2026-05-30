import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- CẤU HÌNH CƠ SỞ DỮ LIỆU ---
DB_NAME = "logistic_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Bảng lưu thông tin chung lô hàng
    c.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cargo_name TEXT,
            booking_no TEXT UNIQUE,
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
            booking_no TEXT,
            category TEXT,
            task_name TEXT,
            is_done INTEGER DEFAULT 0,
            FOREIGN KEY(booking_no) REFERENCES shipments(booking_no) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

def get_active_shipments():
    conn = sqlite3.connect(DB_NAME)
    # Lấy các lô chưa hoàn thành HOẶC đã hoàn thành nhưng chưa quá 3 ngày
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    query = f"""
        SELECT * FROM shipments 
        WHERE is_completed = 0 
        OR (is_completed = 1 AND completed_date >= '{three_days_ago}')
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def create_shipment(name, booking, vessel, eta):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO shipments (cargo_name, booking_no, vessel, eta) VALUES (?, ?, ?, ?)", 
                  (name, booking, vessel, eta))
        
        # Tự động tạo checklist chuẩn cho lô hàng mới
        default_tasks = {
            "Kiểm dịch thực vật": ["Đăng ký KDTV", "Đi kiểm", "Làm chứng thư nháp", "Đã có chứng thư", "Đã lấy chứng thư"],
            "Làm SI VGM": ["Gửi thông tin SI", "Xác nhận SI nháp", "Cân VGM", "Submit VGM lên hãng tàu"],
            "Certificate of Origin (C/O)": ["Chuẩn bị hồ sơ", "Khai báo VĐ/Ecosys", "Xét duyệt nháp", "Đã cấp C/O", "Đi lấy C/O"],
            "Gửi chứng từ": ["Thu thập đủ bộ gốc", "Scan lưu hệ thống", "Gửi DHL/FedEx cho khách", "Khách xác nhận đã nhận"]
        }
        
        for category, task_list in default_tasks.items():
            for task in task_list:
                c.execute("INSERT INTO tasks (booking_no, category, task_name, is_done) VALUES (?, ?, ?, 0)",
                          (booking, category, task))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# --- KHỞI TẠO ỨNG DỤNG ---
init_db()
st.set_page_config(page_title="Logistics Checklist", layout="wide")
st.title("🚢 Quản Lý Tiến Độ Lô Hàng Xuất Nhập Khẩu")

# --- SIDEBAR: THÊM LÔ HÀNG MỚI ---
st.sidebar.header("➕ Thêm Lô Hàng Mới")
with st.sidebar.form("new_shipment_form", clear_on_submit=True):
    new_name = st.text_input("Tên hàng hóa:")
    new_booking = st.text_input("Số Booking / B/L:")
    new_vessel = st.text_input("Tên Tàu / Số chuyến:")
    new_eta = st.date_input("Ngày dự kiến đến (ETA):", datetime.now())
    submit_btn = st.form_submit_button("Tạo lô hàng")
    
    if submit_btn:
        if new_name and new_booking:
            if create_shipment(new_name, new_booking, new_vessel, new_eta.strftime('%Y-%m-%d')):
                st.sidebar.success(f"Đã thêm lô hàng: {new_booking}")
                st.rerun()
            else:
                st.sidebar.error("Số Booking này đã tồn tại!")
        else:
            st.sidebar.error("Vui lòng nhập Tên hàng và Số Booking!")

# --- MÀN HÌNH CHÍNH ---
shipments_df = get_active_shipments()

if shipments_df.empty:
    st.info("Hiện tại không có lô hàng nào đang xử lý.")
else:
    st.subheader("📋 Danh sách lô hàng đang thực hiện")
    
    # Chuẩn bị dữ liệu hiển thị trạng thái tổng quan dạng Màu sắc
    conn = sqlite3.connect(DB_NAME)
    display_data = []
    
    for _, row in shipments_df.iterrows():
        bk = row['booking_no']
        
        # Lấy trạng thái tổng quát từng hạng mục lớn
        categories = ["Kiểm dịch thực vật", "Làm SI VGM", "Certificate of Origin (C/O)", "Gửi chứng từ"]
        status_colors = {}
        
        for cat in categories:
            # Kiểm tra xem trong hạng mục này có bước nào chưa xong (is_done = 0) không
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tasks WHERE booking_no = ? AND category = ? AND is_done = 0", (bk, cat))
            not_done_count = c.fetchone()[0]
            
            # Nếu không còn bước nào chưa xong -> XANH, còn lại -> ĐỎ
            status_colors[cat] = "🟢 Xong" if not_done_count == 0 else "🔴 Chưa xong"
            
        display_data.append({
            "Tên Hàng": row['cargo_name'],
            "Số Booking": bk,
            "Tên Tàu": row['vessel'],
            "Ngày ETA": row['eta'],
            "Kiểm Dịch": status_colors["Kiểm dịch thực vật"],
            "SI VGM": status_colors["Làm SI VGM"],
            "C/O": status_colors["Certificate of Origin (C/O)"],
            "Chứng Từ": status_colors["Gửi chứng từ"],
            "Trạng thái chung": "✅ Hoàn tất" if row['is_completed'] == 1 else "⏳ Đang chạy"
        })
    conn.close()
    
    # Hiển thị bảng tổng quan ra màn hình chính
    st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)

    # --- PHẦN XỬ LÝ CHI TIẾT TỪNG LÔ HÀNG ---
    st.markdown("---")
    st.subheader("🔍 Cập nhật tiến độ chi tiết từng lô")
    
    selected_booking = st.selectbox("Chọn Số Booking để cập nhật tiến độ:", shipments_df['booking_no'].tolist())
    
    if selected_booking:
        # Lấy thông tin lô hàng được chọn
        shipment_info = shipments_df[shipments_df['booking_no'] == selected_booking].iloc[0]
        st.markdown(f"Đang xem chi tiết lô: **{shipment_info['cargo_name']}** | Tàu: **{shipment_info['vessel']}** | ETA: **{shipment_info['eta']}**")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Hiển thị các Hạng mục dạng Expander (Bấm vào sẽ mở ra)
        categories = ["Kiểm dịch thực vật", "Làm SI VGM", "Certificate of Origin (C/O)", "Gửi chứng từ"]
        
        # Dùng form để lưu tất cả thay đổi một lần khi bấm nút
        with st.form("checklist_form"):
            all_checkboxes = {}
            
            for cat in categories:
                with st.expander(f"📁 Hạng mục: {cat}"):
                    # Lấy các task nhỏ thuộc category này
                    c.execute("SELECT id, task_name, is_done FROM tasks WHERE booking_no = ? AND category = ?", (selected_booking, cat))
                    tasks = c.fetchall()
                    
                    for task_id, task_name, is_done in tasks:
                        # Tạo checkbox cho từng task nhỏ
                        all_checkboxes[task_id] = st.checkbox(task_name, value=bool(is_done), key=f"task_{task_id}")
            
            # Nút lưu cập nhật
            save_changes = st.form_submit_button("💾 Lưu cập nhật tiến độ")
            
            if save_changes:
                # 1. Cập nhật trạng thái từng task nhỏ vào DB
                for t_id, checked in all_checkboxes.items():
                    c.execute("UPDATE tasks SET is_done = ? WHERE id = ?", (1 if checked else 0, t_id))
                
                # 2. Kiểm tra xem toàn bộ tất cả các task của lô hàng này đã Xong hết chưa
                c.execute("SELECT COUNT(*) FROM tasks WHERE booking_no = ? AND is_done = 0", (selected_booking,))
                remaining_tasks = c.fetchone()[0]
                
                if remaining_tasks == 0:
                    # Nếu đã hoàn thành hết sạch các bước -> Đánh dấu Hoàn tất hợp đồng
                    if shipment_info['is_completed'] == 0: # Nếu trước đó chưa hoàn tất
                        today = datetime.now().strftime('%Y-%m-%d')
                        c.execute("UPDATE shipments SET is_completed = 1, completed_date = ? WHERE booking_no = ?", (today, selected_booking))
                        st.success("🎉 Xuất sắc! Bạn đã hoàn thành toàn bộ quy trình của lô hàng này. Hợp đồng này sẽ tự động ẩn sau 3 ngày.")
                else:
                    # Nếu có tích bỏ chọn bước nào đó -> Trở lại trạng thái đang chạy
                    c.execute("UPDATE shipments SET is_completed = 0, completed_date = NULL WHERE booking_no = ?", (selected_booking,))
                    st.success("🔄 Đã cập nhật tiến độ thành công!")
                
                conn.commit()
                conn.close()
                st.rerun()
        conn.close()
