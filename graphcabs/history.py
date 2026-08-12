"""Simple dialog for past game run stats."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from graphcabs.db import fetch_game_runs, fetch_totals


def _format_started(iso_text):
    if not iso_text:
        return "—"
    try:
        return iso_text.replace("T", " ")[:16]
    except (TypeError, ValueError):
        return iso_text


def _format_result(reason):
    if reason == "game_over":
        return "Game over"
    if reason == "quit":
        return "Quit"
    return reason or "—"


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Past Games")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        totals = fetch_totals()
        games = int(totals.get("games") or 0)
        if games == 0:
            summary = QLabel("No finished games yet. Play a session and close the app to save your first run.")
            summary.setWordWrap(True)
            layout.addWidget(summary)
        else:
            summary = QLabel(
                f"Games played: {games}  ·  "
                f"Total earned (all runs): ₾{totals.get('all_earned', 0):.2f}  ·  "
                f"Best run: ₾{totals.get('best_earned', 0):.2f}  ·  "
                f"Longest survival: {int(totals.get('best_days', 0))} full day(s)  ·  "
                f"Rides completed: {int(totals.get('all_rides', 0))}"
            )
            summary.setWordWrap(True)
            layout.addWidget(summary)

        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(
            ["When", "Days", "Earned", "Final ₾", "Rides", "Fleet", "Result"]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        for run in fetch_game_runs():
            row = table.rowCount()
            table.insertRow(row)
            days_text = f"{run['days_completed']} done (day {run['days_reached']})"
            rides_text = f"{run['rides_completed']} ✓ / {run['rides_missed']} ✗"
            values = [
                _format_started(run.get("started_at")),
                days_text,
                f"₾{run['total_earned']:.2f}",
                f"₾{run['final_money']:.2f}" if run.get("final_money") is not None else "—",
                rides_text,
                str(run.get("fleet_size", "—")),
                _format_result(run.get("end_reason")),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

        layout.addWidget(table)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)


def show_history_dialog(parent=None):
    HistoryDialog(parent).exec_()
