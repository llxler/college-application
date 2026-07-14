# 志愿推荐筛选程序

这是一个基于 `table.xlsx` 的本地 Streamlit 工具，用于按批次、科目、类别、分数、位次、专业关键词、学校性质和备注条件筛选院校专业组，并按“冲 / 稳 / 保”生成推荐结果。

页面会固定提示：本系统仅基于往年投档线进行辅助筛选，不能替代官方招生计划和最终录取结果。

## 环境准备

建议使用 Python 3.10 或更高版本。

推荐使用 `uv` 运行：

```bash
uv run --with-requirements requirements.txt streamlit run app.py
```

也可以先用 `pip` 安装依赖：

```bash
pip install -r requirements.txt
```

当前程序不依赖 `openpyxl` 读取源文件，内置了针对 `.xlsx` 的轻量读取和导出逻辑。

## 运行

在项目目录执行：

```bash
streamlit run app.py
```

如果使用 `uv`，执行：

```bash
uv run --with-requirements requirements.txt streamlit run app.py
```

启动后浏览器打开：

```text
http://localhost:8501
```

程序默认读取项目根目录下的：

```text
table.xlsx
```

## 公网分享给朋友

根据使用场景选择一种方式：

| 方式 | 适合场景 | 注意事项 |
| --- | --- | --- |
| Streamlit Community Cloud | 长期给朋友访问，最推荐 | 需要把项目放到 GitHub；如果仓库公开，`table.xlsx` 也会公开 |
| Cloudflare Tunnel | 临时演示，最快 | 你的电脑必须开着，命令停止后链接失效 |
| 自建服务器 | 长期稳定、数据不想放公开平台 | 需要购买服务器并维护 Python/进程/域名 |

### 方式一：Streamlit Community Cloud

这是最推荐的部署方式。部署完成后会得到一个 `https://xxx.streamlit.app` 链接，可以直接发给朋友。

本项目已准备好的 GitHub 仓库：

```text
https://github.com/llxler/college-application
```

在 Streamlit Community Cloud 中填写：

```text
Repository: llxler/college-application
Branch: main
Main file path: app.py
```

也可以使用 “Paste GitHub URL” 填入：

```text
https://github.com/llxler/college-application/blob/main/app.py
```

1. 新建 GitHub 仓库。
2. 上传整个项目目录，至少包含：

```text
app.py
requirements.txt
table.xlsx
admission_recommender/
```

3. 如果不希望 `table.xlsx` 被公开，GitHub 仓库不要设为 public，改用 private repo。
4. 打开：

```text
https://share.streamlit.io
```

5. 使用 GitHub 登录并授权。
6. 如果仓库是 private，需要在 GitHub 授权页允许 Streamlit 访问 `llxler/college-application`。
7. 点击创建应用，选择你的仓库、分支和入口文件。
8. 入口文件填写：

```text
app.py
```

9. Python 版本可使用默认 `3.12`，也可以在 Advanced settings 中选择 `3.13`。
10. 点击 Deploy，等待构建完成。
11. 部署成功后复制生成的 `streamlit.app` 链接发给朋友。

### 方式二：Cloudflare Tunnel 临时分享

适合马上给朋友试用。这个方式不需要上传代码，但必须保持本机服务和 tunnel 命令都在运行。

先启动本地 Streamlit：

```bash
uv run --with-requirements requirements.txt streamlit run app.py --server.port 8501
```

另开一个终端，启动 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://localhost:8501
```

如果没有全局安装 `cloudflared`，也可以把二进制放在项目的 `bin/` 目录，然后执行：

```bash
./bin/cloudflared tunnel --url http://localhost:8501 --no-autoupdate
```

命令运行后会输出一个公网 HTTPS 链接，把这个链接发给朋友即可。

限制：

- 电脑关机、断网或命令停止后，朋友就访问不了。
- 免费临时链接通常是随机域名，不适合作为长期固定入口。

### 方式三：自建服务器

适合长期稳定使用，或者不想把 `table.xlsx` 放到公开仓库。

基本步骤：

1. 购买一台云服务器，例如阿里云、腾讯云或其他 VPS。
2. 安装 Python 和 `uv`。
3. 把项目上传到服务器。
4. 在服务器上运行：

```bash
uv run --with-requirements requirements.txt streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

5. 在云服务器安全组/防火墙中放行 `8501` 端口。
6. 访问：

```text
http://服务器公网IP:8501
```

更正式的做法是使用 Nginx 反向代理到 `8501`，并绑定域名和 HTTPS。

## 使用说明

1. 在左侧选择报考批次。
2. 普通批需要选择首选科目，并勾选学生再选科目。
3. 技能高考批需要选择技能类别。
4. 艺术批需要选择艺术类别。
5. 输入用户总分或位次值；两者都输入时，优先按位次推荐。
6. 可选填写专业关键词，例如“计算机”“护理”“会计”“口腔医学”。
7. 可选选择学校性质，例如公办、民办、中外合作等。
8. 可选设置备注排除项，例如中外合作办学、乡村振兴、专本联合培养、国家专项计划、护理类。
9. 设置每档推荐数量后查看结果表格。
10. 可勾选结果左侧的删除框，再点击“删除选中志愿”。
11. 选择 Excel、PDF 或 JPG 格式后下载；文件名会包含首选科目（或类别）和分数。
12. “位次推荐阈值”底部的说明中提供了计算方式、正负方向、填写格式和示例。

## 推荐规则

位次优先。位次值越小，排名越靠前。

```text
位次差 = 院校专业组往年投档位次 - 用户位次
位次差比例 = 位次差 / 用户位次
```

默认位次阈值：

| 档位 | 规则 |
| --- | --- |
| 冲 | -10% 到 5% |
| 稳 | 大于 5% 到 25% |
| 保 | 大于 25% |

如果只输入分数，则使用分差：

```text
分差 = 用户总分 - 投档最低分
```

默认分数阈值：

| 档位 | 规则 |
| --- | --- |
| 冲 | -10 到 5 分 |
| 稳 | 大于 5 到 20 分 |
| 保 | 大于 20 分 |

页面左侧仅保留位次阈值调整。分数阈值不再展示；只填写分数时仍使用上述固定分差规则完成分档。

## 数据清洗规则

- 第 1 行作为表标题跳过，第 2 行作为字段名。
- 去除字段名里的换行、空格和全角空格。
- `专业` 和 `具体专业` 统一为 `专业信息`。
- `院校专业组` 和 `院校专业组代号` 统一为 `院校专业组代号`。
- 艺术本科表尾部空列会被忽略。
- `投档最低分` 或 `位次值` 缺失的数据标记为“数据不完整”，默认不参与推荐。
- 推荐结果保留原始备注。

## 测试

运行自动测试：

```bash
python -m unittest discover -s tests -v
```

如果使用 `uv`，执行：

```bash
uv run --with-requirements requirements.txt python -m unittest discover -s tests -v
```

测试覆盖：

- 10 个工作表读取和字段清洗。
- 普通批再选科目匹配。
- 技能高考类别和艺术类别筛选。
- 体育批无专业字段时忽略专业关键词。
- 学校性质、专业关键词和备注排除。
- 位次优先、分数-only 推荐、阈值边界。
- 缺失分数或位次的数据不进入推荐。
- Excel、PDF、JPG 导出文件有效性和导出文件名。

## 文件结构

```text
app.py
admission_recommender/
  excel_loader.py
  cleaning.py
  matching.py
  recommendation.py
  exporter.py
  models.py
tests/
  test_recommender.py
requirements.txt
table.xlsx
```
