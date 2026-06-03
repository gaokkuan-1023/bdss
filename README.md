# 公司联系电话爬虫 - Company Contact Crawler

> ⚠️ **免责声明：** 本工具仅供合法的商业调研和企业信息收集使用。用户使用本工具获取信息时，应遵守《个人信息保护法》及相关法律法规。**禁止**用于非法获取个人信息、骚扰、诈骗或任何违法违规行为。使用者应自行承担全部法律责任。

支持搜索引擎：百度、谷歌、必应、搜狗、百度地图
基于 DrissionPage + Playwright 双引擎

## 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 使用

```bash
# 使用默认搜索引擎（百度）搜索单个公司
python main.py "深圳腾讯计算机系统有限公司"

# 指定搜索引擎
python main.py "阿里巴巴" --engine baidu
python main.py "Alibaba" --engine google
python main.py "华为" --engine bing

# 指定输出文件
python main.py "字节跳动" -o result.json

# 从文件批量搜索（每行一个公司名）
python main.py -f companies.txt

# 显示所有找到的电话
python main.py "小米科技" --verbose

# 多引擎合并搜索（推荐，自动去重）
python main.py "山东华派集团有限公司" --all --max 5 -v -o result.json

# 设置请求间隔（毫秒），避免触发反爬
python main.py "腾讯" --delay 2000
```

## 支持的搜索引擎

| 引擎 | 类名 | 反爬难度 | 需要代理 | 说明 |
|------|------|---------|---------|------|
| baidu | BaiduSearch | 中 | 否 | 主搜索引擎，含手机版补充 |
| google | GoogleSearch | 高 | 是 | 境外搜索，需代理 |
| bing | BingSearch | 低 | 否 | 微软必应中文版 |
| sogou | SogouSearch | 中 | 否 | 搜狗搜索 |
| baidumap | 函数调用 | 低 | 否 | 百度地图POI查询（API+页面双通道） |

## 项目结构

```
bdss/
├── main.py              # 入口
├── requirements.txt     # 依赖
├── Dockerfile           # Docker 容器化
├── LICENSE              # MIT 开源协议
├── skills/
│   ├── base.py          # 搜索引擎基类 (Playwright)
│   ├── baidu.py         # 百度
│   ├── baidumap.py      # 百度地图 POI
│   ├── google.py        # 谷歌
│   ├── bing.py          # 必应
│   └── sogou.py         # 搜狗
├── extractors/
│   ├── __init__.py
│   └── phone.py         # 电话号码提取器
└── utils/
    ├── __init__.py
    └── helpers.py       # 辅助函数（日志、CSV导出等）
```
