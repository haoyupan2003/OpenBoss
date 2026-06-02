"""
P2-022 测试 — BDDMapper BDD 场景到 Task 完整映射

测试内容：
- BDDScenario → BDDSpec 映射
- BDDSpec → dict 序列化
- dict → BDDSpec 反序列化
- 空字段校验
- BDD → Task 完整链路
- to_text / from_text
"""

import pytest

from agent_automation_system.scheduler.bdd_mapper import BDDMapper
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority, TaskStatus
from agent_automation_system.models.bdd import BDDScenario


class TestBDDMapperScenarioToSpec:
    """BDDScenario → BDDSpec"""

    def test_scenario_to_spec(self):
        s = BDDScenario(
            title="登录成功", given="用户在登录页",
            when="输入正确密码", then="跳转首页",
        )
        spec = BDDMapper.scenario_to_spec(s)
        assert isinstance(spec, BDDSpec)
        assert spec.given == "用户在登录页"
        assert spec.when == "输入正确密码"
        assert spec.then == "跳转首页"

    def test_scenario_to_spec_strips_whitespace(self):
        s = BDDScenario(
            title="测试", given="  前后空格  ",
            when="  when  ", then="then",
        )
        spec = BDDMapper.scenario_to_spec(s)
        assert spec.given == "前后空格"

    def test_scenario_none_raises(self):
        with pytest.raises(ValueError, match="scenario"):
            BDDMapper.scenario_to_spec(None)


class TestBDDMapperSpecToDict:
    """BDDSpec → dict"""

    def test_spec_to_dict(self):
        spec = BDDSpec(given="G", when="W", then="T")
        d = BDDMapper.spec_to_dict(spec)
        assert d == {"given": "G", "when": "W", "then": "T"}

    def test_spec_none_returns_none(self):
        assert BDDMapper.spec_to_dict(None) is None

    def test_roundtrip_spec_to_dict_back(self):
        spec = BDDSpec(given="前置", when="动作", then="结果")
        d = BDDMapper.spec_to_dict(spec)
        spec2 = BDDMapper.dict_to_spec(d)
        assert spec2.given == spec.given
        assert spec2.when == spec.when
        assert spec2.then == spec.then


class TestBDDMapperDictToSpec:
    """dict → BDDSpec"""

    def test_dict_to_spec(self):
        d = {"given": "G", "when": "W", "then": "T"}
        spec = BDDMapper.dict_to_spec(d)
        assert isinstance(spec, BDDSpec)
        assert spec.given == "G"
        assert spec.when == "W"
        assert spec.then == "T"

    def test_dict_empty_fields_default_to_empty_string(self):
        d = {}
        spec = BDDMapper.dict_to_spec(d)
        assert spec.given == ""
        assert spec.when == ""
        assert spec.then == ""

    def test_dict_none_returns_none(self):
        assert BDDMapper.dict_to_spec(None) is None

    def test_dict_not_dict_returns_none(self):
        assert BDDMapper.dict_to_spec("not a dict") is None

    def test_dict_partial_fields(self):
        d = {"given": "只有given"}
        spec = BDDMapper.dict_to_spec(d)
        assert spec.given == "只有given"
        assert spec.when == ""
        assert spec.then == ""


class TestBDDMapperSpecToText:
    """BDDSpec → 文本"""

    def test_spec_to_text(self):
        spec = BDDSpec(given="用户在登录页", when="输入密码", then="跳转首页")
        text = BDDMapper.spec_to_text(spec)
        assert "Given: 用户在登录页" in text
        assert "When: 输入密码" in text
        assert "Then: 跳转首页" in text

    def test_spec_to_text_none_returns_empty(self):
        assert BDDMapper.spec_to_text(None) == ""

    def test_text_to_spec_roundtrip(self):
        spec = BDDSpec(given="G", when="W", then="T")
        text = BDDMapper.spec_to_text(spec)
        spec2 = BDDMapper.text_to_spec(text)
        assert spec2.given == "G"
        assert spec2.when == "W"
        assert spec2.then == "T"


class TestBDDMapperValidation:
    """校验"""

    def test_is_valid_true(self):
        spec = BDDSpec(given="G", when="W", then="T")
        assert BDDMapper.is_valid(spec) is True

    def test_is_valid_false_empty_given(self):
        spec = BDDSpec(given="", when="W", then="T")
        assert BDDMapper.is_valid(spec) is False

    def test_is_valid_false_empty_when(self):
        spec = BDDSpec(given="G", when="", then="T")
        assert BDDMapper.is_valid(spec) is False

    def test_is_valid_false_empty_then(self):
        spec = BDDSpec(given="G", when="W", then="")
        assert BDDMapper.is_valid(spec) is False

    def test_is_valid_none_returns_false(self):
        assert BDDMapper.is_valid(None) is False

    def test_is_valid_whitespace_only(self):
        spec = BDDSpec(given="  ", when="W", then="T")
        assert BDDMapper.is_valid(spec) is False


class TestBDDMapperTaskIntegration:
    """Task 集成 — 写入/读取 task.bdd"""

    def test_attach_spec_to_task(self):
        task = Task(
            id="task-001", title="登录", description="实现登录",
            dependencies=[], status=TaskStatus.PENDING,
        )
        spec = BDDSpec(given="G", when="W", then="T")
        BDDMapper.attach_to_task(task, spec)
        assert task.bdd is spec

    def test_extract_spec_from_task(self):
        spec = BDDSpec(given="G", when="W", then="T")
        task = Task(
            id="task-001", title="登录", description="实现登录",
            bdd=spec, dependencies=[], status=TaskStatus.PENDING,
        )
        extracted = BDDMapper.extract_from_task(task)
        assert extracted is spec

    def test_extract_from_task_no_bdd(self):
        task = Task(
            id="task-001", title="无BDD", description="desc",
            dependencies=[], status=TaskStatus.PENDING,
        )
        assert BDDMapper.extract_from_task(task) is None

    def test_task_has_bdd_true(self):
        task = Task(
            id="task-001", title="T", description="D",
            bdd=BDDSpec(given="G", when="W", then="T"),
            dependencies=[], status=TaskStatus.PENDING,
        )
        assert BDDMapper.task_has_bdd(task) is True

    def test_task_has_bdd_false(self):
        task = Task(
            id="task-001", title="T", description="D",
            dependencies=[], status=TaskStatus.PENDING,
        )
        assert BDDMapper.task_has_bdd(task) is False


class TestBDDMapperScenarioListToSpecs:
    """批量 BDDScenario → BDDSpec 列表"""

    def test_scenarios_to_specs(self):
        scenarios = [
            BDDScenario(title="S1", given="G1", when="W1", then="T1"),
            BDDScenario(title="S2", given="G2", when="W2", then="T2"),
        ]
        specs = BDDMapper.scenarios_to_specs(scenarios)
        assert len(specs) == 2
        assert specs[0].given == "G1"
        assert specs[1].given == "G2"

    def test_empty_scenarios(self):
        assert BDDMapper.scenarios_to_specs([]) == []

    def test_scenarios_to_specs_none_returns_empty(self):
        assert BDDMapper.scenarios_to_specs(None) == []
