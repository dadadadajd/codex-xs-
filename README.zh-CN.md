# Amazon 父子 ASIN 审计 Skill

[English](README.md)

这是一个可重复复用的 Codex Skill，用于完成 Amazon 父子 ASIN 的市场、
关键词、广告边界和 Listing 审计，并输出结构化 JSON、可离线打开的单文件
HTML 报告，以及机器可读的交付校验结果。

只使用 Amazon 实时证据也可以运行；如果当前环境可调用 SIF、Sorftime 或
卖家后台连接器，报告会自动加深。缺失数据会明确写成“不可用”，不会被处理
成 0，也不会用旧结果冒充本次取数。

## 解决的核心问题

- 同一父体销量序列被多个子体接口重复返回后错误相加。
- 一个子体的电机、材质、尺寸或承重被复制给兄弟子体。
- 把流量分、广告位或排名当成花费、CPC、订单或 ACOS。
- 把 SIF 和 Sorftime 的不同口径平均成一个“确认值”。
- 当前连接器失败后，悄悄回填历史结果。
- 分享报告时泄露令牌、客户数据或个人发布项目 ID。

Skill 把这些错误固化成证据契约和自动质量门槛。

## 功能

- 父子体范围核对和逐子体行动矩阵。
- Amazon 实时证据及抓取时间标记。
- 可选 SIF、Sorftime 关键词、类目、竞品和需求数据。
- 前台广告观察与 Amazon Ads 后台指标严格分层。
- 重复父体销量序列检测，禁止按子体重复求和。
- 跨来源关键词数据并列展示。
- 响应式、打印友好、无需联网的 HTML 报告。
- ASIN/来源覆盖、占位符和敏感信息自动检查。
- 图片尺寸、比例、真实格式、目标规格的批量检测，以及独立的视觉复核和逐图HTML结果。
- 用户明确授权后的可选公开发布流程。

## 安装

克隆本仓库，将 `skills/amazon-parent-asin-audit` 整个目录复制到你的
Codex Skills 目录，并保持目录名不变。刷新或重启 Codex，使 Skill 列表重新
加载。

脚本也可以在克隆目录中独立执行，要求 Python 3.10 及以上。原有流程仍只用
标准库；图片检测需安装 `skills/amazon-parent-asin-audit/requirements-images.txt`。

## 商品图片与 A+ 素材质检

支持 2000×2000、1600×1600、1464×600、600×450、仅4:3比例及自定义尺寸。
通过清单为每张图配置目标、套图分组、参考实拍、配件、屏显、文字和Logo要求。
完整契约与人工复核记录见[图片质检说明](skills/amazon-parent-asin-audit/references/image-quality.md)。

```sh
python -m pip install -r skills/amazon-parent-asin-audit/requirements-images.txt
python skills/amazon-parent-asin-audit/scripts/audit_images.py --manifest tests/fixtures/images.manifest.json --output tmp/image-quality.json
python skills/amazon-parent-asin-audit/scripts/render_report.py --input tests/fixtures/input.valid.json --evidence tests/fixtures/evidence.conflicting.json --image-manifest tests/fixtures/images.manifest.json --output tmp/images-report.html
python skills/amazon-parent-asin-audit/scripts/validate_delivery.py --input tests/fixtures/input.valid.json --evidence tests/fixtures/evidence.conflicting.json --image-manifest tests/fixtures/images.manifest.json --report tmp/images-report.html
```

报告逐图展示实测值、自动问题及修改建议，并单独列出产品外观、配件结构、
文字标注、Logo、套图一致性、背景扩展的人工复核。提供原图及位置后，可比较
原始区域像素是否保留；只有4:3比例不能证明产品未缩放或裁切。本模块不做
自动OCR、语义识别或Logo检测，不把文件检测通过当作视觉正确。

样例全部是合成几何图片，含一张故意错误尺寸的图片，人工复核均为待确认。
诊断报告可以有效地记录不合格图片。正式交付素材前，在交付校验命令中加入
`--require-image-approval`；独立图片命令使用 `--require-approval`。
复核指纹会随原图、参考图、要求或套图成员变化而失效。原有不带图片参数的
命令保持兼容，也不会声称检查过图片。

## 在 Codex 中使用

示例：

```text
使用 amazon-parent-asin-audit 分析 Amazon 美国站父 ASIN B000000000，
子 ASIN 为 B000000001、B000000002。优先使用 Amazon 实时数据，并在可用时
接入 SIF 和 Sorftime。输出中文离线 HTML，跨来源估算不要合并，本次不发布。
```

如果需要公开分享，请明确写出发布目标，或者直接要求“生成公开可分享链接”。
普通审计请求不会自动触发外部发布。

## 运行脱敏示例

在仓库根目录执行：

```powershell
python skills/amazon-parent-asin-audit/scripts/validate_input.py `
  --input tests/fixtures/input.valid.json

python skills/amazon-parent-asin-audit/scripts/validate_evidence.py `
  --evidence tests/fixtures/evidence.conflicting.json

python skills/amazon-parent-asin-audit/scripts/render_report.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --output tmp/report.html

python skills/amazon-parent-asin-audit/scripts/validate_delivery.py `
  --input tests/fixtures/input.valid.json `
  --evidence tests/fixtures/evidence.conflicting.json `
  --report tmp/report.html
```

测试数据全部为合成数据，不包含客户 ASIN、账号和真实业务信息。

## 输出目录

```text
outputs/<父ASIN>-<站点>-<日期>/
├── input.json
├── evidence.json
├── report.json          # 可选结构化结论
├── report.html
└── validation.json
```

当 `validation.json` 中 `"valid": false` 时，不得交付或发布。

## 数据边界

- SIF 或 Sorftime 不可用：标记不可用，不回填旧数据。
- 没有 Amazon Ads 后台报表：花费、CPC、订单、ACOS、ROAS 和预算保持
  不可用。
- 多个子体返回完全相同的销量序列：只按一个父体估算展示，禁止求和。
- 不同来源关键词数据不一致：保留各自数值、周期和方法差异。
- 没有公开发布目标：只交付通过校验的本地 HTML。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python .github/scripts/validate_skill.py skills/amazon-parent-asin-audit
```

GitHub Actions 会在 Python 3.10 和 3.12 上执行单元测试、Codex Skill 结构
校验、脱敏报告渲染和交付校验。

## 隐私与安全

- 禁止提交连接器令牌、Cookie、JWT、卖家后台原始报表、客户测试数据或个人
  发布项目 ID。
- SIF、Sorftime 等第三方销量与需求数据必须标记为估算。
- 尊重 Amazon 的登录、验证码、额度和访问控制。
- 外部公开发布必须获得用户明确授权。

提交贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)
