# modules/notification_manager.py
from PyQt5 import sip
from PyQt5.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, 
    QGraphicsDropShadowEffect, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QColor, QFont

class ToastWidget(QWidget):
    def __init__(self, parent, type_str, title, message):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Style yang lebih solid dan kontras
        styles = {
            "SUCCESS": {"bg": "#d4edda", "text": "#155724", "border": "#c3e6cb", "icon": "✅"},
            "INFO":    {"bg": "#d1ecf1", "text": "#0c5460", "border": "#bee5eb", "icon": "ℹ️"},
            "WARNING": {"bg": "#fff3cd", "text": "#856404", "border": "#ffeeba", "icon": "⚠️"},
            "ERROR":   {"bg": "#f8d7da", "text": "#721c24", "border": "#f5c6cb", "icon": "❌"}
        }
        
        style = styles.get(type_str.upper(), styles["INFO"])
        
        # Container Utama
        self.container = QWidget(self)
        self.container.setStyleSheet(f"""
            QWidget {{
                background-color: {style['bg']};
                border: 1px solid {style['border']};
                border-radius: 6px;
            }}
            QLabel {{
                color: {style['text']};
                border: none;
                background-color: transparent;
            }}
            QPushButton {{
                background-color: transparent;
                color: {style['text']};
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(0,0,0,0.1);
            }}
        """)

        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(15, 10, 10, 10)
        
        # Ikon
        lbl_icon = QLabel(style['icon'])
        lbl_icon.setFont(QFont("Segoe UI Emoji", 14))
        
        # Teks
        text_layout = QVBoxLayout()
        lbl_title = QLabel(f"<b>{title}</b>")
        lbl_title.setFont(QFont("Segoe UI", 10))
        lbl_msg = QLabel(message)
        lbl_msg.setFont(QFont("Segoe UI", 9))
        lbl_msg.setWordWrap(True)
        text_layout.addWidget(lbl_title)
        text_layout.addWidget(lbl_msg)
        
        # Close Button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.clicked.connect(self.close_animation)
        
        layout.addWidget(lbl_icon)
        layout.addSpacing(10)
        layout.addLayout(text_layout, 1)
        layout.addWidget(btn_close, 0, Qt.AlignTop)

        # Layout Widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(self.container)

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.container.setGraphicsEffect(shadow)

        # Animasi
        self._opacity = 0.0
        self.anim = QPropertyAnimation(self, b"opacity_prop")
        
        # Auto Close Timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close_animation)
        self.timer.start(5000)

        self.show_animation()

    @pyqtProperty(float)
    def opacity_prop(self): return self._opacity

    @opacity_prop.setter
    def opacity_prop(self, val):
        self._opacity = val
        self.setWindowOpacity(val)

    def show_animation(self):
        self.anim.stop()
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

    def close_animation(self):
        self.timer.stop()
        self.anim.stop()
        self.anim.setDuration(200)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()

class NotificationManager(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.active_toasts = []
        self.hide()

    def show(self, level, title, message):
        level = level.upper()
        # Fallback ke QMessageBox jika Error atau level tidak dikenali
        if level == 'ERROR' or level not in ['SUCCESS', 'INFO', 'WARNING']:
            if level == 'ERROR':
                QMessageBox.critical(self.main_window, title, message)
            elif level == 'WARNING':
                 # Warning bisa Toast atau Box, kita coba Toast dulu
                 self._show_toast(level, title, message)
            else:
                 QMessageBox.information(self.main_window, title, message)
            return

        self._show_toast(level, title, message)

    def _show_toast(self, level, title, message):
        t = ToastWidget(self.main_window, level, title, message)
        t.adjustSize()
        t.show()
        self.active_toasts.append(t)
        t.destroyed.connect(lambda: self._cleanup(t))
        self._reposition()

    def _cleanup(self, t):
        if t in self.active_toasts: self.active_toasts.remove(t)
        self._reposition()

    def _reposition(self):
        if not self.parent(): return
        # Use rect() (relative coords) not geometry() (screen coords)
        rect = self.parent().rect()
        margin = 20
        x_right = rect.width() - margin
        y_start = rect.height() - margin   # start near the bottom-right
        y = y_start
        for t in reversed(self.active_toasts):
            try:
                if not sip.isdeleted(t):
                    t.adjustSize()
                    y -= (t.height() + 10)
                    x = x_right - t.width()
                    t.move(max(0, x), max(0, y))
            except: pass