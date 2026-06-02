#!/usr/bin/env python3
"""
OpenBoss 数据目录初始化脚本

创建运行时所需的 data/ 目录结构：
  data/           - 运行时数据（task.json, progress.txt, memory.md）
  data/backup/    - 数据备份目录
  logs/           - 日志目录
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

DIRS = [
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "data" / "backup",
    PROJECT_ROOT / "logs",
]

GITKEEP_DIRS = [
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "data" / "backup",
    PROJECT_ROOT / "logs",
]


def init_dirs() -> list[Path]:
    """创建所有数据目录并添加 .gitkeep 占位文件

    Returns:
        创建的目录列表
    """
    created = []
    for dir_path in DIRS:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            created.append(dir_path)
            print(f"  创建目录: {dir_path.relative_to(PROJECT_ROOT)}")
        else:
            print(f"  已存在:   {dir_path.relative_to(PROJECT_ROOT)}")

    # 在 gitkeep 目录中添加 .gitkeep
    for dir_path in GITKEEP_DIRS:
        gitkeep = dir_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
            print(f"  创建占位: {gitkeep.relative_to(PROJECT_ROOT)}")

    return created


if __name__ == "__main__":
    print("OpenBoss 数据目录初始化")
    print("-" * 30)
    created = init_dirs()
    print("-" * 30)
    if created:
        print(f"新建 {len(created)} 个目录")
    else:
        print("所有目录已就绪，无需创建")
