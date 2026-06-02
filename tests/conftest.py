"""
OpenBoss 全局测试配置（conftest.py）

提供通用 fixture，所有测试文件共享。
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def project_root() -> Path:
    """项目根目录路径"""
    return PROJECT_ROOT


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """创建一个临时的项目目录结构，模拟运行时环境"""
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    backup_dir = tmp_path / "data" / "backup"

    data_dir.mkdir()
    logs_dir.mkdir()
    backup_dir.mkdir()

    yield tmp_path


@pytest.fixture
def sample_task_data() -> dict:
    """返回一个标准的 task.json 样本数据"""
    return {
        "project_name": "test_project",
        "created_by": "PM-Agent",
        "created_at": "2026-05-15T00:00:00Z",
        "total_tasks": 2,
        "tasks": [
            {
                "id": "T001",
                "title": "创建项目结构",
                "description": "初始化项目目录和基础文件",
                "bdd": {
                    "given": "项目目录不存在",
                    "when": "执行项目初始化",
                    "then": "项目目录和基础文件被创建",
                },
                "test_script": "tests/test_init.py",
                "dependencies": [],
                "suggested_role": "dev",
                "priority": "P0",
                "status": "pending",
            },
            {
                "id": "T002",
                "title": "配置 CI 流水线",
                "description": "创建 CI 配置文件",
                "bdd": {
                    "given": "项目结构已创建",
                    "when": "添加 CI 配置",
                    "then": "CI 流水线可正常运行",
                },
                "test_script": "tests/test_ci.py",
                "dependencies": ["T001"],
                "suggested_role": "dev",
                "priority": "P1",
                "status": "pending",
            },
        ],
    }


@pytest.fixture
def sample_progress_entry() -> dict:
    """返回一个标准的 progress.txt 条目数据"""
    return {
        "task_id": "T001",
        "status": "completed",
        "role": "dev",
        "started": "2026-05-15T10:00:00Z",
        "finished": "2026-05-15T10:30:00Z",
        "git_sha": "abc1234",
        "git_msg": "[task-T001] dev: 创建项目结构",
        "error": None,
        "retry": 0,
    }
