"""pytest 根 conftest。

存在即让 pytest 把仓库根目录加入 sys.path，使 `app` 包在
`.venv/bin/pytest` 直接调用时也可导入（console script 不会自动加入 CWD）。
"""

import os
import sys

# 测试必须离线且可重复，即使开发者本地 `.env` 配置了真实搜索。
# 真实模式用手动启动服务或单独的集成测试验证，不让 pytest 产生外部调用。
os.environ["RESEARCH_MODE"] = "mock"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
