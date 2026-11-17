"""健康檢查與後台統計（資料筆數、資料表關係）。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter

from ..config import DATA_SOURCE, DISCLAIMER
from ..db import db

router = APIRouter(prefix="/api", tags=["系統"])

TABLES = [
    ("accident", "事故"), ("party", "當事人"), ("hotspot", "危險路口"), ("cause_code", "肇因代碼"),
    ("collision_type", "事故型態代碼"), ("import_batch", "匯入批次"),
    ("model_version", "AI 模型版本"), ("prediction", "AI 預測紀錄"), ("shared_route", "家人分享路線"),
]


@router.get("/health", summary="健康檢查")
def health() -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        with db.conn() as connection:
            connection.execute("SELECT 1").fetchone()
            database_version = connection.execute("SHOW server_version").fetchone()["server_version"]
        database_ok = True
        error_message = None
    except Exception as e:  # noqa: BLE001 — 健康檢查要回報任何錯誤
        database_ok = False
        error_message = str(e)
        database_version = None
    return {
        "status": "ok" if database_ok else "error",
        "database": {
            "ok": database_ok,
            "version": database_version,
            "error": error_message,
            "postgis": db.postgis,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        },
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "api_version": "0.1.0",
    }


@router.get("/meta", summary="App 顯示用的說明文字")
def meta() -> dict[str, Any]:
    return {"disclaimer": DISCLAIMER, "data_source": DATA_SOURCE}


@router.get("/admin/stats", summary="後台：各資料表筆數與關係")
def stats() -> dict[str, Any]:
    with db.conn() as connection:
        table_counts = []
        for table_name, label in TABLES:
            row_count = connection.execute(f"SELECT count(*) AS n FROM {table_name}").fetchone()["n"]
            table_counts.append({"table": table_name, "label": label, "rows": row_count})
        relations = connection.execute("""
            SELECT tc.table_name AS child, kcu.column_name AS column, ccu.table_name AS parent
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
              AND tc.table_name <> 'user_report' AND ccu.table_name <> 'user_report'
            ORDER BY child, kcu.column_name""").fetchall()
        monthly_counts = connection.execute("""SELECT year, month, count(*) AS n FROM accident GROUP BY year, month
                              ORDER BY year, month""").fetchall()
    monthly_report = []
    for month in monthly_counts:
        label = f"{month['year'] - 1911}/{month['month']:02d}"
        monthly_report.append({"label": label, "n": month["n"]})
    return {"tables": table_counts, "relations": relations,
            "monthly": monthly_report,
            "postgis": db.postgis, "data_source": DATA_SOURCE}
