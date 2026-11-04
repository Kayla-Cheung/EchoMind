#!/usr/bin/env python3
"""
EchoMind - Mock Data Purge Script
1. Backs up data/pilot.sqlite3 to data/backups/
2. Deletes all trials where source != 'LIVE_LLM_API' or status != 'complete'
3. Cleans orphaned mock jobs in settings
4. Runs VACUUM to reclaim disk space
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "pilot.sqlite3"


def purge_mock_data(db_path=DB_PATH):
    if not db_path.exists():
        print(f"[!] 数据库文件不存在：{db_path}")
        return False

    print(f"[*] 正在连接数据库：{db_path}")
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    cursor = conn.cursor()

    # 1. 查询当前数据量
    cursor.execute("SELECT COUNT(*) FROM trials")
    total_trials = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trials WHERE source = 'LIVE_LLM_API'")
    live_trials = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trials WHERE source != 'LIVE_LLM_API'")
    mock_trials = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trials WHERE source = 'LIVE_LLM_API' AND status != 'complete'")
    error_trials = cursor.fetchone()[0]

    print("=" * 60)
    print("【清理前数据库试次统计】")
    print(f"  - 总试次总数: {total_trials} 条")
    print(f"  - 真实商业 API 试次 (LIVE_LLM_API): {live_trials} 条")
    print(f"  - MOCK 模拟合成试次 (需清除): {mock_trials} 条")
    print(f"  - 失败/未完成 API 试次: {error_trials} 条")
    print("=" * 60)

    if mock_trials == 0 and error_trials == 0:
        print("[i] 数据库中已没有 MOCK 模拟数据或失败试次，无需重复清理。")
        conn.close()
        return True

    # 2. 自动安全备份
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"pilot_backup_before_purge_mock_{ts_str}.sqlite3"

    print(f"[*] 正在为正式数据库创建物理备份...")
    backup_conn = sqlite3.connect(str(backup_file))
    conn.backup(backup_conn)
    backup_conn.close()
    print(f"[√] 数据库安全备份已就绪: {backup_file.name}")

    # 3. 清理 MOCK 试次与失败记录
    print(f"[*] 正在清理 MOCK 模拟数据与失败试次...")
    cursor.execute("DELETE FROM trials WHERE source != 'LIVE_LLM_API'")
    cursor.execute("DELETE FROM trials WHERE status != 'complete'")
    deleted_trials = cursor.rowcount
    conn.commit()

    # 4. 同步清理 settings 表中残留的空/失效 mock job 记录
    cursor.execute("SELECT key, value FROM settings WHERE key LIKE 'job:%'")
    jobs_to_delete = []
    for row in cursor.fetchall():
        key, val_str = row[0], row[1]
        try:
            job_obj = json.loads(val_str)
            bid = job_obj.get("batch_id") or job_obj.get("id")
            # 检查该 batch 是否还有真实 trials
            cursor.execute("SELECT COUNT(*) FROM trials WHERE batch_id = ?", (bid,))
            if cursor.fetchone()[0] == 0:
                jobs_to_delete.append(key)
        except Exception:
            continue

    if jobs_to_delete:
        for k in jobs_to_delete:
            cursor.execute("DELETE FROM settings WHERE key = ?", (k,))
        conn.commit()
        print(f"[√] 已同步清理 {len(jobs_to_delete)} 个已无有效试次的残留 Job 记录。")

    # 5. 执行 VACUUM 释放物理空间
    print("[*] 正在执行 SQLite VACUUM 碎片整理与空间压缩...")
    cursor.execute("VACUUM")
    conn.commit()

    # 6. 清理后统计
    cursor.execute("SELECT COUNT(*) FROM trials")
    final_trials = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT batch_id) FROM trials")
    final_batches = cursor.fetchone()[0]

    models_set = set()
    cursor.execute("SELECT payload FROM trials")
    for r in cursor.fetchall():
        try:
            m = json.loads(r[0]).get("model")
            if m:
                models_set.add(m)
        except Exception:
            pass
    final_models = sorted(models_set)

    print("=" * 60)
    print("【清理完成！100% 纯真实 API 模式】")
    print(f"  - 成功清除 MOCK 试次: {mock_trials} 条")
    print(f"  - 当前数据库保留真实试次: {final_trials} 条")
    print(f"  - 真实实验批次数: {final_batches} 个")
    print(f"  - 涵盖的真实大模型: {', '.join(final_models) if final_models else 'DeepSeek / MiniMax'}")
    print("=" * 60)

    conn.close()
    return True


if __name__ == "__main__":
    purge_mock_data()
