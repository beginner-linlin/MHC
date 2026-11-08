# scripts/ —— 部署与调试脚本全集

按编号排列即完整执行历程（WSL Ubuntu 内 `bash /mnt/c/.../scripts/NN.sh` 调用）。

## 核心脚本（部署一个新环境只需这些）

| 脚本 | 作用 |
|---|---|
| `01_extract.sh` | 解压三个工具 tar.gz 到 /opt/bio |
| `02_survey.sh`–`08_net_check.sh` | 归档勘查、launcher 分析、README 提取、数据归属确认 |
| `09_configure.sh` | **关键**：改三个 launcher 的 NMHOME、建 tmp 目录、装 stabpan 的 data |
| `110_deploy_app.sh` | **关键**：把 mhc-app/ 部署到 /opt/bio/app（语法检查 + 拷贝 + 冒烟） |
| `120_sync_static.sh` | 改代码后同步到 WSL 并重启后端（日常迭代用） |

## 测试脚本

| 脚本 | 作用 |
|---|---|
| `65_regression.sh` | 三工具 13 项回归 |
| `111_e2e_test.sh` | 后端 API 端到端 10 组 |
| `130_real_scenarios.sh` | 真实蛋白场景 33 项 |
| `133_validate_mode_aware.sh` | 模式感知校验 9 项 |
| `96_bench.sh` / `102_latency.sh` | 性能基线 |
| `98–100_edge*.sh` | 输入边界行为实测 |

## 其余编号

10–64、66–95、101、112–132：调试过程中定位 `-pmhc` 打包缺陷、netchop TMPDIR、stabpan `-ia` 兼容层、E2E 四问题、等位基因全量加载、双击启动编码问题等的探针与修复脚本 —— 保留作为问题定位记录，对应根因分析见 `docs/安装与调试报告.md`。
