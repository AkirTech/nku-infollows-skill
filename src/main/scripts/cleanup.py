"""
Clean up generated temporary files.

Removes all files in the TEMP_DIR (articles JSON, state files, HTML).
Safe: never deletes outside of TEMP_DIR.
"""
import sys
import os
from pathlib import Path

from config import TEMP_DIR, print_header, print_ok, print_info


def cleanup() -> dict:
    """
    Delete all files in TEMP_DIR. Returns a summary dict.
    """
    removed = []
    failed = []
    total_size = 0

    if not TEMP_DIR.exists():
        return {"removed": [], "failed": [], "total_size": 0}

    for item in TEMP_DIR.iterdir():
        try:
            if item.is_file():
                size = item.stat().st_size
                total_size += size
                item.unlink()
                removed.append({"name": item.name, "size": size})
            elif item.is_dir():
                # Remove directory and all contents
                dir_size = sum(
                    f.stat().st_size for f in item.rglob("*") if f.is_file()
                )
                import shutil
                shutil.rmtree(item)
                total_size += dir_size
                removed.append({"name": item.name + "/", "size": dir_size})
        except Exception as e:
            failed.append({"name": item.name, "error": str(e)})

    return {
        "removed": removed,
        "failed": failed,
        "total_size": total_size,
    }


def format_size(size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main() -> int:
    print_header("清理临时文件")

    if not TEMP_DIR.exists():
        print_info("临时目录不存在，无需清理")
        return 0

    result = cleanup()

    if not result["removed"] and not result["failed"]:
        print_info("没有需要清理的文件")
        return 0

    for item in result["removed"]:
        print_ok(f"已删除: {item['name']} ({format_size(item['size'])})")

    for item in result["failed"]:
        print(f"  [WARN] 无法删除: {item['name']} - {item['error']}")

    total = format_size(result["total_size"])
    count = len(result["removed"])
    print_info(f"清理完成: 删除了 {count} 个文件/目录，释放 {total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
