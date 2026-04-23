import os
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QSplitter, 
    QListWidget, QListWidgetItem, QTextEdit, QPushButton,
    QLabel, QFrame, QLineEdit, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QFont, QIcon, QColor

from utils.constants import NOTES_FILE_PATH

class NoteItemWidget(QWidget):
    def __init__(self, title, timestamp, snippet, is_pinned=False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        title_text = f"📌 {title}" if is_pinned else title
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        
        self.time_lbl = QLabel(timestamp)
        self.time_lbl.setStyleSheet("color: #b0bec5; font-size: 10px;")
        self.time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.snippet_lbl = QLabel(snippet)
        self.snippet_lbl.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        
        # Ellipsize properly
        self.title_lbl.setWordWrap(False)
        self.snippet_lbl.setWordWrap(False)
        self.title_lbl.setMinimumWidth(50)
        self.title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # We rely on layout for ellipsis instead of hardcoded font metrics now
        
        # Build horizontal row for title and time
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0,0,0,0)
        top_row.addWidget(self.title_lbl)
        top_row.addWidget(self.time_lbl)

        layout.addLayout(top_row)
        layout.addWidget(self.snippet_lbl)

    def update_data(self, title, timestamp, snippet, is_pinned=False):
        title_text = f"📌 {title}" if is_pinned else title
        self.title_lbl.setText(title_text)
        self.time_lbl.setText(timestamp)
        self.snippet_lbl.setText(snippet)

class NotesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notes")
        self.resize(800, 500)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        self.notes_data = {}
        self.current_note_id = None
        
        # Debounce timer for Auto-Save
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._perform_save)

        self._init_ui()
        self.load_data()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Gunakan QSplitter agar bisa di resize user antara panel kiri & kanan
        self.splitter = QSplitter(Qt.Horizontal)

        # --- LEFT PANEL (Note List) ---
        self.left_panel = QWidget()
        self.left_panel.setStyleSheet("background-color: #4e5663;") # Dark blue-grey from mockup
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 15, 10, 15)
        left_layout.setSpacing(10)

        # Header Tools (Add, Delete)
        tools_layout = QHBoxLayout()
        
        self.btn_add = QPushButton(" 📝 New ")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: transparent; border: 1px solid #78909c; color: #eceff1; border-radius: 4px; padding: 5px;
            }
            QPushButton:hover { background-color: #607d8b; }
        """)
        self.btn_add.clicked.connect(self.create_new_note)

        self.btn_delete = QPushButton(" 🗑️ ")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: transparent; border: 1px solid #ff5252; color: #ffeb3b; border-radius: 4px; padding: 5px;
            }
            QPushButton:hover { background-color: #ff1744; }
        """)
        self.btn_delete.clicked.connect(self.delete_current_note)

        self.btn_pin = QPushButton(" 📌 ")
        self.btn_pin.setCursor(Qt.PointingHandCursor)
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background-color: transparent; border: 1px solid #ffca28; color: #ffca28; border-radius: 4px; padding: 5px;
            }
            QPushButton:hover { background-color: #ff8f00; }
        """)
        self.btn_pin.clicked.connect(self.toggle_pin_current_note)

        tools_layout.addWidget(self.btn_add)
        tools_layout.addStretch()
        tools_layout.addWidget(self.btn_pin)
        tools_layout.addWidget(self.btn_delete)
        left_layout.addLayout(tools_layout)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #37404b; color: white; border: none; padding: 8px; border-radius: 4px;
            }
        """)
        self.search_bar.textChanged.connect(self._filter_list)
        left_layout.addWidget(self.search_bar)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent; border: none; outline: none;
            }
            QListWidget::item { padding: 0px; border-bottom: 1px solid #37404b; }
            QListWidget::item:selected { background-color: #37404b; border-radius: 5px; }
        """)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self.list_widget)

        # --- RIGHT PANEL (Editor) ---
        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("background-color: #2B2D30;") # Dark from theme
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(30, 30, 30, 30)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Title...")
        self.title_input.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                border: none;
                color: #EAEAEA;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 20px;
                font-weight: bold;
                padding-bottom: 10px;
                border-bottom: 1px solid #4A4C50;
            }
        """)
        self.title_input.textChanged.connect(self._on_title_changed)
        right_layout.addWidget(self.title_input)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Start typing your note here...")
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #ECF0F1;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 15px;
                line-height: 1.6;
            }
        """)
        self.editor.textChanged.connect(self._on_text_changed)
        right_layout.addWidget(self.editor)

        # Setup Splitter Ratios
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 1)  # Left gets 1 part
        self.splitter.setStretchFactor(1, 2)  # Right gets 2 parts (33% vs 66%)

        main_layout.addWidget(self.splitter)

    # --- LOGIC ---
    def load_data(self):
        if os.path.exists(NOTES_FILE_PATH):
            try:
                with open(NOTES_FILE_PATH, 'r', encoding='utf-8') as f:
                    self.notes_data = json.load(f)
            except Exception as e:
                print(f"Error loading notes: {e}")
                self.notes_data = {}
        self.refresh_list()

        # Select first item if exists
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _perform_save(self):
        try:
            # Pastikan folder data ada
            os.makedirs(os.path.dirname(NOTES_FILE_PATH), exist_ok=True)
            with open(NOTES_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.notes_data, f, indent=4)
        except Exception as e:
            print(f"Error auto-saving notes: {e}")

    def refresh_list(self, filter_text=""):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        # Sort descending by timestamp usually, pinned first
        sorted_items = sorted(
            self.notes_data.items(), 
            key=lambda x: (x[1].get('is_pinned', False), x[1].get('timestamp', '')), 
            reverse=True
        )

        for note_id, note_dict in sorted_items:
            # Search logic
            title = note_dict.get('title', 'Untitled')
            content = note_dict.get('content', '')
            timestamp = note_dict.get('timestamp', '')
            is_pinned = note_dict.get('is_pinned', False)
            
            if filter_text.lower() not in title.lower() and filter_text.lower() not in content.lower():
                continue

            # Limit snippet size
            snippet = content.replace("\n", " ")
            if len(snippet) > 80: snippet = snippet[:80] + "..."
            
            # Buat Item UI Custom
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.UserRole, note_id) # Simpan ID rahasia
            
            item_widget = NoteItemWidget(title, timestamp, snippet, is_pinned)
            # Tentukan ukuran yang pas sesuai konten widget + margin
            item.setSizeHint(QSize(200, 70))
            
            self.list_widget.setItemWidget(item, item_widget)

        self.list_widget.blockSignals(False)

    def _filter_list(self, text):
        # Prevent losing current unsaved work when filtering changes selection
        self.refresh_list(text)

    def _on_item_selected(self, current, previous):
        if not current:
            self.title_input.clear()
            self.title_input.setDisabled(True)
            self.editor.clear()
            self.editor.setDisabled(True)
            self.current_note_id = None
            return

        note_id = current.data(Qt.UserRole)
        note_dict = self.notes_data.get(note_id)
        if hasattr(self, 'editor') and note_dict:
            self.current_note_id = note_id
            
            self.title_input.setDisabled(False)
            self.title_input.blockSignals(True)
            self.title_input.setText(note_dict.get('title', ''))
            self.title_input.blockSignals(False)

            self.editor.setDisabled(False)
            self.editor.blockSignals(True) # Hindari loop auto-save saat load text
            self.editor.setPlainText(note_dict.get('content', ''))
            self.editor.blockSignals(False)

    def _on_text_changed(self):
        if not self.current_note_id: return
        
        text = self.editor.toPlainText()
        title = self.title_input.text().strip()
        if not title: title = "Untitled"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Preserve is_pinned if it exists
        is_pinned = self.notes_data.get(self.current_note_id, {}).get("is_pinned", False)

        # Update Dict memory
        self.notes_data[self.current_note_id] = {
            "title": title,
            "content": text,
            "timestamp": timestamp,
            "is_pinned": is_pinned
        }

        # Update List UI visually without doing a full rebuild 
        # to prevent focus/scroll losing
        item = self.list_widget.currentItem()
        if item:
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, NoteItemWidget):
                snippet = text.replace("\n", " ")
                if len(snippet) > 80: snippet = snippet[:80] + "..."
                is_pinned = self.notes_data[self.current_note_id].get('is_pinned', False)
                widget.update_data(title, timestamp, snippet, is_pinned)

        # Trigger auto-save debounce (1000ms pause)
        self.save_timer.start(1000)

    def _on_title_changed(self):
        if not self.current_note_id: return
        
        text = self.editor.toPlainText()
        title = self.title_input.text().strip()
        if not title: title = "Untitled"
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        is_pinned = self.notes_data.get(self.current_note_id, {}).get("is_pinned", False)

        self.notes_data[self.current_note_id] = {
            "title": title,
            "content": text,
            "timestamp": timestamp,
            "is_pinned": is_pinned
        }

        item = self.list_widget.currentItem()
        if item:
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, NoteItemWidget):
                snippet = text.replace("\n", " ")
                if len(snippet) > 80: snippet = snippet[:80] + "..."
                widget.update_data(title, timestamp, snippet, is_pinned)

        self.save_timer.start(1000)

    def create_new_note(self):
        note_id = "note_" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        self.notes_data[note_id] = {
            "title": "New Note",
            "content": "",
            "timestamp": timestamp,
            "is_pinned": False
        }
        
        # Bersihkan search filter jika rekap
        self.search_bar.clear()
        self.refresh_list()
        
        # Cari dan pilih note baru
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == note_id:
                self.list_widget.setCurrentItem(item)
                break
                
        self.editor.setFocus()
        self._perform_save()

    def delete_current_note(self):
        if not self.current_note_id: return
        
        del self.notes_data[self.current_note_id]
        self.current_note_id = None
        self._perform_save()
        self.refresh_list()

    def toggle_pin_current_note(self):
        if not self.current_note_id: return
        
        current_pin = self.notes_data[self.current_note_id].get("is_pinned", False)
        self.notes_data[self.current_note_id]["is_pinned"] = not current_pin
        
        self._perform_save()
        self.refresh_list(self.search_bar.text())
        
        # Reselect the note after list rebuild
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == self.current_note_id:
                self.list_widget.setCurrentItem(item)
                break
