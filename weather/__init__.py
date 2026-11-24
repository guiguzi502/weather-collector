# -*- coding: utf-8 -*-
"""天气数据采集与可视化分析系统。

注意：这里**不要** eager import 各子模块。
``from weather import collector`` 这种写法本身就够用，
而 eager import 会把 matplotlib 拉进每个只用到 cleaner 的测试进程。
"""
__version__ = "1.1.0"