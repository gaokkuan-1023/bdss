# 公司联系电话爬虫 — Company Phone Finder Skill

通过百度/必应/搜狗等搜索引擎自动搜索公司名称，提取联系电话。

## 功能

- **多引擎搜索**: 百度 + 必应 + 搜狗 三引擎互补
- **自动翻页**: 百度支持 5 页翻页（desktop + 手机版双重策略）
- **验证码处理**: 自动检测百度安全验证，3 次重试 + 上下文切换
- **AI 摘要提取**: 手机版 UA 获取百度企业信息卡片中的电话
- **Stealth 反检测**: 集成 playwright-stealth 隐藏自动化特征
- **地理校验**: 自动识别城市，校验电话区号匹配度
- **结果去重**: 多引擎结果自动合并去重

## 使用

```bash
# 单个引擎
python main.py "公司名称" --engine baidu --max 5 -v

# 多引擎互补（推荐）
python main.py "公司名称" --all --max 5 -o result.json

# 批量搜索
python main.py -f companies.txt --all --max 3

# 查看帮助
python main.py --help
```

## 搜索引擎

| 引擎 | 代码 | 特点 |
|------|------|------|
| 百度 | `baidu` | 国内数据最全，支持翻页 + 手机版 AI 摘要 |
| 必应 | `bing` | 无验证码，国内直连 |
| 搜狗 | `sogou` | 补充搜索 |
| 谷歌 | `google` | 需配置代理 |

## 输出

默认打印到终端，可加 `-o result.json` 输出 JSON：

```json
{
  "company": "山东华派集团有限公司",
  "phones": ["0632-5128868", "0632-5128869", ...],
  "phone_count": 10,
  "engines_run": ["baidu", "bing"],
  "sources": [...],
  "geo_check": {"valid": [...], "suspicious": [...], "cities": ["枣庄"]}
}
```

## 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```
