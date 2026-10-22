import copy
import json
import shutil
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                             QMenu, QMessageBox, QPlainTextEdit, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)

from app.bridge import TX
from app.pages.base import Page
from app.store import Store
from app.ui import button, confirm, group, pad, page_header, shortcut
from app.workers import SendWorker


class EditDialog(QDialog):
    def __init__(self, name="", code=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit key" if name else "Add key")
        self.resize(540, 480)
        c = code or {}
        self._extra = {k: v for k, v in c.items()
                       if k not in ("proto", "name", "addr", "cmd", "khz", "raw", "note")}
        f = QFormLayout(self)
        f.setContentsMargins(24, 20, 24, 20)
        f.setVerticalSpacing(10)
        self.name = QLineEdit(name)
        self.pname = QLineEdit(c.get("name", "UNKNOWN"))
        self.khz = QSpinBox(); self.khz.setRange(20, 60); self.khz.setValue(c.get("khz", 38)); self.khz.setSuffix(" kHz")
        self.proto = QSpinBox(); self.proto.setRange(0, 99); self.proto.setValue(c.get("proto", 0))
        self.addr = QSpinBox(); self.addr.setRange(0, 65535); self.addr.setValue(c.get("addr", 0))
        self.cmd = QSpinBox(); self.cmd.setRange(0, 65535); self.cmd.setValue(c.get("cmd", 0))
        self.note = QLineEdit(c.get("note", ""))
        self.raw = QPlainTextEdit(",".join(map(str, c.get("raw", []))))
        self.raw.setObjectName("log")
        for label, w in [("Key name", self.name), ("Protocol name", self.pname), ("Protocol id", self.proto),
                         ("Address", self.addr), ("Command", self.cmd), ("Carrier frequency", self.khz),
                         ("Note", self.note), ("Raw timings (us, comma separated)", self.raw)]:
            f.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = bb.button(QDialogButtonBox.Ok)
        ok.setText("Save")
        ok.setObjectName("primary")
        bb.accepted.connect(self.check)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def check(self):
        try:
            raw = [int(x) for x in self.raw.toPlainText().replace(",", " ").split()]
            if len(raw) < 2 or min(raw) <= 0 or not Store.key_name(self.name.text()):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Invalid key", "Enter a key name and at least two raw timings "
                                "(positive whole numbers, in microseconds).")
            return
        self.key = Store.key_name(self.name.text())
        self.code = dict(self._extra, proto=self.proto.value(), name=self.pname.text() or "UNKNOWN",
                         addr=self.addr.value(), cmd=self.cmd.value(), khz=self.khz.value(),
                         raw=raw, note=self.note.text())
        self.accept()


class LibraryPage(Page):
    UNDO_LIMIT = 20

    def __init__(self, win):
        super().__init__(win)
        self.undo = []              # (remote name, snapshot of its data)
        self.send_thread = None
        self.rlist = QListWidget()
        self.rlist.currentRowChanged.connect(self.on_remote)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search keys")
        self.search.textChanged.connect(self.fill_table)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Key", "Protocol", "Address", "Command", "Pulses", "Note"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_key)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.key_menu)
        shortcut(self.table, "Del", self.del_key, Qt.WidgetShortcut)
        shortcut(self, "Ctrl+Z", self.do_undo)
        self.empty = QLabel()
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notes about this remote (brand, model, room)")
        self.notes.editingFinished.connect(self.save_notes)
        self.msg = QLabel()
        self.msg.setObjectName("muted")

        # Remote actions: primary buttons visible, the rest in a menu to keep the column calm.
        more = button("More")
        menu = QMenu(more)
        for text, fn in [("Rename…", self.ren_remote), ("Duplicate…", self.dup_remote),
                         ("Import…", self.imp), ("Export…", self.exp)]:
            menu.addAction(text, fn)
        menu.addSeparator()
        menu.addAction("Delete remote", self.del_remote)
        more.setMenu(menu)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(group("Remotes"))
        left.addWidget(self.rlist)
        left.addWidget(button("New remote", win.new_remote, "primary"))
        left.addWidget(more)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.notes)
        right.addWidget(self.search)
        right.addWidget(self.table, 1)
        right.addWidget(self.empty, 1)
        right.addWidget(self.msg)
        row = QHBoxLayout()
        row.addWidget(button("Add key", self.add_key, "primary"))
        row.addWidget(button("Edit", self.edit_key))
        row.addWidget(button("Test send", self.test_key))
        row.addWidget(button("Re-learn", self.relearn))
        kmore = button("More")
        km = QMenu(kmore)
        km.addAction("Rename…", self.ren_key)
        km.addAction("Duplicate", self.dup_key)
        km.addSeparator()
        km.addAction("Undo last change (Ctrl+Z)", self.do_undo)
        kmore.setMenu(km)
        row.addWidget(kmore)
        row.addStretch()
        row.addWidget(button("Delete", self.del_key, "danger"))
        right.addLayout(row)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Library", "Manage remotes and the keys stored in each one."))
        h = QHBoxLayout()
        h.setSpacing(24)
        h.addLayout(left, 1)
        h.addLayout(right, 4)
        v.addLayout(h, 1)

    # data + undo --------------------------------------------------------
    def mutate(self, fn):
        """Run fn(data) on the current remote, saving an undo snapshot first."""
        d = self.win.data()
        if d is None:
            return
        self.undo.append((self.win.current, copy.deepcopy(d)))
        del self.undo[:-self.UNDO_LIMIT]
        fn(d)
        self.win.put(d)
        self.refresh()

    def do_undo(self):
        while self.undo:
            name, snap = self.undo.pop()
            if self.win.store.exists(name):
                self.win.current = name
                self.win.store.save(name, snap)
                self.refresh()
                self.msg.setText("Undid the last change.")
                return
        self.msg.setText("Nothing to undo.")

    # view ---------------------------------------------------------------
    def refresh(self):
        self.rlist.blockSignals(True)
        self.rlist.clear()
        names = self.win.store.names()
        self.rlist.addItems(names)
        if self.win.current in names:
            self.rlist.setCurrentRow(names.index(self.win.current))
        self.rlist.blockSignals(False)
        self.notes.setText((self.win.data() or {}).get("notes", ""))
        self.fill_table()

    def on_remote(self, row):
        if row >= 0:
            self.win.current = self.rlist.item(row).text()
            self.refresh()

    def fill_table(self):
        d = self.win.data()
        self.table.setRowCount(0)
        q = self.search.text().lower()
        for k, c in (d["keys"].items() if d else []):
            if q and q not in k.lower() and q not in c.get("note", "").lower():
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            for i, v in enumerate([k, c.get("name", "RAW"), c.get("addr", ""), c.get("cmd", ""),
                                   len(c.get("raw", [])), c.get("note", "")]):
                self.table.setItem(r, i, QTableWidgetItem(str(v)))
        n = self.table.rowCount()
        self.table.setVisible(n > 0)
        self.empty.setVisible(n == 0)
        self.empty.setText(self.win.load_error if self.win.load_error else
                           "No remote selected. Create one with New remote." if not d else
                           "No keys match your search." if q else
                           "This remote has no keys yet. Use Add key, or record them in Clone remote.")

    def sel(self):
        r = self.table.currentRow()
        return self.table.item(r, 0).text() if r >= 0 else None

    def key_menu(self, pos):
        if self.table.itemAt(pos) is None:
            return
        self.table.selectRow(self.table.itemAt(pos).row())
        m = QMenu(self)
        for text, fn in [("Test send", self.test_key), ("Edit…", self.edit_key), ("Rename…", self.ren_key),
                         ("Duplicate", self.dup_key), ("Re-learn", self.relearn)]:
            m.addAction(text, fn)
        m.addSeparator()
        m.addAction("Delete", self.del_key)
        m.exec_(self.table.viewport().mapToGlobal(pos))

    def save_notes(self):
        d = self.win.data()
        if d is not None and d.get("notes", "") != self.notes.text():
            d["notes"] = self.notes.text()
            self.win.put(d)

    # remotes ------------------------------------------------------------
    def ren_remote(self):
        old = self.win.current
        if not old:
            return
        n, ok = QInputDialog.getText(self, "Rename remote", "New name:", text=old)
        n = Store.safe_name(n)
        if ok and n and n != old:
            if self.win.store.exists(n):
                QMessageBox.information(self, "Remote exists", "A remote with that name already exists.")
                return
            self.win.store.rename(old, n)
            self.win.current = n
            self.undo = [(n if r == old else r, s) for r, s in self.undo]
            self.win.refresh_all()

    def dup_remote(self):
        old = self.win.current
        if not old:
            return
        n, ok = QInputDialog.getText(self, "Duplicate remote", "Name of the copy:", text=old + "_copy")
        n = Store.safe_name(n)
        if ok and n and self.win.store.exists(n):
            QMessageBox.information(self, "Remote exists", "A remote with that name already exists.")
            return
        if ok and n:
            self.win.store.duplicate(old, n)
            self.win.current = n
            self.win.refresh_all()

    def del_remote(self):
        n = self.win.current
        if n and confirm(self, "Delete remote", f"Delete “{n}” and all its keys? This cannot be undone."):
            self.win.store.delete(n)
            self.undo = [(r, s) for r, s in self.undo if r != n]
            self.win.current = None
            self.win.refresh_all()

    def imp(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import remote", "", "JSON (*.json)")
        if not p:
            return
        try:
            data = Store.normalize(json.loads(Path(p).read_text(encoding="utf-8")))
        except Exception as e:
            QMessageBox.warning(self, "Import failed", f"This file is not a valid remote: {e}")
            return
        name = Store.safe_name(Path(p).stem)
        if not name:
            QMessageBox.warning(self, "Import failed", "The file name has no usable characters.")
            return
        dest = self.win.store.path(name)
        if dest.exists() and not confirm(self, "Replace remote", f"A remote named “{name}” already exists. "
                                         "Replace it?", "Replace"):
            return
        self.win.store.save(name, data)
        self.win.current = name
        self.win.refresh_all()

    def exp(self):
        n = self.win.current
        if not n:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export remote", f"{n}.json", "JSON (*.json)")
        if p:
            shutil.copy(self.win.store.path(n), p)

    # keys ---------------------------------------------------------------
    def add_key(self):
        if not self.win.current:
            self.msg.setText("Create a remote first.")
            return
        dlg = EditDialog(parent=self)
        if dlg.exec_():
            if dlg.key in self.win.data()["keys"]:
                QMessageBox.information(self, "Key exists", f"{dlg.key} already exists in this remote. "
                                        "Edit that key or pick a different name.")
                return
            self.mutate(lambda d: d["keys"].__setitem__(dlg.key, dlg.code))

    def edit_key(self):
        k = self.sel()
        if not k:
            return
        dlg = EditDialog(k, self.win.data()["keys"][k], self)
        if dlg.exec_():
            if dlg.key != k and dlg.key in self.win.data()["keys"]:
                QMessageBox.information(self, "Key exists", f"{dlg.key} already exists in this remote.")
                return
            def apply(d):
                # keep key order: replace in place
                d["keys"] = {(dlg.key if x == k else x): (dlg.code if x == k else v)
                             for x, v in d["keys"].items()}
            self.mutate(apply)

    def ren_key(self):
        k = self.sel()
        if not k:
            return
        n, ok = QInputDialog.getText(self, "Rename key", "New name:", text=k)
        n = Store.key_name(n)
        if ok and n and n != k:
            if n in self.win.data()["keys"]:
                QMessageBox.information(self, "Key exists", f"{n} already exists in this remote.")
                return
            self.mutate(lambda d: d.__setitem__("keys", {(n if x == k else x): v
                                                         for x, v in d["keys"].items()}))

    def dup_key(self):
        k = self.sel()
        if not k:
            return
        def apply(d):
            name = k + "_COPY"
            i = 2
            while name in d["keys"]:
                name, i = f"{k}_COPY{i}", i + 1
            d["keys"][name] = copy.deepcopy(d["keys"][k])
        self.mutate(apply)

    def del_key(self):
        k = self.sel()
        if k and confirm(self, "Delete key", f"Delete {k}? You can undo this with Ctrl+Z."):
            self.mutate(lambda d: d["keys"].pop(k, None))
            self.msg.setText(f"Deleted {k}. Press Ctrl+Z to undo.")

    def test_key(self):
        k = self.sel()
        if not k or self.send_thread or not self.win.ensure_connected(TX):
            return
        self.send_thread = SendWorker(self.win.bridge, self.win.data()["keys"][k], label=k)
        self.send_thread.sent.connect(lambda l, r: self.sent(f"Sent {l}." if r.startswith("OK")
                                                             else f"{l}: sender replied {r or 'nothing'}"))
        self.send_thread.failed.connect(lambda l, e: self.sent(f"{l}: {e}"))
        self.send_thread.start()

    def sent(self, text):
        t, self.send_thread = self.send_thread, None
        if t:
            t.wait(1000)
        self.msg.setText(text)

    def relearn(self):
        k = self.sel()
        if k:
            self.win.goto("clone")
            self.win.pages["clone"].prefill(k)
