"""
冒烟测试：验证 pytest 配置和基础 fixture 是否正常工作
"""


def test_project_root_exists(project_root):
    """验证 project_root fixture 返回有效路径"""
    assert project_root.exists()
    assert project_root.is_dir()


def test_tmp_project_dir_structure(tmp_project_dir):
    """验证 tmp_project_dir fixture 创建了正确的目录结构"""
    assert (tmp_project_dir / "data").exists()
    assert (tmp_project_dir / "logs").exists()
    assert (tmp_project_dir / "data" / "backup").exists()


def test_sample_task_data(sample_task_data):
    """验证 sample_task_data fixture 返回正确结构"""
    assert "project_name" in sample_task_data
    assert "tasks" in sample_task_data
    assert len(sample_task_data["tasks"]) == 2
    assert sample_task_data["tasks"][0]["id"] == "T001"
    assert sample_task_data["tasks"][1]["dependencies"] == ["T001"]


def test_sample_progress_entry(sample_progress_entry):
    """验证 sample_progress_entry fixture 返回正确结构"""
    assert sample_progress_entry["task_id"] == "T001"
    assert sample_progress_entry["status"] == "completed"
    assert sample_progress_entry["retry"] == 0
