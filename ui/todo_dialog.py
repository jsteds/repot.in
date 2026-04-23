import os
import json
from datetime import datetime, timedelta
import logging

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QListWidget, QListWidgetItem, QWidget, QCheckBox, QToolButton,
    QButtonGroup, QFrame, QMenu, QAction, QInputDialog, QApplication
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QColor

from utils.constants import TODO_FILE_PATH

class TodoItemWidget(QWidget):
    # Signals to communicate with the parent dialog
    delete_requested = pyqtSignal()
    checked_changed = pyqtSignal(bool)
    memo_updated = pyqtSignal(str)
    pin_toggled = pyqtSignal()
    size_changed = pyqtSignal() # Emitted when memo visibility changes

    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 10, 5, 10)
        
        # Checkbox replacement using QToolButton for guaranteed rendering without assets
        self.checkbox = QToolButton()
        self.checkbox.setCheckable(True)
        self.checkbox.setChecked(self.task_data.get("completed", False))
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.setText("✔")
        self.checkbox.setStyleSheet("""
            QToolButton {
                border: 2px solid #576574;
                border-radius: 4px;
                background-color: transparent;
                color: transparent;
                font-weight: bold;
                font-size: 14px;
            }
            QToolButton:checked {
                background-color: #A3C9A6;
                border: 2px solid #A3C9A6;
                color: white;
            }
        """)
        self.checkbox.toggled.connect(self._on_checked)
        
        # Text layout (Task + Memo)
        self.text_vbox = QVBoxLayout()
        self.text_vbox.setSpacing(4)
        
        self.label = QLabel(self.task_data.get("task", ""))
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setWordWrap(True)
        
        memo_text = self.task_data.get("memo", "")
        self.memo_label = QLabel(memo_text)
        self.memo_label.setFont(QFont("Segoe UI", 9))
        self.memo_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        self.memo_label.setWordWrap(True)
        self.memo_label.setVisible(bool(memo_text))
        
        self.text_vbox.addWidget(self.label)
        self.text_vbox.addWidget(self.memo_label)
        
        # Menu Button ("...")
        self.menu_btn = QToolButton()
        self.menu_btn.setText(" ⋯ ")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #7f8c8d;
                font-size: 18px;
                font-weight: bold;
                border: none;
                padding: 0px 5px;
            }
            QToolButton:hover {
                color: #ecf0f1;
            }
            QToolButton::menu-indicator {
                image: none; /* Hide default dropdown arrow */
            }
        """)
        
        # Context Menu
        self.menu = QMenu(self.menu_btn)
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #2f3640;
                color: #ecf0f1;
                border: 1px solid #485460;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px 5px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #E66A8A;
            }
        """)
        
        is_pinned = self.task_data.get("is_pinned", False)
        pin_text = "Unpin from top" if is_pinned else "Pin on the top"
        self.action_pin = self.menu.addAction(pin_text)
        self.action_pin.triggered.connect(self._toggle_pin)
        
        self.action_memo = self.menu.addAction("Edit memo" if memo_text else "Add a memo")
        self.action_memo.triggered.connect(self._edit_memo)
        
        self.menu.addSeparator()
        self.action_delete = self.menu.addAction("Delete")
        self.action_delete.triggered.connect(self.delete_requested.emit)
        
        self.menu_btn.setMenu(self.menu)
        
        # Pin Indicator (Optional visually, but adds to logic)
        self.pin_icon = QLabel("📌")
        self.pin_icon.setStyleSheet("color: #E66A8A; font-size: 12px;")
        self.pin_icon.setVisible(is_pinned)
        
        # Assemble Layout
        self.layout.addWidget(self.checkbox, 0, Qt.AlignTop)
        
        icon_text_layout = QHBoxLayout()
        icon_text_layout.addWidget(self.pin_icon, 0, Qt.AlignTop)
        icon_text_layout.addLayout(self.text_vbox, 1)
        
        self.layout.addLayout(icon_text_layout, 1)
        self.layout.addWidget(self.menu_btn, 0, Qt.AlignTop)
        
        self.update_style()

    def update_style(self):
        if self.checkbox.isChecked():
            self.label.setStyleSheet("color: #7f8c8d; text-decoration: line-through;")
        else:
            self.label.setStyleSheet("color: #ecf0f1; text-decoration: none;")
            
    def _on_checked(self, checked):
        self.update_style()
        self.checked_changed.emit(checked)
        
    def _toggle_pin(self):
        self.pin_toggled.emit()
        
    def _edit_memo(self):
        current_memo = self.task_data.get("memo", "")
        # Gunakan QInputDialog untuk simple input
        text, ok = QInputDialog.getMultiLineText(
            self, "Memo", "Masukkan catatan:", current_memo
        )
        if ok:
            memo_str = text.strip()
            self.memo_label.setText(memo_str)
            self.memo_label.setVisible(bool(memo_str))
            self.action_memo.setText("Edit memo" if memo_str else "Add a memo")
            self.memo_updated.emit(memo_str)
            self.size_changed.emit() # Beritahu parent list bahwa tinggi berubah


class TodoListDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Todo List")
        # Mengubah setFixedSize agar responsif
        self.resize(400, 600)
        self.setMinimumSize(350, 450)
        
        self.setWindowFlags(self.windowFlags() | Qt.Tool) 
        
        self.is_pinned = False
        self.current_date = datetime.now()
        self.view_mode = "Day"
        self.todos = {} # Format: {"YYYY-MM-DD": [{"task": "...", "completed": bool, "memo": "", "is_pinned": bool}]}
        
        self.load_data()
        self.init_ui()
        self.refresh_list()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #353B48; /* Dark theme matching mockup */
                border-radius: 8px;
            }
            QLabel {
                color: #ecf0f1;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- TOP TABS (Day, Week, Month, Year) ---
        tabs_container = QWidget()
        tabs_container.setStyleSheet("background-color: #2f3640;")
        tabs_layout = QHBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tab_group = QButtonGroup(self)
        tabs = ["Day", "Week", "Month", "Year"]
        for i, tab_name in enumerate(tabs):
            btn = QPushButton(tab_name)
            btn.setCheckable(True)
            if i == 0: btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #7f8c8d;
                    border: none;
                    padding: 15px;
                    font-weight: bold;
                    font-family: "Segoe UI";
                }
                QPushButton:checked {
                    color: #ecf0f1;
                    border-bottom: 2px solid #E66A8A; /* Pink accent */
                }
                QPushButton:hover {
                    color: #bdc3c7;
                }
            """)
            self.tab_group.addButton(btn, i)
            tabs_layout.addWidget(btn)
        
        self.tab_group.buttonClicked.connect(self.change_view_mode)
        main_layout.addWidget(tabs_container)
        
        # --- DATE NAVIGATOR ---
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(20, 20, 20, 10)
        
        date_row = QHBoxLayout()
        self.prev_btn = QPushButton(" < ")
        self.next_btn = QPushButton(" > ")
        for btn in [self.prev_btn, self.next_btn]:
            btn.setStyleSheet("background: transparent; color: #7f8c8d; font-size: 20px; font-weight: bold; border: none;")
            btn.setCursor(Qt.PointingHandCursor)
            
        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setStyleSheet("font-size: 24px; font-weight: bold; font-family: 'Segoe UI';")
        
        self.sub_date_label = QLabel()
        self.sub_date_label.setAlignment(Qt.AlignCenter)
        self.sub_date_label.setStyleSheet("font-size: 12px; color: #7f8c8d; font-family: 'Segoe UI';")
        
        date_col = QVBoxLayout()
        date_col.addWidget(self.date_label)
        date_col.addWidget(self.sub_date_label)
        
        date_row.addWidget(self.prev_btn)
        date_row.addLayout(date_col, 1)
        date_row.addWidget(self.next_btn)
        
        nav_layout.addLayout(date_row)
        main_layout.addWidget(nav_container)
        
        self.prev_btn.clicked.connect(self.prev_day)
        self.next_btn.clicked.connect(self.next_day)
        self.update_date_labels()
        
        # --- INPUT ROW ---
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(20, 10, 20, 10)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("≡  Add a task...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #2f3640;
                color: #ecf0f1;
                border: 1px solid #485460;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
        """)
        self.input_field.returnPressed.connect(self.add_task)
        input_layout.addWidget(self.input_field)
        main_layout.addWidget(input_container)
        
        # --- LIST WIDGET ---
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #485460;
            }
            QListWidget::item:selected {
                background-color: transparent;
            }
        """)
        main_layout.addWidget(self.list_widget, 1)
        
        # --- BOTTOM BAR (Pin) ---
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(10, 5, 20, 10)
        
        self.pin_btn = QPushButton("📌 Pin Editor")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7f8c8d;
                border: none;
                font-size: 12px;
                text-align: right;
            }
            QPushButton:checked {
                color: #E66A8A;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #bdc3c7;
            }
        """)
        self.pin_btn.clicked.connect(self.toggle_pin)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.pin_btn)
        
        main_layout.addWidget(bottom_container)

    def load_data(self):
        if os.path.exists(TODO_FILE_PATH):
            try:
                with open(TODO_FILE_PATH, 'r', encoding='utf-8') as f:
                    self.todos = json.load(f)
            except Exception as e:
                logging.error(f"Gagal memuat Todo list: {e}")
                self.todos = {}

    def save_data(self):
        try:
            os.makedirs(os.path.dirname(TODO_FILE_PATH), exist_ok=True)
            with open(TODO_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.todos, f, indent=4)
        except Exception as e:
            logging.error(f"Gagal menyimpan Todo list: {e}")

    def update_date_labels(self):
        if hasattr(self, 'view_mode'):
            mode = self.view_mode
        else:
            mode = "Day"

        if mode == "Day":
            self.date_label.setText(self.current_date.strftime("%A"))
            self.sub_date_label.setText(self.current_date.strftime("%b %d, %Y"))
            if self.current_date.date() == datetime.now().date():
                self.date_label.setText(f"Today ({self.date_label.text()})")
        elif mode == "Week":
            start_week = self.current_date - timedelta(days=self.current_date.weekday())
            end_week = start_week + timedelta(days=6)
            self.date_label.setText("This Week" if start_week.date() <= datetime.now().date() <= end_week.date() else "Week")
            self.sub_date_label.setText(f"{start_week.strftime('%b %d')} - {end_week.strftime('%b %d, %Y')}")
        elif mode == "Month":
            self.date_label.setText(self.current_date.strftime("%B"))
            self.sub_date_label.setText(self.current_date.strftime("%Y"))
            if self.current_date.month == datetime.now().month and self.current_date.year == datetime.now().year:
                self.date_label.setText(f"This Month ({self.current_date.strftime('%B')})")
        elif mode == "Year":
            self.date_label.setText(self.current_date.strftime("%Y"))
            self.sub_date_label.setText("Full Year")
            if self.current_date.year == datetime.now().year:
                self.date_label.setText(f"This Year ({self.current_date.strftime('%Y')})")

    def change_view_mode(self, btn):
        self.view_mode = btn.text()
        self.update_date_labels()
        self.refresh_list()

    def prev_day(self):
        if getattr(self, 'view_mode', 'Day') == "Day":
            self.current_date -= timedelta(days=1)
        elif self.view_mode == "Week":
            self.current_date -= timedelta(weeks=1)
        elif self.view_mode == "Month":
            first_day = self.current_date.replace(day=1)
            self.current_date = first_day - timedelta(days=1)
        elif self.view_mode == "Year":
            self.current_date = self.current_date.replace(year=self.current_date.year - 1)
        self.update_date_labels()
        self.refresh_list()

    def next_day(self):
        if getattr(self, 'view_mode', 'Day') == "Day":
            self.current_date += timedelta(days=1)
        elif self.view_mode == "Week":
            self.current_date += timedelta(weeks=1)
        elif self.view_mode == "Month":
            next_month = (self.current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            self.current_date = next_month
        elif self.view_mode == "Year":
            self.current_date = self.current_date.replace(year=self.current_date.year + 1)
        self.update_date_labels()
        self.refresh_list()

    def add_task(self):
        task_text = self.input_field.text().strip()
        if not task_text:
            return
            
        date_str = self.current_date.strftime("%Y-%m-%d")
        if date_str not in self.todos:
            self.todos[date_str] = []
            
        # Format task data baru dengan is_pinned dan memo
        self.todos[date_str].append({
            "task": task_text, 
            "completed": False,
            "memo": "",
            "is_pinned": False
        })
        self.input_field.clear()
        self.save_data()
        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        mode = getattr(self, 'view_mode', 'Day')
        all_tasks = []
        
        if mode == "Day":
            date_str = self.current_date.strftime("%Y-%m-%d")
            for idx, task in enumerate(self.todos.get(date_str, [])):
                all_tasks.append((date_str, idx, task))
        else:
            if mode == "Week":
                start_w = (self.current_date - timedelta(days=self.current_date.weekday())).date()
                end_w = start_w + timedelta(days=6)
                for d_str, tasks in self.todos.items():
                    try:
                        t_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                        if start_w <= t_date <= end_w:
                            for idx, task in enumerate(tasks):
                                all_tasks.append((d_str, idx, task))
                    except ValueError:
                        pass
            elif mode == "Month":
                for d_str, tasks in self.todos.items():
                    try:
                        t_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                        if t_date.month == self.current_date.month and t_date.year == self.current_date.year:
                            for idx, task in enumerate(tasks):
                                all_tasks.append((d_str, idx, task))
                    except ValueError:
                        pass
            elif mode == "Year":
                for d_str, tasks in self.todos.items():
                    try:
                        t_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                        if t_date.year == self.current_date.year:
                            for idx, task in enumerate(tasks):
                                all_tasks.append((d_str, idx, task))
                    except ValueError:
                        pass

        # Sort tasks: Pinned first, then by date, then original index
        all_tasks.sort(key=lambda x: (not x[2].get("is_pinned", False), x[0], x[1]))

        for orig_date_str, orig_idx, task_data in all_tasks:
            # We copy data so we can mutate task title for UI display without saving to JSON
            display_data = task_data.copy()
            if mode != "Day":
                try:
                    dt = datetime.strptime(orig_date_str, "%Y-%m-%d")
                    display_data["task"] = f"[{dt.strftime('%d %b')}] {display_data['task']}"
                except ValueError:
                    pass

            item = QListWidgetItem(self.list_widget)
            widget = TodoItemWidget(display_data, self)
            
            # Use default parameters to bind variables properly in loop
            widget.delete_requested.connect(lambda d=orig_date_str, idx=orig_idx: self.delete_task(d, idx))
            widget.checked_changed.connect(lambda state, d=orig_date_str, idx=orig_idx: self.on_task_checked(d, idx, state))
            widget.memo_updated.connect(lambda memo, d=orig_date_str, idx=orig_idx: self.on_memo_updated(d, idx, memo))
            widget.pin_toggled.connect(lambda d=orig_date_str, idx=orig_idx: self.on_pin_toggled(d, idx))
            
            widget.size_changed.connect(lambda i=item, w=widget: i.setSizeHint(w.sizeHint()))
            widget.layout.invalidate()
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)

    def on_task_checked(self, date_str, index, state):
        if date_str in self.todos and index < len(self.todos[date_str]):
            self.todos[date_str][index]["completed"] = state
            self.save_data()

    def on_memo_updated(self, date_str, index, new_memo):
        if date_str in self.todos and index < len(self.todos[date_str]):
            self.todos[date_str][index]["memo"] = new_memo
            self.save_data()

    def on_pin_toggled(self, date_str, index):
        if date_str in self.todos and index < len(self.todos[date_str]):
            current_pin = self.todos[date_str][index].get("is_pinned", False)
            self.todos[date_str][index]["is_pinned"] = not current_pin
            self.save_data()
            self.refresh_list()

    def delete_task(self, date_str, index):
        if date_str in self.todos and index < len(self.todos[date_str]):
            del self.todos[date_str][index]
            self.save_data()
            self.refresh_list()

    def toggle_pin(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.pin_btn.setText("📌 (Pinned)")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.pin_btn.setText("📌 Pin Editor")
            
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalculate heights when dialog is resized horizontally 
        # to ensure text wrapping doesn't get clipped.
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget:
                # Force recalculation of size
                QApplication.processEvents() 
                item.setSizeHint(widget.sizeHint())
