.PHONY: install install-dev test lint run clean help check

# Auto-detect Python with required dependencies (pydantic)
PYTHON ?= $(shell python3 -c "import pydantic" 2>/dev/null && echo python3 || echo /Library/Frameworks/Python.framework/Versions/3.10/bin/python3)

# 默认目标
help:
	@echo "OpenBoss - 主从架构分布式 Agent 自动化执行系统"
	@echo ""
	@echo "可用命令:"
	@echo "  make install      - 安装运行时依赖"
	@echo "  make install-dev  - 安装运行时 + 开发依赖"
	@echo "  make test         - 运行测试"
	@echo "  make check        - 一键校验 (tsc + vitest + pytest)"
	@echo "  make lint         - 代码规范检查 (ruff)"
	@echo "  make run          - 启动系统"
	@echo "  make clean        - 清理构建产物和缓存"

# 安装运行时依赖
install:
	pip install -r requirements.txt

# 安装运行时 + 开发依赖
install-dev:
	pip install -e ".[dev]"

# 运行测试
test:
	$(PYTHON) -m pytest tests/ -v --tb=short

# 一键校验: TypeScript + Vitest + Pytest 全量
check:
	@echo "=== 1/3 TypeScript ==="
	cd frontend && npx tsc --noEmit
	@echo ""
	@echo "=== 2/3 Vitest ==="
	cd frontend && npx vitest run
	@echo ""
	@echo "=== 3/3 Pytest ==="
	$(PYTHON) -m pytest tests/ -q
	@echo ""
	@echo "check passed"

# 代码规范检查
lint:
	ruff check agent_automation_system/ tests/

# 启动系统
run:
	python -m agent_automation_system

# 清理构建产物和缓存
clean:
	rm -rf __pycache__/ *.pyc *.pyo
	rm -rf agent_automation_system/__pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info/
	@echo "清理完成 ✅"
