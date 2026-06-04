# BDSS — 公司联系电话爬虫 & 招标监控

> ⚠️ **免责声明：** 本工具仅供合法的商业调研和企业信息收集使用。用户使用本工具获取信息时，应遵守《个人信息保护法》及相关法律法规。**禁止**用于非法获取个人信息、骚扰、诈骗或任何违法违规行为。使用者应自行承担全部法律责任。

BDSS 是一套面向**工业品销售/B2B获客**场景的数据工具包，包含三个核心模块：

| 模块 | 用途 | 数据源 |
|------|------|--------|
| **批量搜电话** | 已知公司名，查最新联系方式 | 百度地图 POI API（主）+ 顺企网（辅） |
| **招标监控** | 按行业关键词，自动扫描招标线索 | 中国政府采购网 + 招标采购导航网 |
| **Web 界面** | 上传 Excel 名单 → 自动搜 → 下载结果 | 集成以上两个模块 |

---

## 快速开始

### 前置配置

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置百度地图 API Key（必填，电话查询的核心数据源）
#    申请地址：https://lbsyun.baidu.com/apiconsole/key
#    创建 .env 文件：
echo 'BAIDU_MAP_AK=你的百度地图AK' >> .env
```

### 启动 Web 界面（推荐）

```bash
cd bdss-app
python app.py
# 浏览器打开 http://localhost:5300
```

| 页面 | 功能 |
|------|------|
| `http://localhost:5300` | 上传公司 Excel → 自动搜电话 → 下载结果 |
| `http://localhost:5300/monitor` | 招标监控面板 → 一键扫描 → 查看线索 |

### 命令行使用

```bash
# 单公司查电话（需百度地图 AK）
python -c "
from skills.lite_search import search_company_phones
r = search_company_phones('华能国际电力股份有限公司德州电厂')
print(r['phones'])
"

# AI 引擎搜索（需配置 AI API Key）
python main.py "深圳腾讯" --engine ai

# 多引擎（Playwright 可选）
python main.py "山东华派" --all --delay 2000
```

---

## 能力对比

| 搜索方式 | 需要 | 速度 | 覆盖 | 适合场景 |
|----------|------|------|------|---------|
| **百度地图 POI** | `BAIDU_MAP_AK` | 2s/家 | ~60% 有电话 | 已知公司名查电话 |
| **AI 引擎** | `BDSS_AI_API_KEY` | 3-5s | 直接回答 | 快速查询 + 验证 |
| **Playwright 引擎** | Chromium 浏览器 | 8-15s | 视情况 | 深度爬取（可选） |

---

## 招标监控

按行业关键词自动扫描招标网站，匹配新线索：

```bash
# 一次性扫描
python -c "from bidding_monitor import scan; r = scan(); print(r)"

# 通过 Web 界面
# http://localhost:5300/monitor → 点"立即扫描"
```

**数据源：**
- 中国政府采购网（ccgp.gov.cn）— POST 搜索
- 招标采购导航网（okcis.cn）— HTML 解析
- 可扩展：更多源在 `bidding_monitor.py` 的 `BIDDING_SOURCES` 配置

---

## 项目结构

```
bdss/
├── main.py              # CLI 入口
├── bidding_monitor.py   # 招标监控引擎 + AI 分析
├── requirements.txt     # 依赖
├── .env.example         # 环境变量模板
├── skills/
│   ├── engines.py       # HTTP 搜索 (Bing/Baidu)
│   ├── lite_search.py   # 全网搜电话
│   ├── ai.py            # AI 引擎 (LLM API)
│   └── baidumap.py      # 百度地图 POI
├── extractors/
│   └── phone.py         # 电话提取器
├── utils/
│   ├── helpers.py       # 工具函数
│   ├── cache.py         # SQLite 缓存
│   └── env.py           # .env 读取
├── tests/
│   └── test_phone_extractor.py
└── bdss-app/            # Web 界面
    ├── app.py           # Flask 服务
    ├── industry_api.py  # 行业拓客 API
    └── templates/
        ├── index.html   # 搜电话页
        ├── monitor.html # 招标监控页
        └── industry.html# 行业拓客页
```

## 运行要求

- Python 3.10+
- 百度地图 API Key（免费申请，电话查询必需）
- (可选) AI API Key（AI 搜索和分析需要）

---

## 许可证

MIT
