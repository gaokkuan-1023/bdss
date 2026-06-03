"""
公司联系电话爬虫 - 主入口

支持搜索引擎: baidu / google / bing / sogou / baidumap
多引擎合并搜索: --all (自动并行跑 baidu + bing + sogou，合并结果去重)
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from skills.baidu import BaiduSearch
from skills.google import GoogleSearch
from skills.bing import BingSearch
from skills.sogou import SogouSearch
from skills.baidumap import query_baidu_map_poi as query_map_poi
from extractors.phone import PhoneExtractor
from utils.helpers import save_result, load_companies_from_file, export_csv
from utils.helpers import setup_logger
from utils.cache import SearchCache

logger = logging.getLogger(__name__)

# 搜索词扩展（当初始搜索电话不足时自动补充）
SEARCH_EXPANSIONS = [
    ("{公司} 电话", "加关键词:电话"),
    ("{公司} 联系方式", "加关键词:联系方式"),
    ("{公司} 联系电话", "加关键词:联系电话"),
]

# 来源可信度等级
CONFIDENCE_LEVELS = {
    "搜索引擎结果页": 5,       # AI 摘要/企业信息卡片 → 最高
    "天眼查": 4,
    "企查查": 4,
    "企查猫": 4,
    "爱企查": 4,
    "百度百科": 4,
    "百度地图": 4,
    "BOSS直聘": 3,
    "齐鲁人才网": 3,
    "58同城": 3,
    "政府": 3,
    "默认": 1,                 # 其他页面 → 最低
}

# 搜索引擎注册表
ENGINE_REGISTRY = {
    'baidu': BaiduSearch,
    'google': GoogleSearch,
    'bing': BingSearch,
    'sogou': SogouSearch,
}

# 多引擎合并搜索时默认使用的引擎（跳过 google，需要代理）
MULTI_ENGINES = ['baidu', 'bing', 'sogou']

# 全局缓存实例
_cache = SearchCache()


def search_company(
    company_name: str,
    engine: str = 'baidu',
    max_results: int = 5,
    headless: bool = True,
    proxy: str = None,
    verbose: bool = False,
    delay: int = 0,  # 请求间隔（毫秒）
) -> dict:
    """
    搜索公司并提取联系电话。

    Returns:
        {"company": str, "phones": list[str], "sources": list[dict], ...}
    """
    engine_cls = ENGINE_REGISTRY.get(engine)
    if not engine_cls:
        logger.error(f"不支持的搜索引擎: {engine}")
        return {"company": company_name, "phones": [], "sources": [], "engine": engine}

    crawler = engine_cls(headless=headless, proxy=proxy)
    extractor = PhoneExtractor(prefer_nearby=True)

    all_phones = set()
    sources = []

    try:
        logger.info(f"{'=' * 50}")
        logger.info(f"[搜索] {company_name}  (引擎: {engine})")
        logger.info(f"{'=' * 50}")

        if delay > 0:
            time.sleep(delay / 1000)

        opened_pages, search_page_text = crawler.search_and_open(company_name, max_results=max_results)

        # 从搜索结果页本身提取电话（百度 AI 摘要/企业信息框等）
        search_phones = []
        if search_page_text:
            search_phones = extractor.extract(search_page_text)
            for p in search_phones:
                all_phones.add(p)
                sources.append({
                    'url': f'搜索引擎结果页',
                    'title': f'{engine}搜索结果-{company_name}',
                    'phone': p,
                })
            if search_phones and verbose:
                logger.info(f"  [搜索结果页] 发现电话: {', '.join(search_phones)}")

        # 如果没有从搜索页找到电话（AI 摘要可能没加载），重试一次
        if not search_phones and engine == 'baidu' and headless:
            logger.info(f"  [!] 搜索结果页未找到电话（AI摘要可能未加载），重试搜索...")
            crawler.close()
            opened_pages, search_page_text = [], None
            # 等待后重试
            time.sleep(3)
            crawler2 = engine_cls(headless=headless, proxy=proxy)
            try:
                if delay > 0:
                    time.sleep(delay / 1000)
                opened_pages2, search_page_text2 = crawler2.search_and_open(company_name, max_results=max_results)
                crawler = crawler2
                opened_pages, search_page_text = opened_pages2, search_page_text2
                if search_page_text:
                    search_phones2 = extractor.extract(search_page_text)
                    for p in search_phones2:
                        all_phones.add(p)
                        sources.append({
                            'url': f'搜索引擎结果页',
                            'title': f'{engine}搜索结果-{company_name}',
                            'phone': p,
                        })
                    if search_phones2 and verbose:
                        logger.info(f"\n  [搜索结果页-重试] 发现电话: {', '.join(search_phones2)}")
            except Exception:
                pass

        # 从每个打开页面提取电话
        for page_data in (opened_pages or []):
            if not page_data['page_text']:
                continue
            phones = extractor.extract(page_data['page_text'])
            for p in phones:
                all_phones.add(p)
                sources.append({
                    'url': page_data['url'],
                    'title': page_data['title'],
                    'phone': p,
                })

            if verbose:
                logger.info(f"  [页面] {page_data['title'][:50]}")
                logger.info(f"     URL: {page_data['url']}")
                if phones:
                    for ph in phones:
                        logger.info(f"     [电话] 发现电话: {ph}")
                else:
                    logger.info(f"     [X] 未发现电话")

        # 从搜索结果摘要中提取电话
        for r in opened_pages:
            if r.get('snippet'):
                phones_in_snippet = extractor.extract(r['snippet'])
                for p in phones_in_snippet:
                    all_phones.add(p)

    except Exception as e:
        logger.error(f"执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        crawler.close()

    result = {
        "company": company_name,
        "phones": sorted(all_phones),
        "phone_count": len(all_phones),
        "sources": sources,
        "engine": engine,
    }

    # ===== 地理校验 =====
    try:
        import re
        all_page_texts = [p.get('page_text','') for p in opened_pages if p.get('page_text')] + [search_page_text or '']
        ccd = {'枣庄':['0632'],'济南':['0531'],'青岛':['0532'],'潍坊':['0536'],
               '淄博':['0533'],'德州':['0534'],'烟台':['0535'],'济宁':['0537'],
               '泰安':['0538'],'临沂':['0539'],'菏泽':['0530'],'威海':['0631'],
               '日照':['0633'],'聊城':['0635'],'滨州':['0543']}
        cts = set()
        for t in all_page_texts:
            for m in re.findall(r'([\u4e00-\u9fa5]{2,4})市', t):
                if m in ccd: cts.add(m)
        vc = set()
        for c in cts: vc.update(ccd[c])
        vld, sus = [], []
        for p in all_phones:
            cl = p.replace('-','').replace(' ','')
            if not cl.startswith('0'): vld.append(p); continue
            if not vc: sus.append(p); continue
            if any(cl[:ln] in vc for ln in [4,3]): vld.append(p)
            else: sus.append(p)
        if cts:
            logger.info(f"  [地理校验] 检测到城市: {', '.join(cts)}")
            if sus:
                logger.warning(f"  [可疑] 以下号码区号不匹配: {', '.join(sus)}")
                for s in sus:
                    for src in result['sources']:
                        if src['phone'] == s: src['warning'] = '区号不匹配'
            if vld:
                logger.info(f"  [匹配] {', '.join(vld)}")
        else:
            logger.info(f"  [!] 未检测到城市，跳过区号校验")
        result['geo_check'] = {"valid":vld,"suspicious":sus,"cities":list(cts)}
    except Exception as ge:
        logger.warning(f"  [!] 地理校验异常: {ge}")
        result['geo_check'] = {"valid":[],"suspicious":[],"cities":[]}

    # ===== 搜索词扩展：电话不足时自动补充搜索 =====
    if len(all_phones) < 2 and engine != 'google':
        for suffix, keyword in SEARCH_EXPANSIONS:
            expanded = suffix.replace("{公司}", company_name)
            logger.info(f"  [!] 仅找到 {len(all_phones)} 个电话，尝试补充搜索: \"{expanded}\"")
            try:
                crawler2 = engine_cls(headless=headless, proxy=proxy)
                if delay > 0:
                    time.sleep(delay / 1000)
                opened2, page_text2 = crawler2.search_and_open(expanded, max_results=max(3, max_results))
                crawler2.close()
                if page_text2:
                    extra = extractor.extract(page_text2)
                    for p in extra:
                        if p not in all_phones:
                            all_phones.add(p)
                            sources.append({
                                'url': f'搜索引擎结果页',
                                'title': f'{engine}搜索结果-{expanded}',
                                'phone': p,
                                'keyword': keyword,
                            })
                for pd in (opened2 or []):
                    if pd.get('page_text'):
                        for p in extractor.extract(pd['page_text']):
                            if p not in all_phones:
                                all_phones.add(p)
                                sources.append({
                                    'url': pd['url'],
                                    'title': pd['title'],
                                    'phone': p,
                                    'keyword': keyword,
                                })
                logger.info(f"    补充后: {len(all_phones)} 个电话")
                if len(all_phones) >= 3:
                    break
            except Exception as e:
                logger.warning(f"    补充搜索失败: {e}")

    # 重建 result
    result['phones'] = sorted(all_phones)
    result['phone_count'] = len(all_phones)
    result['sources'] = sources

    # ===== 百度地图 POI 补充查询 =====
    if len(all_phones) < 3 or engine != 'google':
        logger.info(f"  [百度地图] 补充查询POI数据...")
        map_r = query_map_poi(company_name)
        if map_r.get('all_phones'):
            # 先统计新增电话数（此时还没加入 all_phones）
            new_count = len([p for p in map_r['all_phones'] if p not in all_phones])
            for p in map_r['all_phones']:
                if p not in all_phones:
                    all_phones.add(p)
                    sources.append({
                        'url': f'百度地图POI',
                        'title': f'{map_r.get("name", company_name)}-百度地图',
                        'phone': p,
                    })
            if map_r.get('address'):
                logger.info(f"  [百度地图] 地址: {map_r['address']}")
            logger.info(f"  [百度地图] 新增 {new_count} 个电话")
            # 更新 result
            result['phones'] = sorted(all_phones)
            result['phone_count'] = len(all_phones)
            result['sources'] = sources

    return result


def search_all_engines(
    company_name: str,
    max_results: int = 5,
    headless: bool = True,
    proxy: str = None,
    verbose: bool = False,
    delay: int = 0,
    cached: bool = True,
) -> dict:
    """
    多引擎并行搜索：同时跑 baidu → bing → sogou，合并结果去重自动去重。
    缓存命中时跳过搜索直接返回。
    """
    # 缓存命中检查
    cache_key = "+".join(MULTI_ENGINES)
    if cached:
        cached_result = _cache.get(company_name, cache_key)
        if cached_result:
            return cached_result

    all_phones = {}
    per_engine = []
    engines_run = []

    def _run_engine(eng: str) -> dict | None:
        """执行单个引擎搜索，异常时返回 None 不中断整体"""
        try:
            result = search_company(
                company_name=company_name,
                engine=eng,
                max_results=max_results,
                headless=headless,
                proxy=proxy,
                verbose=verbose,
                delay=delay,
            )
            return result
        except Exception as e:
            logger.error(f"  [X] 引擎 {eng} 搜索失败: {e}")
            return None

    logger.info(f"  并行启动 {len(MULTI_ENGINES)} 个引擎...")
    with ThreadPoolExecutor(max_workers=len(MULTI_ENGINES)) as executor:
        future_map = {executor.submit(_run_engine, eng): eng for eng in MULTI_ENGINES}
        for future in as_completed(future_map):
            eng = future_map[future]
            result = future.result()
            if result is None:
                continue
            per_engine.append({eng: result})
            engines_run.append(eng)
            for phone in result.get('phones', []):
                if phone not in all_phones:
                    all_phones[phone] = []
                for src in result.get('sources', []):
                    if src['phone'] == phone:
                        all_phones[phone].append(src)

    merged = {
        "company": company_name,
        "phones": sorted(all_phones.keys()),
        "phone_count": len(all_phones),
        "engines_run": engines_run,
        "details": per_engine,
        "sources": [s for srcs in all_phones.values() for s in srcs],
        "engine": " + ".join(engines_run),
    }
    # 写入缓存
    if cached and engines_run:
        _cache.set(company_name, cache_key, merged)
    return merged


def main():
    parser = argparse.ArgumentParser(
        description='公司联系电话爬虫 - 支持多引擎合并搜索',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  单个引擎:
    python main.py "山东华派集团有限公司" --engine baidu --max 5 -v
    
  多引擎合并（推荐）:
    python main.py "山东华派集团有限公司" --all --max 5 -o result.json
    
  批量搜索:
    python main.py -f companies.txt --all --max 3
        """
    )
    parser.add_argument('company', nargs='?', help='公司名称')
    parser.add_argument('-f', '--file', help='公司名称列表文件（每行一个）')
    parser.add_argument('--engine', '-e', default='baidu',
                        choices=list(ENGINE_REGISTRY.keys()),
                        help='搜索引擎 (默认: baidu)')
    parser.add_argument('--all', '-a', action='store_true',
                        help='多引擎合并搜索 (baidu + bing + sogou，自动去重)')
    parser.add_argument('--max', '-m', type=int, default=5,
                        help='每个引擎打开前 N 个结果 (默认: 5)')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径')
    parser.add_argument('--csv', action='store_true',
                        help='同时导出 CSV 文件')
    parser.add_argument('--proxy', help='代理地址')
    parser.add_argument('--delay', type=int, default=0,
                        help='请求间隔（毫秒），避免触发反爬')
    parser.add_argument('--no-cache', action='store_true',
                        help='禁用缓存，强制重新搜索')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='显示详细信息')
    parser.add_argument('--visible', action='store_true',
                        help='显示浏览器窗口')

    args = parser.parse_args()

    # 配置日志级别
    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=level)
    logger.setLevel(level)

    companies = []
    if args.file:
        try:
            companies = load_companies_from_file(args.file)
            logger.info(f"[列表] 从文件加载了 {len(companies)} 个公司")
        except FileNotFoundError as e:
            logger.error(f"文件不存在: {e}")
            sys.exit(1)
    elif args.company:
        companies = [args.company]
    else:
        parser.print_help()
        sys.exit(1)

    headless = not args.visible

    for i, company in enumerate(companies):
        logger.info(f"{'#' * 60}")
        logger.info(f"# 进度: [{i + 1}/{len(companies)}]  {company}")
        logger.info(f"{'#' * 60}")

        if args.all:
            result = search_all_engines(
                company_name=company,
                max_results=args.max,
                headless=headless,
                proxy=args.proxy,
                verbose=args.verbose,
                delay=args.delay,
                cached=not args.no_cache,
            )
        else:
            result = search_company(
                company_name=company,
                engine=args.engine,
                max_results=args.max,
                headless=headless,
                proxy=args.proxy,
                verbose=args.verbose,
                delay=args.delay,
            )

        # 打印合并摘要
        if args.all:
            engines_str = ' + '.join(result.get('engines_run', []))
            logger.info(f"{'=' * 50}")
            logger.info(f"[合并结果] {company}")
            logger.info(f"  引擎: {engines_str}")
            logger.info(f"  电话总数: {result['phone_count']}")
            if result['phones']:
                for p in result['phones']:
                    logger.info(f"  [电话] {p}")
            logger.info(f"{'=' * 50}")
        else:
            logger.info(f"{'---' * 40}")
            logger.info(f"[结果] {company}")
            logger.info(f"  找到 {result['phone_count']} 个电话号码")
            if result['phones']:
                for p in result['phones']:
                    logger.info(f"  [电话] {p}")
            logger.info(f"{'---' * 40}")

        if args.output:
            path = save_result(company, result, args.output)
            logger.info(f"[保存] {path}")

        if args.csv or (args.output and args.output.endswith('.csv')):
            csv_path = args.output if args.output and args.output.endswith('.csv') else args.output or '.'
            csv_file = export_csv(company, result.get('phones', []), result.get('sources', []), csv_path)
            logger.info(f"[CSV] {csv_file}")

    if len(companies) > 1:
        summary = {
            "total": len(companies),
            "mode": "all" if args.all else args.engine,
            "results": [],
        }
        path = save_result("all_companies", summary, args.output or ".")
        logger.info(f"\n[结果] 全部结果已保存: {path}")


if __name__ == '__main__':
    main()
