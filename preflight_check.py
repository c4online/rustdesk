#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送前本地预检脚本
==================
用途：推送到 GitHub 之前，在本地先把「工作流配置」「自动更新是否清干净」
      「关键文件语法」检查一遍，避免推一次错一次。

用法（在仓库根目录执行，即含 .github 和 src 的那一层）：
    python preflight_check.py

特点：
    - 只用 Python 标准库，Windows / macOS / Linux 都能跑，无需装任何包；
    - 不修改任何文件，纯只读检查；
    - 最后给出退出码：0 = 全部通过，1 = 有 FAIL（先修好再推）。

注意：本脚本只能检查「配置和代码本身」是否正确，无法验证
      「GitHub runner 上能不能真正编译通过」——那一步必须靠本地实跑
      交叉编译（见脚本末尾提示）或先手动触发验证工作流。
"""

import os
import re
import sys
import subprocess

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

REPO = os.path.dirname(os.path.abspath(__file__))

PASS, FAIL, WARN = [], [], []


def ok(msg, detail=""):
    PASS.append(msg)
    print("[通过] " + msg + (("  -> " + detail) if detail else ""))


def bad(msg, detail=""):
    FAIL.append(msg)
    print("[失败] " + msg + (("  -> " + detail) if detail else ""))


def warn(msg, detail=""):
    WARN.append(msg)
    print("[注意] " + msg + (("  -> " + detail) if detail else ""))


def read(path):
    """按 utf-8 读文本，找不到返回 None。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def find_root():
    """确认当前在仓库根（同时存在 src 与 .github）。"""
    has_src = os.path.isdir(os.path.join(REPO, "src"))
    has_gh = os.path.isdir(os.path.join(REPO, ".github", "workflows"))
    if not (has_src and has_gh):
        print("!! 这个脚本要放在仓库根目录执行（同时能看到 src/ 和 .github/）。")
        print("   当前目录：" + REPO)
        sys.exit(2)


# ---------------------------------------------------------------------------
# 1) 提取 sciter 任务片段
# ---------------------------------------------------------------------------

def extract_sciter_job(text):
    """从 flutter-build.yml 中截取 build-for-windows-sciter 这个 job 的文本。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        # job 名形如 "  build-for-windows-sciter:"
        if re.match(r"^  build-for-windows-sciter:\s*$", ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # 下一个同级 job（缩进两格的 xxx:） 或文件结束
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# 2) 各项检查
# ---------------------------------------------------------------------------

def check_ci():
    print("")
    print("== 一、CI 工作流配置 ==")
    wf = os.path.join(REPO, ".github", "workflows", "flutter-build.yml")
    text = read(wf)
    if text is None:
        bad("找不到 .github/workflows/flutter-build.yml")
        return

    # YAML 语法（若有 pyyaml 才做，缺了不报错）
    try:
        import yaml  # noqa
        try:
            yaml.safe_load(text)
            ok("flutter-build.yml 的 YAML 语法可解析")
        except Exception as e:
            bad("flutter-build.yml 的 YAML 语法有错", str(e)[:120])
    except ImportError:
        warn("未安装 PyYAML，跳过整份 YAML 语法校验（不影响其余检查）")

    seg = extract_sciter_job(text)
    if seg is None:
        bad("没有找到 build-for-windows-sciter 任务")
        return
    ok("定位到 build-for-windows-sciter 任务")

    # 2.1 LLVM 必须是 64 位
    if "install-llvm-action-32bit" in seg:
        bad("sciter 任务的 LLVM 仍是 32 位版",
            "64 位构建脚本加载 32 位 libclang.dll 会报 invalid DLL (32-bit)")
    elif "KyleMayes/install-llvm-action" in seg:
        ok("sciter 任务的 LLVM 用的是 64 位 action")
    else:
        warn("sciter 任务的 LLVM 步骤写法无法识别，请人工确认")

    # 2.2 工具链不得把 target 拼进宿主名
    m = re.search(r"toolchain:\s*([^\n#]+)", seg)
    if not m:
        warn("sciter 任务里没找到 toolchain 行")
    else:
        val = m.group(1).strip()
        if "matrix.job.target" in val or val.endswith("-i686-pc-windows-msvc"):
            bad("工具链名把 target 拼进了宿主位：" + val,
                "装出来的 32 位宿主工具链在 64 位 runner 上跑不起来")
        elif val == "nightly-2023-10-13":
            ok("工具链为 64 位宿主 " + val)
        elif val.startswith("nightly-2023-10-13"):
            bad("工具链值带了多余后缀：" + val, "应恰好为 nightly-2023-10-13")
        else:
            warn("工具链值未识别：" + val)

    # 2.3 cargo build 必须带 --target
    if re.search(r"cargo\s+build[^\n]*--target\s+\$\{\{\s*matrix\.job\.target\s*\}\}", seg):
        ok("cargo build 带了 --target（产出真正的 32 位程序）")
    else:
        bad("cargo build 没有 --target",
            "只换工具链不加 --target，命令会成功但产物是 64 位，被静默当成 32 位包")

    # 2.4 产物路径必须带 target 目录
    if re.search(r"target/\$\{\{\s*matrix\.job\.target\s*\}\}/release/", seg):
        ok("产物路径带 target 目录（能取到 32 位产物）")
    else:
        bad("产物路径还是 ./target/release/",
            "交叉编译后产物在 target/<target>/release/，原路径取不到文件")

    # 2.5 旧写法是否残留
    if "force-non-host" in text:
        warn("文件里还存在 --force-non-host（若已改走跨编译方案，应删掉它）")


def check_autoupdate():
    print("")
    print("== 二、自动更新是否清干净 ==")
    if os.path.exists(os.path.join(REPO, "src", "updater.rs")):
        bad("src/updater.rs 仍然存在（应整体删除）")
    else:
        ok("src/updater.rs 已删除")

    lib = read(os.path.join(REPO, "src", "lib.rs")) or ""
    if re.search(r"^\s*mod\s+updater\s*;", lib, re.M):
        bad("src/lib.rs 里还有 mod updater;")
    else:
        ok("src/lib.rs 已无 mod updater;")

    p = os.path.join(REPO, "flutter", "lib", "desktop", "widgets", "update_progress.dart")
    if os.path.exists(p):
        bad("flutter/lib/desktop/widgets/update_progress.dart 仍然存在（应整体删除）")
    else:
        ok("update_progress.dart 已删除")


def check_syntax():
    print("")
    print("== 三、关键文件语法 ==")
    ffi = os.path.join(REPO, "src", "flutter_ffi.rs")
    text = read(ffi)
    if text is None:
        warn("找不到 src/flutter_ffi.rs，跳过")
    else:
        # 粗略括号平衡（会忽略字符串/注释里的括号，只能发现明显重复粘贴这类大问题）
        l = text.count("{") + text.count("(") + text.count("[")
        r = text.count("}") + text.count(")") + text.count("]")
        if l == r:
            ok("src/flutter_ffi.rs 括号数量平衡（%d/%d）" % (l, r))
        else:
            bad("src/flutter_ffi.rs 括号不平衡",
                "开 %d / 闭 %d，常见于重复粘贴导致语法被破坏" % (l, r))


def check_git():
    print("")
    print("== 四、Git 状态提醒 ==")
    try:
        inside = subprocess.check_output(
            ["git", "-C", REPO, "rev-parse", "--is-inside-work-tree"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8", "replace").strip()
        if inside != "true":
            warn("当前目录不是 git 仓库，跳过 git 状态检查")
            return
        out = subprocess.check_output(
            ["git", "-C", REPO, "status", "--short"],
            stderr=subprocess.STDOUT
        ).decode("utf-8", "replace").strip()
    except Exception as e:
        warn("无法执行 git status（可能没装 git，" + type(e).__name__ + "）")
        return
    if not out:
        ok("工作区干净，改动都已提交")
    else:
        n = len([x for x in out.splitlines() if x.strip()])
        warn("有 %d 处改动还没提交——推送前记得 git add / commit" % n)
        for line in out.splitlines():
            print("       " + line)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=" * 64)
    print(" RustDesk 推送前本地预检")
    print(" 仓库目录：" + REPO)
    print("=" * 64)
    find_root()
    check_ci()
    check_autoupdate()
    check_syntax()
    check_git()

    print("")
    print("=" * 64)
    print(" 结果：通过 %d 项，失败 %d 项，注意 %d 项" % (len(PASS), len(FAIL), len(WARN)))
    print("=" * 64)
    if FAIL:
        print(" 有失败项，先按上面的提示改好再推。")
        return 1
    print(" 本地静态检查通过。")
    print(" 提醒：这一步只验证配置/代码本身；能否编译通过还需本地实跑或先手动触发验证工作流。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
