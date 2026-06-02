"""
公司联系电话爬虫 - 主入口

支持搜索引擎: baidu / google / bing / sogou
多引擎合并搜索: --all (自动跑 baidu + bing + sogou，合并结果去重)
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from skills.baidu import BaiduSearch
from skills.google import GoogleSearch
from skills.bing import BingSearch
from skills.sogou import SogouSearch
from extractors.phone import PhoneExtractor
from utils.helpers import save_result, load_companies_from_file

# 地理校验函数（内联，避免 import 缓存问题）
def _check_phone_geo(phones, page_texts):
    """检查电话区号是否与页面中提取的城市匹配"""
    import re
    city_codes = {'枣庄':['0632'],'济南':['0531'],'青岛':['0532'],'潍坊':['0536'],
                  '淄博':['0533'],'德州':['0534'],'烟台':['0535'],'济宁':['0537'],
                  '泰安':['0538'],'临沂':['0539'],'菏泽':['0530'],'威海':['0631'],
                  '日照':['0633'],'聊城':['0635'],'滨州':['0543']}
    # 提取城市
    cities = set()
    for t in page_texts:
        for m in re.findall(r'([\u4e00-\u9fa5]{2,4})市', t):
            if m in city_codes: cities.add(m)
        for m in re.findall(r'(?:山东|广东|浙江|江苏)(?:省)?([\u4e00-\u9fa5]{2,4})(?:市|区|县)', t):
            if m in city_codes: cities.add(m)
    # 提取地址
    addr = None
    for t in page_texts:
        m = re.search(r'地址[：:]\s*([^\n。；]{5,80})', t)
        if m: addr = m.group(1).strip(); break
    # 校验
    valid_codes = set()
    for c in cities: valid_codes.update(city_codes.get(c,[]))
    valid, suspicious = [], []
    for p in phones:
        cl = p.replace('-','').replace(' ','')
        if not cl.startswith('0'): valid.append(p); continue
        if not valid_codes: suspicious.append(p); continue
        if any(cl[:clen] in valid_codes for clen in [4,3]):
            valid.append(p)
        else:
            suspicious.append(p)
    return {"valid":valid,"suspicious":suspicious,"cities":list(cities),"address":addr}

# 搜索引擎注册表
ENGINE_REGISTRY = {
    'baidu': BaiduSearch,
    'google': GoogleSearch,
    'bing': BingSearch,
    'sogou': SogouSearch,
}

# 多引擎合并搜索时默认使用的引擎（跳过 google，需要代理）
MULTI_ENGINES = ['baidu', 'bing', 'sogou']


def search_company(
    company_name: str,
    engine: str = 'baidu',
    max_results: int = 5,
    headless: bool = True,
    proxy: str = None,
    verbose: bool = False,
) -> dict:
    """
    搜索公司并提取联系电话。

    Returns:
        {"company": str, "phones": list[str], "sources": list[dict], ...}
    """
    engine_cls = ENGINE_REGISTRY.get(engine)
    if not engine_cls:
        print(f"[X] 不支持的搜索引擎: {engine}")
        return {"company": company_name, "phones": [], "sources": [], "engine": engine}

    crawler = engine_cls(headless=headless, proxy=proxy)
    extractor = PhoneExtractor(prefer_nearby=True)

    all_phones = set()
    sources = []

    try:
        print(f"\n{'=' * 50}")
        print(f"[搜索] {company_name}  (引擎: {engine})")
        print(f"{'=' * 50}")

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
                print(f"\n  [搜索结果页] 发现电话: {', '.join(search_phones)}")

        # 如果没有从搜索页找到电话（AI 摘要可能没加载），重试一次
        if not search_phones and engine == 'baidu' and headless:
            print(f"  [!] 搜索结果页未找到电话（AI摘要可能未加载），重试搜索...")
            crawler.close()
            opened_pages, search_page_text = None, None
            # 等待后重试
            time.sleep(3)
            crawler2 = engine_cls(headless=headless, proxy=proxy)
            try:
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
                        print(f"\n  [搜索结果页-重试] 发现电话: {', '.join(search_phones2)}")
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
                try:
                    print(f"\n  [页面] {page_data['title'][:50]}")
                    print(f"     URL: {page_data['url']}")
                    if phones:
                        for ph in phones:
                            print(f"     [电话] 发现电话: {ph}")
                    else:
                        print(f"     [X] 未发现电话")
                except UnicodeEncodeError:
                    title_safe = page_data['title'].encode('gbk', errors='replace').decode('gbk')[:50]
                    print(f"\n  [页面] {title_safe}")
                    print(f"     URL: {page_data['url']}")
                    if phones:
                        for ph in phones:
                            print(f"     [电话] 发现电话: {ph}")
                    else:
                        print(f"     [X] 未发现电话")

        # 从搜索结果摘要中提取电话
        for r in opened_pages:
            if r.get('snippet'):
                phones_in_snippet = extractor.extract(r['snippet'])
                for p in phones_in_snippet:
                    all_phones.add(p)

    except Exception as e:
        print(f"[X] 执行出错: {e}")
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

    # ===== 地理校验（内联，不用外部函数）=====
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
            print(f"\n  [地理校验] 检测到城市: {', '.join(cts)}")
            if sus:
                print(f"  [可疑] 以下号码区号不匹配: {', '.join(sus)}")
                for s in sus:
                    for src in result['sources']:
                        if src['phone'] == s: src['warning'] = '区号不匹配'
            if vld: print(f"  [匹配] {', '.join(vld)}")
        else:
            print(f"  [!] 未检测到城市，跳过区号校验")
        result['geo_check'] = {"valid":vld,"suspicious":sus,"cities":list(cts)}
    except Exception as ge:
        print(f"  [!] 地理校验异常: {ge}")
        result['geo_check'] = {"valid":[],"suspicious":[],"cities":[]}
    
    return result
def search_all_engines(
    company_name: str,
    max_results: int = 5,
    headless: bool = True,
    proxy: str = None,
    verbose: bool = False,
) -> dict:
    """
    多引擎合并搜索：依次用 baidu → bing → sogou 搜索，合并结果去重。
    """
    all_phones = {}
    per_engine = []
    engines_run = []

    for eng in MULTI_ENGINES:
        print(f"\n{'#' * 60}")
        print(f"# 引擎: {eng}")
        print(f"{'#' * 60}")
        result = search_company(
            company_name=company_name,
            engine=eng,
            max_results=max_results,
            headless=headless,
            proxy=proxy,
            verbose=verbose,
        )
        per_engine.append({eng: result})
        engines_run.append(eng)
        for phone in result.get('phones', []):
            if phone not in all_phones:
                all_phones[phone] = []
            # 合并来源
            for src in result.get('sources', []):
                if src['phone'] == phone:
                    all_phones[phone].append(src)

    # 构建合并结果
    merged_sources = []
    for phone, srcs in all_phones.items():
        for s in srcs:
            merged_sources.append(s)

    merged = {
        "company": company_name,
        "phones": sorted(all_phones.keys()),
        "phone_count": len(all_phones),
        "engines_run": engines_run,
        "details": per_engine,
        "sources": merged_sources,
        "engine": " + ".join(engines_run),
    }
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
    parser.add_argument('--proxy', help='代理地址')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='显示详细信息')
    parser.add_argument('--visible', action='store_true',
                        help='显示浏览器窗口')

    args = parser.parse_args()

    companies = []
    if args.file:
        try:
            companies = load_companies_from_file(args.file)
            print(f"[列表] 从文件加载了 {len(companies)} 个公司")
        except FileNotFoundError as e:
            print(f"[X] {e}")
            sys.exit(1)
    elif args.company:
        companies = [args.company]
    else:
        parser.print_help()
        sys.exit(1)

    headless = not args.visible

    for i, company in enumerate(companies):
        print(f"\n{'#' * 60}")
        print(f"# 进度: [{i + 1}/{len(companies)}]  {company}")
        print(f"{'#' * 60}")

        if args.all:
            result = search_all_engines(
                company_name=company,
                max_results=args.max,
                headless=headless,
                proxy=args.proxy,
                verbose=args.verbose,
            )
        else:
            result = search_company(
                company_name=company,
                engine=args.engine,
                max_results=args.max,
                headless=headless,
                proxy=args.proxy,
                verbose=args.verbose,
            )

        # 打印合并摘要
        if args.all:
            engines_str = ' + '.join(result.get('engines_run', []))
            print(f"\n{'=' * 50}")
            print(f"[合并结果] {company}")
            print(f"  引擎: {engines_str}")
            print(f"  电话总数: {result['phone_count']}")
            if result['phones']:
                for p in result['phones']:
                    print(f"  [电话] {p}")
            print(f"{'=' * 50}")
        else:
            print(f"\n{'---' * 40}")
            print(f"[结果] {company}")
            print(f"  找到 {result['phone_count']} 个电话号码")
            if result['phones']:
                for p in result['phones']:
                    print(f"  [电话] {p}")
            print(f"{'---' * 40}")

        if args.output:
            path = save_result(company, result, args.output)
            print(f"[保存] {path}")

    if len(companies) > 1:
        summary = {
            "total": len(companies),
            "mode": "all" if args.all else args.engine,
            "results": [],
        }
        path = save_result("all_companies", summary, args.output or ".")
        print(f"\n[结果] 全部结果已保存: {path}")


if __name__ == '__main__':
    main()
