import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk

# ====================================================
# [의존성 라이브러리 검사]
# 사용자가 패키지를 설치하지 않고 실행했을 때 친절하게 안내합니다.
# ====================================================
try:
    import chardet
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError as e:
    import tkinter.messagebox as messagebox
    root = tk.Tk()
    root.withdraw()
    missing_pkg = e.name if hasattr(e, 'name') else str(e)
    messagebox.showerror(
        "의존성 라이브러리 미설치",
        f"필수 라이브러리({missing_pkg})가 설치되어 있지 않습니다.\n\n"
        "같은 디렉토리에 있는 'install_dependencies.bat' 파일을 실행하여 "
        "필요한 라이브러리를 먼저 설치한 후 다시 실행해 주세요."
    )
    sys.exit(1)

# ====================================================
# [설정 및 전역 변수]
# ====================================================
TARGET_DIR = r"C:\정승찬\노래 월드컵"
os.makedirs(TARGET_DIR, exist_ok=True)  # 대상 폴더가 없으면 자동 생성

# 스레드 간 안전한 통신을 위한 FIFO 큐
event_queue = queue.Queue()

# 인덱싱 데이터 구조
file_index = {}
index_lock = threading.Lock()  # 멀티스레드 환경에서 dict 읽기/쓰기 충돌 방지용 락

# GUI 참조 변수
root = None
search_var = None
results_text = None
status_label = None
displayed_results = []  # 현재 화면에 출력된 검색 결과 매핑 목록
observer = None

# DPI Aware 설정 (윈도우 고해상도 모니터에서 글자 깨짐/흐림 방지)
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ====================================================
# [디자인 색상 테마 정의 - 클래식 플레이어 & 재즈 앨범 테마]
# ====================================================
COLOR_BG = '#121212'        # 깊은 밤 느낌의 미드나잇 다크 차콜 (전체 배경)
COLOR_CARD = '#1A1A1A'      # 입력 필드 및 카드 영역 배경
COLOR_DEEP = '#0B0B0B'      # 딥 블랙 (헤더/결과 영역 내부 배경)
COLOR_TEXT = '#EAEAEA'      # 세련된 소프트 화이트 (메인 텍스트/파일명)
COLOR_MUTED = '#666666'     # 차분한 다크 그레이 (경로/상세 설명)
COLOR_BRASS = '#A68A64'     # 은은한 빛바랜 앤틱 브라스/황동 (포인트/포커스/강조)
COLOR_RED = '#E26D5C'       # 빈티지 웜 레드 (닫기 버튼 호버 피드백)

# 현대적이고 깔끔한 폰트 스택 (기본값: Segoe UI, 한글 대체: 맑은 고딕)
FONT_FAMILY = ('Segoe UI', 'Malgun Gothic')


# ====================================================
# [1. 안전한 파일 인코딩 분석 및 읽기 기능]
# ====================================================
def read_file_safe(file_path):
    """
    chardet를 사용하여 파일의 인코딩을 분석하고 
    다양한 인코딩(UTF-8, CP949, Shift-JIS 등)으로 안전하게 읽어옵니다.
    """
    try:
        if not os.path.exists(file_path):
            return [], None
            
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        if not raw_data:
            return [], 'empty'

        # chardet로 인코딩 분석 (앞부분 일부 혹은 전체 분석)
        detect_sample = raw_data[:10240]  # 성능을 위해 최대 10KB만 샘플링
        detected = chardet.detect(detect_sample)
        detected_enc = detected.get('encoding')
        
        # 시도해볼 인코딩 후보군 리스트 (추천 순)
        encodings_to_try = []
        if detected_enc:
            encodings_to_try.append(detected_enc)
        
        # 한국어 및 일어 텍스트 파일의 주요 인코딩 추가
        encodings_to_try.extend(['utf-8', 'cp949', 'euc-kr', 'shift_jis', 'utf-16', 'ascii'])

        content = None
        used_encoding = None

        for enc in encodings_to_try:
            if not enc:
                continue
            try:
                content = raw_data.decode(enc)
                used_encoding = enc
                break
            except (UnicodeDecodeError, LookupError):
                continue

        # 모든 디코딩이 실패한 경우 손실 허용 디코딩 적용
        if content is None:
            content = raw_data.decode('utf-8', errors='replace')
            used_encoding = 'utf-8 (lossy)'

        # 행 단위 분리 및 반환
        return content.splitlines(), used_encoding
        
    except Exception as e:
        print(f"[오류] 파일 읽기 실패: {file_path} - {e}")
        return [], None


# ====================================================
# [2. 백그라운드 전체 인덱싱 및 개별 파일 갱신 스레드]
# ====================================================
def scan_and_index():
    """
    대상 폴더를 재귀적으로 탐색하여 모든 .txt 파일의 인덱스를 빌드합니다.
    (백그라운드 스레드에서 실행)
    """
    event_queue.put(("indexing_progress", (0, 1)))
    
    txt_files = []
    for root_dir, _, files in os.walk(TARGET_DIR):
        for file in files:
            if file.lower().endswith('.txt'):
                txt_files.append(os.path.join(root_dir, file))
                
    total = len(txt_files)
    if total == 0:
        event_queue.put(("indexing_done", 0))
        return

    # 대량의 파일이 있을 경우 속도를 위해 인덱싱 수행
    temp_index = {}
    for idx, file_path in enumerate(txt_files):
        if idx % 10 == 0 or idx == total - 1:
            event_queue.put(("indexing_progress", (idx + 1, total)))
            
        mtime = os.path.getmtime(file_path)
        lines, encoding = read_file_safe(file_path)
        filename = os.path.basename(file_path)
        rel_path = os.path.relpath(file_path, TARGET_DIR)
        
        temp_index[file_path] = {
            "mtime": mtime,
            "filename": filename,
            "rel_path": rel_path,
            "lines": lines,
            "content_lower": "\n".join(lines).lower(),
            "encoding": encoding
        }
        
    # 기존 인덱스를 백그라운드에서 빌드된 최신 인덱스로 교체 (락 처리)
    with index_lock:
        global file_index
        file_index.clear()
        file_index.update(temp_index)
        
    event_queue.put(("indexing_done", total))


def start_background_indexing():
    """인덱싱 작업을 백그라운드 스레드에서 시작합니다."""
    threading.Thread(target=scan_and_index, daemon=True).start()


def update_single_file(file_path):
    """개별 파일이 추가되거나 수정되었을 때 인덱스를 업데이트합니다. (락 처리)"""
    if not file_path.lower().endswith('.txt'):
        return
    
    # 디바운싱: 수정 직후 파일이 작성 중일 수 있으므로 약간의 지연 후 읽기
    time.sleep(0.1)
    
    mtime = os.path.getmtime(file_path)
    lines, encoding = read_file_safe(file_path)
    filename = os.path.basename(file_path)
    rel_path = os.path.relpath(file_path, TARGET_DIR)
    
    with index_lock:
        file_index[file_path] = {
            "mtime": mtime,
            "filename": filename,
            "rel_path": rel_path,
            "lines": lines,
            "content_lower": "\n".join(lines).lower(),
            "encoding": encoding
        }
    event_queue.put(("index_updated", len(file_index)))


def delete_single_file(file_path):
    """파일이 삭제되었을 때 인덱스에서 제거합니다. (락 처리)"""
    with index_lock:
        if file_path in file_index:
            del file_index[file_path]
    event_queue.put(("index_updated", len(file_index)))


# ====================================================
# [3. Watchdog 기반 실시간 파일 시스템 변화 모니터링]
# ====================================================
class FileUpdateHandler(FileSystemEventHandler):
    """파일 생성, 수정, 삭제 이벤트를 캐치하여 실시간으로 인덱스를 갱신하는 핸들러"""
    def on_created(self, event):
        if not event.is_directory:
            threading.Thread(target=update_single_file, args=(event.src_path,), daemon=True).start()

    def on_modified(self, event):
        if not event.is_directory:
            threading.Thread(target=update_single_file, args=(event.src_path,), daemon=True).start()

    def on_deleted(self, event):
        if not event.is_directory:
            threading.Thread(target=delete_single_file, args=(event.src_path,), daemon=True).start()


def start_file_watcher():
    """지정된 폴더의 실시간 모니터링을 시작합니다. (백그라운드 스레드)"""
    global observer
    event_handler = FileUpdateHandler()
    observer = Observer()
    observer.schedule(event_handler, path=TARGET_DIR, recursive=True)
    observer.start()


# ====================================================
# [4. 검색 연산 로직 (파일명 기준 그룹화 구현)]
# ====================================================
def perform_search(query):
    """
    메모리 캐시에서 파일명 및 파일 내부를 검색합니다.
    결과는 중복 파일명 없이 파일 단위로 그룹화되어 리턴됩니다.
    """
    if not query:
        # 검색어가 없을 때는 최근에 수정된 파일 상위 10개를 기본 노출합니다.
        with index_lock:
            sorted_files = sorted(file_index.items(), key=lambda x: x[1]["mtime"], reverse=True)[:10]
        
        results = []
        for path, data in sorted_files:
            results.append({
                "file_path": path,
                "filename": data["filename"],
                "rel_path": data["rel_path"],
                "matches": [],
                "is_filename_match": True,
                "match_count_str": "최근 수정됨"
            })
        return results

    query_lower = query.lower()
    results = []
    
    with index_lock:
        for file_path, data in file_index.items():
            filename = data["filename"]
            content_lower = data["content_lower"]
            lines = data["lines"]
            rel_path = data["rel_path"]
            
            # 1. 파일 이름 일치 여부
            filename_match = query_lower in filename.lower()
            
            # 2. 내용 일치 여부
            content_match = query_lower in content_lower
            
            if filename_match or content_match:
                file_matches = []
                # 내용이 일치하는 구체적인 행(라인 번호 및 문장)을 모두 추출
                if content_match:
                    for idx, line in enumerate(lines):
                        if query_lower in line.lower():
                            file_matches.append({
                                "line_no": idx + 1,
                                "line_text": line.strip()
                            })
                
                # 파일 단위로 단 1개의 그룹화된 결과 딕셔너리를 빌드
                results.append({
                    "file_path": file_path,
                    "filename": filename,
                    "rel_path": rel_path,
                    "matches": file_matches,
                    "is_filename_match": filename_match,
                    "match_count_str": f"{len(file_matches)}개 내용 일치" if file_matches else "파일명 일치"
                })
                    
    # 정렬 순서 정의
    def sort_criteria(item):
        fn_match = -1 if item["is_filename_match"] else 0
        return (fn_match, len(item["filename"]), item["filename"])
        
    results.sort(key=sort_criteria)
    return results[:100]  # UI 성능 확보를 위해 최대 100개 파일 노출


# ====================================================
# [5. Modern Flat GUI (Segoe UI 및 음악 트랙 스타일)]
# ====================================================
def build_gui():
    """Tkinter 검색기 창을 설계합니다. (모던 플랫 & 미드나잇 앤틱 테마)"""
    global root, search_var, results_text, status_label
    
    root = tk.Tk()
    root.title("노래 월드컵 로컬 검색기 (Premium Edition)")
    
    # 윈도우 프레임 제거 및 플랫 룩앤필 적용 (border 3D 완전 배제)
    root.overrideredirect(True)
    root.attributes("-alpha", 1.0)
    root.attributes("-topmost", False)
    
    # 아이콘 설정 (app_icon.ico 파일이 존재하면 적용)
    try:
        if os.path.exists("app_icon.ico"):
            root.iconbitmap("app_icon.ico")
    except Exception:
        pass
    
    # 메인 윈도우 크기 및 중앙 배치 계산
    width = 720
    height = 480
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2 - 40
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # 외곽 1px 얇은 구분선만 가지는 플랫 프레임
    main_frame = tk.Frame(root, bg=COLOR_BG, bd=0, relief='flat', highlightthickness=1, highlightbackground='#242424')
    main_frame.pack(fill='both', expand=True)
    
    # (1) 플랫 헤더 바
    header = tk.Frame(main_frame, bg=COLOR_DEEP, height=36, bd=0, relief='flat', highlightthickness=0)
    header.pack(fill='x', side='top')
    header.pack_propagate(False)
    
    title_lbl = tk.Label(header, text="노래 월드컵 텍스트 검색기", bg=COLOR_DEEP, fg=COLOR_BRASS, font=(FONT_FAMILY, 9, 'bold'), bd=0, relief='flat')
    title_lbl.pack(side='left', padx=18)
    
    # ✕ 종료 버튼
    close_btn = tk.Label(header, text="✕", bg=COLOR_DEEP, fg=COLOR_MUTED, font=('Georgia', 11, 'bold'), cursor='hand2', bd=0, relief='flat')
    close_btn.pack(side='right', padx=18)
    close_btn.bind("<Button-1>", lambda e: terminate_app())
    close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLOR_RED))  # 웜 레드 호버
    close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLOR_MUTED))
    
    # 헤더 드래그 기능 구현
    def start_drag(event):
        root.x = event.x
        root.y = event.y
    def drag(event):
        deltax = event.x - root.x
        deltay = event.y - root.y
        x = root.winfo_x() + deltax
        y = root.winfo_y() + deltay
        root.geometry(f"+{x}+{y}")
        
    header.bind("<Button-1>", start_drag)
    header.bind("<B1-Motion>", drag)
    title_lbl.bind("<Button-1>", start_drag)
    title_lbl.bind("<B1-Motion>", drag)
    
    # (2) 입력 검색 창 (3D 릴리프 없이 평면 서브 프레임으로 구성)
    search_frame = tk.Frame(main_frame, bg=COLOR_BG, bd=0, relief='flat', highlightthickness=0)
    search_frame.pack(fill='x', padx=24, pady=(20, 10))
    
    # 1px 플랫 테두리 시뮬레이션용 단색 프레임
    border_frame = tk.Frame(search_frame, bg='#262626', bd=1, relief='flat')
    border_frame.pack(fill='both', expand=True)
    
    # 포커스 시 앤틱 브라스색(Antique Brass) 1px 엣지 피드백
    def on_input_focus_in(event):
        border_frame.config(bg=COLOR_BRASS)
    def on_input_focus_out(event):
        border_frame.config(bg='#262626')
        
    search_var = tk.StringVar()
    entry = tk.Entry(border_frame, textvariable=search_var, bg=COLOR_CARD, fg=COLOR_TEXT, 
                     insertbackground=COLOR_BRASS, font=(FONT_FAMILY, 11), bd=0, relief='flat', highlightthickness=0)
    entry.pack(fill='both', expand=True, padx=12, pady=10)
    entry.bind("<FocusIn>", on_input_focus_in)
    entry.bind("<FocusOut>", on_input_focus_out)
    
    # 실시간 입력값 감지 연결
    search_var.trace_add("write", lambda *args: on_search_change())
    
    # (3) 결과 뷰 프레임 및 스크롤바 (음악 플레이어 트랙리스트 간격 및 패딩 디자인)
    results_frame = tk.Frame(main_frame, bg=COLOR_BG, bd=0, relief='flat', highlightthickness=0)
    results_frame.pack(fill='both', expand=True, padx=24, pady=(5, 12))
    
    # 스크롤바 재즈 다크 브라운 스타일링
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Vertical.TScrollbar", gripcount=0, background=COLOR_CARD, darkcolor=COLOR_BG, 
                    lightcolor=COLOR_BG, troughcolor=COLOR_DEEP, bordercolor=COLOR_BG, arrowcolor=COLOR_TEXT)
    
    scrollbar = ttk.Scrollbar(results_frame, style="Vertical.TScrollbar")
    scrollbar.pack(side='right', fill='y')
    
    # 여유로운 패딩(padx=15, pady=15)과 3D 아웃라인이 제거된 결과 텍스트창
    results_text = tk.Text(results_frame, bg=COLOR_DEEP, fg=COLOR_TEXT, font=(FONT_FAMILY, 10), 
                           bd=0, yscrollcommand=scrollbar.set, relief='flat', wrap='word', 
                           padx=18, pady=18, highlightthickness=0)
    results_text.pack(side='left', fill='both', expand=True)
    scrollbar.config(command=results_text.yview)
    
    # 음악 트랙 리스트 연출용 스타일링 태그 구성
    results_text.tag_config('title', font=(FONT_FAMILY, 11, 'bold'), foreground=COLOR_TEXT)        # 파일명 (소프트 화이트)
    results_text.tag_config('path', font=(FONT_FAMILY, 9), foreground=COLOR_MUTED)                 # 경로 및 매칭수 (다크 그레이)
    results_text.tag_config('divider', font=(FONT_FAMILY, 8), foreground=COLOR_DEEP)               # 트랙 사이 간격 패딩용 분리자
    
    # 결과 클릭 및 마우스 오버 이벤트 바인딩
    results_text.bind("<ButtonRelease-1>", on_result_click)
    results_text.bind("<Motion>", on_result_hover)
    
    # (4) 하단 상태 표시줄
    status_bar = tk.Frame(main_frame, bg=COLOR_DEEP, height=26, bd=0, relief='flat', highlightthickness=0)
    status_bar.pack(fill='x', side='bottom')
    status_bar.pack_propagate(False)
    
    status_label = tk.Label(status_bar, text="파일 인덱싱 준비 중...", bg=COLOR_DEEP, fg=COLOR_MUTED, font=(FONT_FAMILY, 8), bd=0, relief='flat')
    status_label.pack(side='left', padx=18)
    
    help_lbl = tk.Label(status_bar, text="종료: ESC / 우측 X 버튼 | 클릭: 상세 정보", bg=COLOR_DEEP, fg=COLOR_MUTED, font=(FONT_FAMILY, 8), bd=0, relief='flat')
    help_lbl.pack(side='right', padx=18)
    
    # ESC 입력 시 완전 종료 연결
    root.bind("<Escape>", lambda e: terminate_app())
    
    # 윈도우 닫기(X) 요청 시 완전 종료 설정
    root.protocol("WM_DELETE_WINDOW", terminate_app)
    
    # UI 이벤트 큐 처리를 주기적으로 수행 시작
    root.after(100, process_ui_queue)
    
    # 입력창 기본 포커싱
    entry.focus_set()


# ====================================================
# [6. GUI 제어 및 결과 노출 메서드]
# ====================================================
def on_search_change(*args):
    """검색어가 바뀔 때마다 실시간으로 검색 연산을 수행하고 화면을 다시 채웁니다."""
    query = search_var.get().strip()
    results = perform_search(query)
    display_results(results, query)


def insert_highlighted_text(text_widget, text, keyword):
    """텍스트 내부에 검색어와 매칭되는 단어가 있을 경우 차분한 앤틱 브라스 하이라이트로 색상을 교체해 삽입합니다."""
    if not keyword:
        text_widget.insert('end', text + '\n', 'snippet')
        return
        
    text_lower = text.lower()
    kw_lower = keyword.lower()
    kw_len = len(kw_lower)
    
    start = 0
    while True:
        pos = text_lower.find(kw_lower, start)
        if pos == -1:
            text_widget.insert('end', text[start:] + '\n', 'snippet')
            break
            
        text_widget.insert('end', text[start:pos], 'snippet')
        # 앤틱 브라스 배경색 하이라이트 적용
        text_widget.insert('end', text[pos:pos+kw_len], 'highlight')
        start = pos + kw_len


def display_results(results, query):
    """그룹화된 파일 매칭 결과를 Text 위젯에 포맷팅하여 정렬 출력합니다."""
    global displayed_results
    displayed_results = results  # 전역 변수에 현재 표시 결과 저장 (클릭 이벤트 추적용)
    
    results_text.config(state='normal')
    results_text.delete('1.0', 'end')
    
    if not results:
        if not query:
            results_text.insert('end', "\n  검색어를 입력해 주세요.\n", 'snippet')
        else:
            results_text.insert('end', f"\n  '{query}'에 대한 검색 결과가 없습니다.\n", 'snippet')
        results_text.config(state='disabled')
        return
        
    for r in results:
        # 1행: 파일명 (소프트 화이트)
        results_text.insert('end', f"  {r['filename']}\n", 'title')
        
        # 2행: 상대경로 및 일치 갯수 안내 (다크 그레이)
        info_text = f"  {r['rel_path']}   |   {r['match_count_str']}\n"
        results_text.insert('end', info_text, 'path')
        
        # 3행: 개별 항목 분리용 넉넉한 간격 생성 (음악 플레이어 디자인)
        results_text.insert('end', "\n", 'divider')
        
    results_text.config(state='disabled')


# ====================================================
# [7. 클릭 시 파일별 매칭 정보 상세 상세 팝업 창 구현]
# ====================================================
def show_detail_popup(target):
    """선택된 파일의 세부 매칭 문장들과 행 번호를 보여주는 모던 재즈 테마 팝업 창을 띄웁니다."""
    popup = tk.Toplevel(root)
    popup.title(f"상세 정보 - {target['filename']}")
    popup.configure(bg=COLOR_BG)
    
    popup.transient(root)
    popup.grab_set()  # 모달 효과 부여
    
    # 팝업 윈도우 크기 및 중앙 배치
    pw = 680
    ph = 480
    rx = root.winfo_x()
    ry = root.winfo_y()
    rw = root.winfo_width()
    rh = root.winfo_height()
    px = rx + (rw - pw) // 2
    py = ry + (rh - ph) // 2
    popup.geometry(f"{pw}x{ph}+{px}+{py}")
    
    # 팝업 윈도우 플랫 아웃라인
    pop_frame = tk.Frame(popup, bg=COLOR_BG, bd=0, relief='flat', highlightthickness=1, highlightbackground='#242424')
    pop_frame.pack(fill='both', expand=True)
    
    # (1) 헤더 패널 (파일명 및 전체 경로)
    header_frame = tk.Frame(pop_frame, bg=COLOR_DEEP, padx=20, pady=15, bd=0, relief='flat', highlightthickness=0)
    header_frame.pack(fill='x', side='top')
    
    title_lbl = tk.Label(header_frame, text=target["filename"], bg=COLOR_DEEP, fg=COLOR_TEXT, font=(FONT_FAMILY, 12, 'bold'), bd=0, relief='flat')
    title_lbl.pack(anchor='w')
    
    path_lbl = tk.Label(header_frame, text=f"경로: {target['file_path']}", bg=COLOR_DEEP, fg=COLOR_MUTED, font=('Consolas', 9), bd=0, relief='flat', wraplength=640, justify='left')
    path_lbl.pack(anchor='w', pady=(4, 0))
    
    # (2) 메인 리스트 영역 (텍스트 뷰 + 스크롤바)
    detail_frame = tk.Frame(pop_frame, bg=COLOR_BG, padx=20, pady=18, bd=0, relief='flat', highlightthickness=0)
    detail_frame.pack(fill='both', expand=True)
    
    scrollbar = ttk.Scrollbar(detail_frame, style="Vertical.TScrollbar")
    scrollbar.pack(side='right', fill='y')
    
    detail_text = tk.Text(detail_frame, bg=COLOR_DEEP, fg=COLOR_TEXT, font=(FONT_FAMILY, 10), 
                           bd=0, yscrollcommand=scrollbar.set, relief='flat', wrap='word', 
                           padx=15, pady=15, highlightthickness=0)
    detail_text.pack(side='left', fill='both', expand=True)
    scrollbar.config(command=detail_text.yview)
    
    # 팝업 텍스트용 태그 스타일링
    detail_text.tag_config('snippet', font=(FONT_FAMILY, 10), foreground=COLOR_TEXT)
    detail_text.tag_config('highlight', font=(FONT_FAMILY, 10, 'bold'), background='#D4AF37', foreground=COLOR_DEEP) # 선명한 골드/노란색 하이라이트
    detail_text.tag_config('line_no', font=('Consolas', 10, 'bold'), foreground=COLOR_BRASS) # 라인 번호는 앤틱 브라스 적용
    detail_text.tag_config('divider', font=(FONT_FAMILY, 6), foreground=COLOR_BG)
    detail_text.tag_config('info', font=(FONT_FAMILY, 10, 'italic'), foreground=COLOR_MUTED)
    
    query = search_var.get().strip()
    
    # 본문 데이터 출력 채우기 (전체 파일 내용을 보여주고 검색어만 노란색 하이라이트)
    detail_text.config(state='normal')
    
    file_path = target["file_path"]
    with index_lock:
        file_data = file_index.get(file_path)
        
    if file_data:
        all_lines = file_data["lines"]
    else:
        all_lines, _ = read_file_safe(file_path)
        
    if not all_lines:
        detail_text.insert('end', "\n  파일 내용이 비어 있거나 읽을 수 없습니다.\n", 'info')
    else:
        for idx, line in enumerate(all_lines):
            line_no = idx + 1
            detail_text.insert('end', f"  L{line_no}: ", 'line_no')
            insert_highlighted_text(detail_text, line, query)
            
    detail_text.config(state='disabled')
    
    # 파일 실행 헬퍼
    def open_notepad(e=None):
        try:
            os.startfile(target["file_path"])
        except Exception as ex:
            print(f"[오류] 파일 열기 실패: {ex}")
            
    # 더블 클릭 시 파일 바로 실행 바인딩
    detail_text.bind("<Double-Button-1>", open_notepad)
    
    # (3) 하단 제어 패널 및 버튼
    btn_frame = tk.Frame(pop_frame, bg=COLOR_DEEP, pady=12, bd=0, relief='flat', highlightthickness=0)
    btn_frame.pack(fill='x', side='bottom')
    
    open_btn = tk.Button(btn_frame, text="메모장(Notepad)으로 파일 열기", bg='#262626', fg=COLOR_TEXT, 
                         activebackground='#333333', activeforeground=COLOR_TEXT, relief='flat', bd=0, 
                         font=(FONT_FAMILY, 10, 'bold'), command=open_notepad, cursor='hand2', padx=18, pady=6)
    open_btn.pack(side='left', padx=18)
    
    close_btn = tk.Button(btn_frame, text="닫기 (ESC)", bg=COLOR_DEEP, fg=COLOR_TEXT, 
                          activebackground=COLOR_BG, activeforeground=COLOR_TEXT, relief='flat', bd=0, 
                          font=(FONT_FAMILY, 10), command=popup.destroy, cursor='hand2', padx=18, pady=6)
    close_btn.pack(side='right', padx=18)
    
    # ESC 키 입력 시 팝업 닫기
    popup.bind("<Escape>", lambda e: popup.destroy())
    
    # 포커스 고정
    detail_text.focus_set()


def on_result_click(event):
    """
    메인 결과 목록에서 파일명을 마우스로 클릭했을 때 상세 팝업창을 실행합니다.
    클릭한 좌표가 어떤 파일 인덱스에 매칭되는지 계산합니다.
    """
    click_pos = results_text.index(f"@{event.x},{event.y}")
    line_num = int(click_pos.split('.')[0])
    
    # 1개 검색 결과(파일명)당 고정 3행씩 사용하고 있으므로 나눗셈으로 인덱스 유추
    result_idx = (line_num - 1) // 3
    
    if 0 <= result_idx < len(displayed_results):
        # 텍스트 위젯 내 실제로 채워진 텍스트 영역 내부의 클릭인지만 체크
        if line_num <= len(displayed_results) * 3:
            target = displayed_results[result_idx]
            show_detail_popup(target)


def on_result_hover(event):
    """마우스 포인터가 유효한 파일 블록 위에 위치하면 손가락 피드백 커서 모양으로 변환합니다."""
    click_pos = results_text.index(f"@{event.x},{event.y}")
    line_num = int(click_pos.split('.')[0])
    result_idx = (line_num - 1) // 3
    
    if 0 <= result_idx < len(displayed_results) and line_num <= len(displayed_results) * 3:
        results_text.config(cursor="hand2")
    else:
        results_text.config(cursor="")


# ====================================================
# [8. 스레드 세이프(Thread-Safe) 이벤트 큐 프로세서]
# ====================================================
def process_ui_queue():
    """
    메인 GUI 루프 안에서 주기적으로 실행되며(100ms 간격)
    백그라운드 스레드에서 쌓은 이벤트 메시지들을 Thread-Safe하게 파싱하여 UI에 반영합니다.
    """
    try:
        while True:
            # 큐에서 이벤트를 비차단(Non-blocking) 방식으로 추출
            cmd, data = event_queue.get_nowait()
            
            if cmd == "reindex":
                start_background_indexing()
            elif cmd == "indexing_progress":
                current, total = data
                status_label.config(text=f"동기화 중... ({current}/{total})")
            elif cmd == "indexing_done":
                total_files = data
                status_label.config(text=f"색인 완료: {total_files}개 파일 ({TARGET_DIR})")
                on_search_change()
            elif cmd == "index_updated":
                total_files = data
                status_label.config(text=f"실시간 업데이트 완료: {total_files}개 파일 감시 중")
                on_search_change()
            elif cmd == "exit":
                terminate_app()
                return
    except queue.Empty:
        pass
    
    # 100ms 후에 다시 이 큐 확인 작업을 재귀 예약함
    if root:
        root.after(100, process_ui_queue)


# ====================================================
# [9. 프로그램 안전 종료 및 리소스 해제]
# ====================================================
def terminate_app():
    """모든 모니터링 스레드를 해제하고 완전히 프로그램을 종료합니다."""
    global root, observer
    
    # 1. Watchdog 파일 모니터링 종료
    if observer:
        try:
            observer.stop()
            observer.join(timeout=1.0)
        except Exception:
            pass
            
    # 2. GUI 종료 및 파이썬 종료
    if root:
        try:
            root.quit()
            root.destroy()
        except Exception:
            pass
    sys.exit(0)


# ====================================================
# [10. 메인 엔트리 포인트]
# ====================================================
if __name__ == "__main__":
    print("====================================================")
    print("   노래 월드컵 로컬 텍스트 검색 프로그램 작동 시작")
    print(f"   감시 경로: {TARGET_DIR}")
    print("   종료: ESC 키 또는 창 우측 상단 X 버튼")
    print("====================================================")
    
    # 1. 파일 감시자 시작 (데몬 스레드로 백그라운드 구동)
    start_file_watcher()
    
    # 2. 백그라운드 인덱싱 최초 수행 시작 (비동기 수행)
    start_background_indexing()
    
    # 3. Tkinter GUI 빌드 (★메인 스레드에서 실행)
    # 윈도우 OS 특성상 UI 루프는 반드시 메인 스레드에서 돌아야 정상 동작합니다.
    build_gui()
    
    # 4. 메인 스레드에서 UI 이벤트 대기 루프 실행
    # (GUI가 즉시 노출되며 루프 대기에 들어갑니다.)
    root.mainloop()
