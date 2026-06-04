"""BDSS 全面审查脚本 — 检查所有修复 + 代码质量"""
import ast, os, sys, glob

issues = []

def check(name, ok, detail=""):
    if ok:
        print(f"  \u2705 {name}")
    else:
        print(f"  \u274c {name} {detail}")
        issues.append(name)

print("=== \u4fee\u590d\u9a8c\u8bc1 ===")

# 1. 语法检查
py_files = []
for root, dirs, files in os.walk("."):
    if ".venv" in root or "__pycache__" in root or ".git" in root or "node_modules" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

for f in py_files:
    try:
        with open(f) as fh:
            ast.parse(fh.read())
    except SyntaxError as e:
        print(f"  \u274c \u8bed\u6cd5\u9519\u8bef {f}: {e}")
        issues.append(f"\u8bed\u6cd5\u9519\u8bef: {f}")
        break
else:
    check(f"\u6240\u6709 {len(py_files)} \u4e2a Python \u6587\u4ef6\u8bed\u6cd5\u6b63\u786e", True)

# 2. ThreadPoolExecutor removed
with open("main.py") as f:
    main = f.read()
check("#1 ThreadPoolExecutor \u5df2\u79fb\u9664", "ThreadPoolExecutor" not in main)
check("#7 or \u2192 and", main.count("all_phones) < 3 or engine") == 0)

# 3. bare except with pass
bare_count = 0
for f in py_files:
    with open(f) as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("except Exception:") or stripped == "except:":
            if i + 1 < len(lines) and lines[i + 1].strip() == "pass":
                bare_count += 1
check(f"#4 \u5c11\u6570\u88f8 except: pass \u5269 {bare_count} \u5904", bare_count == 0, f"({bare_count} \u5904)")
if bare_count > 0:
    print(f"    \u5efa\u8bae\u5728\u540e\u7eed\u8fed\u4ee3\u4e2d\u6e05\u7406: https://github.com/gaokkuan-1023/bdss/labels/bare-except")

# 4. PhoneExtractor delegation in lite_search
with open("skills/lite_search.py") as f:
    ls = f.read()
check("#6 lite_search \u4f7f\u7528 PhoneExtractor \u59d4\u6258", "PHONE_EXTRACTOR" in ls or "from extractors.phone" in ls)

# 5. base.py fix
with open("skills/base.py") as f:
    base = f.read()
check("#2 base.py \u533a\u5206\u5171\u4eab/\u72ec\u7acb\u6d4f\u89c8\u5668", "self._owns_browser" in base)
check("#2 \u5f02\u5e38\u65e5\u5fd7", "logger.debug(" in base)

# 6. requirements
check("#8 requirements-dev.txt", os.path.exists("requirements-dev.txt"))
check("#8 python-dotenv", "python-dotenv" in open("requirements-dev.txt").read())

# 7. app.py debug
app_path = "/Users/lhqc/bdss-app/app.py"
with open(app_path) as f:
    app_content = f.read()
check("#3 app.py debug \u7981\u7528", "debug=True" not in app_content and "debug=args.verbose" not in app_content)
if "debug=True" in app_content or "debug=args.verbose" in app_content:
    app_content = app_content.replace("debug=True", "debug=False").replace("debug=args.verbose", "debug=False")
    with open(app_path, "w") as f:
        f.write(app_content)
    print("    \u2192 \u5df2\u4fee\u590d")

# 8. baidumap.py browser lifecycle
with open("skills/baidumap.py") as f:
    bd = f.read()
check("#2 baidumap \u6d4f\u89c8\u5668\u751f\u547d\u5468\u671f", "finally:" in bd[bd.find("p.chromium.launch"):])

# 9. .env parsing duplication
env_count = 0
for f in py_files:
    with open(f) as fh:
        c = fh.read()
    if 'BAIDU_MAP_AK' in c and 'os.environ.get' in c:
        # Check if it's reading from .env
        if '.env' in c:
            env_count += 1
check(f".env \u89e3\u6790\u91cd\u590d ({env_count} \u5904)", env_count <= 2)

print()
print("=== \u5168\u9762\u5ba1\u67e5\u7ed3\u679c ===")
print(f"\u5171\u53d1\u73b0 {len(issues)} \u4e2a\u95ee\u9898" if issues else "\u2705 0 \u4e2a\u95ee\u9898\uff0c\u5168\u90e8\u4fee\u590d\u5b8c\u6210")
if issues:
    for i in issues:
        print(f"  \u274c {i}")
