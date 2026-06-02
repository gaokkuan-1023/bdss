# 公司联系电话爬虫 - Company Contact Crawler

支持搜索引擎：百度、谷歌、必应、搜狗
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
```

## 支持的搜索引擎

| 引擎 | 类名 | 反爬难度 | 需要代理 |
|------|------|---------|---------|
| baidu | BaiduSearch | 中 | 否 |
| google | GoogleSearch | 高 | 是 |
| bing | BingSearch | 低 | 否 |
| sogou | SogouSearch | 中 | 否 |

## 项目结构

```
company_crawler/
├── main.py              # 入口
├── requirements.txt     # 依赖
├── skills/
│   ├── base.py          # 搜索引擎基类
│   ├── baidu.py         # 百度
│   ├── google.py        # 谷歌
│   ├── bing.py          # 必应
│   └── sogou.py         # 搜狗
├── extractors/
│   └── phone.py         # 电话号码提取器
└── utils/
    └── helpers.py       # 辅助函数
```
