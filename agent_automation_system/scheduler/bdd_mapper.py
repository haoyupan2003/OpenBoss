"""
BDDMapper — BDD 场景到 Task 完整映射

将 BDDScenario ↔ BDDSpec ↔ Task.bdd 完整映射链路。
确保 BDD 数据在 PM → Task → Dev 管道中正确流转。

映射关系：
    BDDScenario (models/bdd.py) → BDDSpec (models/task.py) → Task.bdd
    dict (task.json 格式) ↔ BDDSpec
"""

import re
from typing import Optional

from agent_automation_system.models.task import BDDSpec, Task
from agent_automation_system.models.bdd import BDDScenario


class BDDMapper:
    """BDD 数据映射器 — 纯静态方法工具类"""

    @staticmethod
    def scenario_to_spec(scenario: BDDScenario) -> BDDSpec:
        if scenario is None:
            raise ValueError("scenario cannot be None")
        return BDDSpec(
            given=scenario.given.strip(),
            when=scenario.when.strip(),
            then=scenario.then.strip(),
        )

    @staticmethod
    def scenarios_to_specs(scenarios: Optional[list[BDDScenario]]) -> list[BDDSpec]:
        if not scenarios:
            return []
        return [BDDMapper.scenario_to_spec(s) for s in scenarios]

    @staticmethod
    def spec_to_dict(spec: Optional[BDDSpec]) -> Optional[dict]:
        if spec is None:
            return None
        return {"given": spec.given, "when": spec.when, "then": spec.then}

    @staticmethod
    def dict_to_spec(d: Optional[dict]) -> Optional[BDDSpec]:
        if d is None or not isinstance(d, dict):
            return None
        return BDDSpec(
            given=d.get("given", ""),
            when=d.get("when", ""),
            then=d.get("then", ""),
        )

    @staticmethod
    def spec_to_text(spec: Optional[BDDSpec]) -> str:
        if spec is None:
            return ""
        parts = []
        if spec.given:
            parts.append(f"Given: {spec.given}")
        if spec.when:
            parts.append(f"When: {spec.when}")
        if spec.then:
            parts.append(f"Then: {spec.then}")
        return "\n".join(parts)

    @staticmethod
    def text_to_spec(text: str) -> BDDSpec:
        given = when = then = ""
        for line in text.split("\n"):
            line = line.strip()
            m = re.match(r"Given:\s*(.+)", line, re.IGNORECASE)
            if m:
                given = m.group(1).strip()
                continue
            m = re.match(r"When:\s*(.+)", line, re.IGNORECASE)
            if m:
                when = m.group(1).strip()
                continue
            m = re.match(r"Then:\s*(.+)", line, re.IGNORECASE)
            if m:
                then = m.group(1).strip()
        return BDDSpec(given=given, when=when, then=then)

    @staticmethod
    def is_valid(spec: Optional[BDDSpec]) -> bool:
        if spec is None:
            return False
        return bool(spec.given.strip() and spec.when.strip() and spec.then.strip())

    @staticmethod
    def attach_to_task(task: Task, spec: BDDSpec) -> None:
        task.bdd = spec

    @staticmethod
    def extract_from_task(task: Task) -> Optional[BDDSpec]:
        return task.bdd

    @staticmethod
    def task_has_bdd(task: Task) -> bool:
        return task.bdd is not None
