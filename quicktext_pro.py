"""
QuickText Pro - Text Expander Application
Author: Jati Satrio
Version: 1.0.0
Description: A modern text expander with dual mode (Hotkey & Auto-expand)
"""

import sys
import json
import os
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QLineEdit, QComboBox, QTextEdit, QLabel, QDialog,
                             QMessageBox, QFileDialog, QSystemTrayIcon, QMenu,
                             QHeaderView, QGroupBox, QCheckBox, QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor
from pynput import keyboard
from pynput.keyboard import Key, Controller
import pyperclip
import sqlite3
import time


class KeyboardMonitor(QThread):
    """Thread for monitoring keyboard input"""
    expansion_triggered = pyqtSignal(str, str)  # keyword, phrase

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.mode = "hotkey"  # "hotkey" or "auto"
        self.shortcuts = {}
        self.buffer = ""
        self.last_key_time = time.time()
        self.ctrl_pressed = False
        self.listener = None
        self.keyboard_controller = Controller()
        self.pending_expansion = False

    def set_shortcuts(self, shortcuts):
        """Update shortcuts dictionary"""
        self.shortcuts = shortcuts

    def set_mode(self, mode):
        """Set monitoring mode"""
        self.mode = mode

    def on_press(self, key):
        """Handle key press events"""
        if not self.is_running:
            return

        try:
           # Suppress the trigger key if expansion is pending
            if self.pending_expansion:
                if key in [Key.space, Key.enter, Key.tab]:
                    self.pending_expansion = False
                    return False  # Suppress this key
            
            current_time = time.time()

            # Reset buffer if more than 2 seconds between keystrokes
            if current_time - self.last_key_time > 2:
                self.buffer = ""
            self.last_key_time = current_time

            # Track Ctrl key
            if key == Key.ctrl_l or key == Key.ctrl_r:
                self.ctrl_pressed = True
                return

            # Hotkey mode: Ctrl+Space to expand
            if self.mode == "hotkey":
                if self.ctrl_pressed and key == Key.space:
                    self.expand_from_buffer()
                    return

                # Build buffer for hotkey mode too
                if hasattr(key, 'char') and key.char:
                    self.buffer += key.char
                elif key == Key.space:
                    self.buffer += " "
                elif key == Key.backspace and len(self.buffer) > 0:
                    self.buffer = self.buffer[:-1]

            # Auto-expand mode
            elif self.mode == "auto":
                if hasattr(key, 'char') and key.char:
                    self.buffer += key.char
                elif key in [Key.space, Key.enter, Key.tab]:
                    # Check if we should expand before the trigger key is processed
                    if self.check_for_expansion():
                        self.pending_expansion = True
                        self.expand_from_buffer()
                        return False  # Suppress the trigger key
                    self.buffer = ""
                elif key == Key.backspace and len(self.buffer) > 0:
                    self.buffer = self.buffer[:-1]
                  
        except Exception as e:
            print(f"Error in on_press: {e}")

    def on_release(self, key):
        """Handle key release events"""
        if key == Key.ctrl_l or key == Key.ctrl_r:
            self.ctrl_pressed = False

    def check_for_expansion(self):
        """Check if buffer contains a keyword that should be expanded"""
        words = self.buffer.strip().split()
        if not words:
            return False
        keyword = words[-1].lower()
        return keyword in self.shortcuts  

    def expand_from_buffer(self):
        """Check buffer for keywords and expand"""
        words = self.buffer.strip().split()
        if not words:
            return

        keyword = words[-1].lower()

        if keyword in self.shortcuts:
            phrase = self.shortcuts[keyword]

            # Delete the keyword
            for _ in range(len(keyword)):
                self.keyboard_controller.press(Key.backspace)
                self.keyboard_controller.release(Key.backspace)
                time.sleep(0.01)

            # Copy phrase to clipboard and paste
            pyperclip.copy(phrase)
            time.sleep(0.05)

            # Paste using Ctrl+V
            self.keyboard_controller.press(Key.ctrl)
            self.keyboard_controller.press('v')
            time.sleep(0.05)
            self.keyboard_controller.release('v')
            self.keyboard_controller.release(Key.ctrl)

            # Emit signal for statistics
            self.expansion_triggered.emit(keyword, phrase)

            # Clear buffer after expansion
            self.buffer = ""

    def run(self):
        """Start keyboard listener"""
        self.is_running = True
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as self.listener:
            self.listener.join()

    def stop(self):
        """Stop keyboard listener"""
        self.is_running = False
        if self.listener:
            self.listener.stop()
            self.listener = None


class Database:
    """Database handler for shortcuts"""
    
    def __init__(self, db_path="quicktext_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Shortcuts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shortcuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                phrase TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Insert default shortcuts if empty
        cursor.execute('SELECT COUNT(*) FROM shortcuts')
        if cursor.fetchone()[0] == 0:
            default_shortcuts = [
                ('tady', 'Thank you very much in advance.', 'Thanks'),
                ('tassist', 'Thank you for your assistance.', 'Thanks'),
                ('tcontact', 'Thank you very much for contacting us.', 'Thanks'),
                ('tcoop', 'Thank you very much for your cooperation.', 'Thanks'),
                ('temail', 'Thank you for the e-mail.', 'Thanks'),
                ('hello', 'Hello, how can I help you today?', 'Greetings'),
                ('bye', 'Thank you and have a great day!', 'Closing'),
            ]
            cursor.executemany(
                'INSERT INTO shortcuts (keyword, phrase, category) VALUES (?, ?, ?)',
                default_shortcuts
            )
        
        conn.commit()
        conn.close()
    
    def get_all_shortcuts(self):
        """Get all shortcuts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, keyword, phrase, category, usage_count FROM shortcuts ORDER BY keyword')
        shortcuts = cursor.fetchall()
        conn.close()
        return shortcuts
    
    def add_shortcut(self, keyword, phrase, category):
        """Add new shortcut"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO shortcuts (keyword, phrase, category) VALUES (?, ?, ?)',
                (keyword.lower(), phrase, category)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def update_shortcut(self, shortcut_id, keyword, phrase, category):
        """Update existing shortcut"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE shortcuts SET keyword=?, phrase=?, category=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (keyword.lower(), phrase, category, shortcut_id)
        )
        conn.commit()
        conn.close()
    
    def delete_shortcut(self, shortcut_id):
        """Delete shortcut"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM shortcuts WHERE id=?', (shortcut_id,))
        conn.commit()
        conn.close()
    
    def increment_usage(self, keyword):
        """Increment usage count for a shortcut"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE shortcuts SET usage_count = usage_count + 1 WHERE keyword=?',
            (keyword.lower(),)
        )
        conn.commit()
        conn.close()
    
    def get_categories(self):
        """Get all unique categories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT category FROM shortcuts ORDER BY category')
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories
    
    def export_data(self, filepath):
        """Export all data to JSON"""
        shortcuts = self.get_all_shortcuts()
        data = {
            'shortcuts': [
                {
                    'keyword': s[1],
                    'phrase': s[2],
                    'category': s[3],
                    'usage_count': s[4]
                } for s in shortcuts
            ],
            'exported_at': datetime.now().isoformat()
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def import_data(self, filepath):
        """Import data from JSON"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for shortcut in data['shortcuts']:
            try:
                cursor.execute(
                    'INSERT OR REPLACE INTO shortcuts (keyword, phrase, category, usage_count) VALUES (?, ?, ?, ?)',
                    (shortcut['keyword'], shortcut['phrase'], shortcut['category'], shortcut.get('usage_count', 0))
                )
            except:
                pass
        
        conn.commit()
        conn.close()


class AddShortcutDialog(QDialog):
    """Dialog for adding/editing shortcuts"""
    
    def __init__(self, parent=None, edit_mode=False, shortcut_data=None):
        super().__init__(parent)
        self.edit_mode = edit_mode
        self.shortcut_data = shortcut_data
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Edit Shortcut" if self.edit_mode else "Add New Shortcut")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Keyword
        keyword_label = QLabel("Keyword:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("e.g., tady")
        layout.addWidget(keyword_label)
        layout.addWidget(self.keyword_input)
        
        # Phrase
        phrase_label = QLabel("Phrase:")
        self.phrase_input = QTextEdit()
        self.phrase_input.setPlaceholderText("e.g., Thank you very much in advance.")
        self.phrase_input.setMaximumHeight(100)
        layout.addWidget(phrase_label)
        layout.addWidget(self.phrase_input)
        
        # Category
        category_label = QLabel("Category:")
        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        db = Database()
        categories = db.get_categories()
        if not categories:
            categories = ['Thanks', 'Greetings', 'Closing', 'Opening', 'Apologies']
        self.category_input.addItems(categories)
        layout.addWidget(category_label)
        layout.addWidget(self.category_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet("background-color: #2563eb; color: white; padding: 5px 15px;")
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Fill data if edit mode
        if self.edit_mode and self.shortcut_data:
            self.keyword_input.setText(self.shortcut_data[1])
            self.phrase_input.setText(self.shortcut_data[2])
            self.category_input.setCurrentText(self.shortcut_data[3])
    
    def get_data(self):
        """Get input data"""
        return {
            'keyword': self.keyword_input.text().strip(),
            'phrase': self.phrase_input.toPlainText().strip(),
            'category': self.category_input.currentText().strip()
        }


class SettingsDialog(QDialog):
    """Settings dialog"""
    
    def __init__(self, parent=None, current_mode="hotkey"):
        super().__init__(parent)
        self.current_mode = current_mode
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Mode selection
        mode_group = QGroupBox("Expansion Mode")
        mode_layout = QVBoxLayout()
        
        info_label = QLabel("⚠️ You must stop monitoring before changing mode")
        info_label.setStyleSheet("color: #f59e0b; padding: 5px;")
        mode_layout.addWidget(info_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Hotkey (Ctrl+Space)", "Auto-Expand"])
        self.mode_combo.setCurrentIndex(0 if self.current_mode == "hotkey" else 1)
        mode_layout.addWidget(self.mode_combo)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def get_mode(self):
        """Get selected mode"""
        return "hotkey" if self.mode_combo.currentIndex() == 0 else "auto"


class StatisticsDialog(QDialog):
    """Statistics dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Usage Statistics")
        self.setModal(True)
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        db = Database()
        shortcuts = db.get_all_shortcuts()
        
        # Summary
        total_shortcuts = len(shortcuts)
        total_usage = sum(s[4] for s in shortcuts)
        
        summary = QLabel(f"Total Shortcuts: {total_shortcuts} | Total Expansions: {total_usage}")
        summary.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px; background: #e0e7ff;")
        layout.addWidget(summary)
        
        # Top shortcuts table
        top_label = QLabel("Top 10 Most Used Shortcuts:")
        top_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(top_label)
        
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Rank", "Keyword", "Phrase", "Usage Count"])
        
        # Sort by usage
        sorted_shortcuts = sorted(shortcuts, key=lambda x: x[4], reverse=True)[:10]
        table.setRowCount(len(sorted_shortcuts))
        
        for i, shortcut in enumerate(sorted_shortcuts):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(shortcut[1]))
            table.setItem(i, 2, QTableWidgetItem(shortcut[2][:50] + "..."))
            table.setItem(i, 3, QTableWidgetItem(str(shortcut[4])))
        
        header = table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        layout.addWidget(table)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.monitor = KeyboardMonitor()
        self.monitor.expansion_triggered.connect(self.on_expansion)
        self.is_monitoring = False
        self.init_ui()
        self.load_shortcuts()
        self.setup_tray()
    
    def init_ui(self):
        self.setWindowTitle("QuickText Pro v1.0")
        self.setMinimumSize(900, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Toolbar
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Keyword", "Phrase", "Category", "Usage"])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 350)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 80)
        main_layout.addWidget(self.table)
        
        # Status bar
        from PyQt5.QtWidgets import QStatusBar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Click 'Start Monitoring' to begin")
    
    def create_header(self):
        """Create header widget"""
        header = QWidget()
        header.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #7c3aed); padding: 15px;")
        layout = QHBoxLayout(header)
        
        title = QLabel("⚡ Pendi Sarap")
        title.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Mode selector
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Hotkey (Ctrl+Space)", "Auto-Expand"])
        self.mode_combo.currentIndexChanged.connect(self.change_mode)
        layout.addWidget(self.mode_combo)
        
        # Start/Stop button
        self.monitor_btn = QPushButton("▶ Start Monitoring")
        self.monitor_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.monitor_btn.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.monitor_btn)
        
        return header
    
    def create_toolbar(self):
        """Create toolbar widget"""
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #f3f4f6; padding: 10px; border-bottom: 1px solid #d1d5db;")
        layout = QHBoxLayout(toolbar)
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search shortcuts...")
        self.search_input.textChanged.connect(self.filter_shortcuts)
        self.search_input.setMaximumWidth(300)
        layout.addWidget(self.search_input)
        
        # Category filter
        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories")
        self.category_filter.currentIndexChanged.connect(self.filter_shortcuts)
        layout.addWidget(self.category_filter)
        
        layout.addStretch()
        
        # Buttons
        add_btn = QPushButton("➕ Add")
        add_btn.clicked.connect(self.add_shortcut)
        layout.addWidget(add_btn)
        
        edit_btn = QPushButton("✏️ Edit")
        edit_btn.clicked.connect(self.edit_shortcut)
        layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.clicked.connect(self.delete_shortcut)
        layout.addWidget(delete_btn)
        
        export_btn = QPushButton("💾 Export")
        export_btn.clicked.connect(self.export_data)
        layout.addWidget(export_btn)
        
        import_btn = QPushButton("📁 Import")
        import_btn.clicked.connect(self.import_data)
        layout.addWidget(import_btn)
        
        stats_btn = QPushButton("📊 Statistics")
        stats_btn.clicked.connect(self.show_statistics)
        layout.addWidget(stats_btn)
        
        settings_btn = QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self.show_settings)
        layout.addWidget(settings_btn)
        
        return toolbar
    
    def load_shortcuts(self):
        """Load shortcuts from database"""
        shortcuts = self.db.get_all_shortcuts()
        self.table.setRowCount(len(shortcuts))

        for i, shortcut in enumerate(shortcuts):
            self.table.setItem(i, 0, QTableWidgetItem(str(shortcut[0])))
            self.table.setItem(i, 1, QTableWidgetItem(shortcut[1]))
            self.table.setItem(i, 2, QTableWidgetItem(shortcut[2]))
            self.table.setItem(i, 3, QTableWidgetItem(shortcut[3]))
            self.table.setItem(i, 4, QTableWidgetItem(str(shortcut[4])))

        # Update category filter
        categories = self.db.get_categories()
        self.category_filter.clear()
        self.category_filter.addItem("All Categories")
        self.category_filter.addItems(categories)

        # Update monitor shortcuts
        self.update_monitor_shortcuts()
    
    def update_monitor_shortcuts(self):
        """Update shortcuts in monitor thread"""
        shortcuts = self.db.get_all_shortcuts()
        shortcuts_dict = {s[1]: s[2] for s in shortcuts}
        self.monitor.set_shortcuts(shortcuts_dict)
    
    def toggle_monitoring(self):
        """Toggle keyboard monitoring"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_btn.setText("⏸ Stop Monitoring")
            self.monitor_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: white;
                    font-weight: bold;
                    padding: 8px 20px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
            """)
            self.mode_combo.setEnabled(False)
            self.statusBar().showMessage("🟢 Monitoring ACTIVE - QuickText is watching your keystrokes") # type: ignore
            self.monitor.start()
        else:
            self.is_monitoring = False
            self.monitor.stop()
            self.monitor_btn.setText("▶ Start Monitoring")
            self.monitor_btn.setStyleSheet("""
                QPushButton {
                    background-color: #10b981;
                    color: white;
                    font-weight: bold;
                    padding: 8px 20px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #059669;
                }
            """)
            self.mode_combo.setEnabled(True)
            self.statusBar().showMessage("🔴 Monitoring STOPPED") # type: ignore
    
    def change_mode(self):
        """Change monitoring mode"""
        mode = "hotkey" if self.mode_combo.currentIndex() == 0 else "auto"
        self.monitor.set_mode(mode)
    
    def add_shortcut(self):
        """Add new shortcut"""
        dialog = AddShortcutDialog(self)
        if dialog.exec_():
            data = dialog.get_data()
            if data['keyword'] and data['phrase']:
                if self.db.add_shortcut(data['keyword'], data['phrase'], data['category']):
                    self.load_shortcuts()
                    QMessageBox.information(self, "Success", "Shortcut added successfully!")
                else:
                    QMessageBox.warning(self, "Error", "Keyword already exists!")
    
    def edit_shortcut(self):
        """Edit selected shortcut"""
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Warning", "Please select a shortcut to edit")
            return
        
        shortcut_id = int(self.table.item(selected, 0).text()) # type: ignore
        shortcuts = self.db.get_all_shortcuts()
        shortcut_data = next((s for s in shortcuts if s[0] == shortcut_id), None)
        
        if shortcut_data:
            dialog = AddShortcutDialog(self, edit_mode=True, shortcut_data=shortcut_data)
            if dialog.exec_():
                data = dialog.get_data()
                if data['keyword'] and data['phrase']:
                    self.db.update_shortcut(shortcut_id, data['keyword'], data['phrase'], data['category'])
                    self.load_shortcuts()
                    QMessageBox.information(self, "Success", "Shortcut updated successfully!")
    
    def delete_shortcut(self):
        """Delete selected shortcut"""
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Warning", "Please select a shortcut to delete")
            return
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                     "Are you sure you want to delete this shortcut?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            item = self.table.item(selected, 0)
            if item is not None:
                shortcut_id = int(item.text())
                self.db.delete_shortcut(shortcut_id)
                self.load_shortcuts()
                QMessageBox.information(self, "Success", "Shortcut deleted successfully!")
            else:
                QMessageBox.warning(self, "Error", "Could not find the selected shortcut ID.")
    
    def filter_shortcuts(self):
        """Filter shortcuts based on search and category"""
        search_text = self.search_input.text().lower()
        category = self.category_filter.currentText()
        
        for i in range(self.table.rowCount()):
            keyword_item = self.table.item(i, 1)
            phrase_item = self.table.item(i, 2)
            cat_item = self.table.item(i, 3)

            keyword = keyword_item.text().lower() if keyword_item is not None else ""
            phrase = phrase_item.text().lower() if phrase_item is not None else ""
            cat = cat_item.text() if cat_item is not None else ""

            match_search = search_text in keyword or search_text in phrase
            match_category = category == "All Categories" or category == cat

            self.table.setRowHidden(i, not (match_search and match_category))
    
    def export_data(self):
        """Export shortcuts to JSON"""
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Data", "", "JSON Files (*.json)")
        if filepath:
            self.db.export_data(filepath)
            QMessageBox.information(self, "Success", "Data exported successfully!")
    
    def import_data(self):
        """Import shortcuts from JSON"""
        filepath, _ = QFileDialog.getOpenFileName(self, "Import Data", "", "JSON Files (*.json)")
        if filepath:
            self.db.import_data(filepath)
            self.load_shortcuts()
            QMessageBox.information(self, "Success", "Data imported successfully!")
    
    def show_statistics(self):
        """Show statistics dialog"""
        dialog = StatisticsDialog(self)
        dialog.exec_()
    
    def show_settings(self):
        """Show settings dialog"""
        current_mode = "hotkey" if self.mode_combo.currentIndex() == 0 else "auto"
        dialog = SettingsDialog(self, current_mode)
        if dialog.exec_():
            new_mode = dialog.get_mode()
            self.mode_combo.setCurrentIndex(0 if new_mode == "hotkey" else 1)
    
    def on_expansion(self, keyword, phrase):
        """Handle expansion event"""
        self.db.increment_usage(keyword)
        self.load_shortcuts()
        if hasattr(self, 'status_bar') and self.status_bar is not None:
            self.status_bar.showMessage(f"✅ Expanded: {keyword} → {phrase[:30]}...", 3000)
    
    def setup_tray(self):
        """Setup system tray icon"""
        self.tray_icon = QSystemTrayIcon(self)
        # Set a default icon (should be replaced with a valid icon file)
        self.tray_icon.setIcon(QIcon())
        
        # Create tray menu
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show")
        if show_action is not None:
            show_action.triggered.connect(self.show)
        
        tray_menu.addSeparator()
        
        start_action = tray_menu.addAction("Start Monitoring")
        if start_action is not None:
            start_action.triggered.connect(self.toggle_monitoring)
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("Quit")
        if quit_action is not None:
            quit_action.triggered.connect(QApplication.quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("QuickText Pro")
        self.tray_icon.show()
    
    def closeEvent(self, event):
        """Handle window close event"""
        event.ignore()
        self.hide()
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.showMessage(
                "QuickText Pro",
                "Application minimized to tray",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("QuickText Pro")
    
    # Set application style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
