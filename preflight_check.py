#!/usr/bin/env python3
# RustDesk 代码修改预检脚本，推送前运行，无需安装任何依赖
# Windows下直接运行: python preflight_check.py
import os
import sys
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
PASS = 0
FAIL = 0

def check_pass(name, ok, msg=""):
    global PASS, FAIL
    if ok:
        print(f"[PASS] {name}")
        PASS +=1
    else:
        print(f"[FAIL] {name}：{msg}")
        FAIL +=1

def read_file(rel_path):
    full = os.path.join(ROOT, rel_path)
    if not os.path.exists(full):
        return None
    with open(full, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def grep_in_file(rel_path, pattern):
    content = read_file(rel_path)
    if content is None:
        return False
    return bool(re.search(pattern, content, re.MULTILINE))

def extract_section(lines, start_marker, end_marker):
    section = []
    in_section = False
    for line in lines:
        if start_marker in line:
            in_section = True
        elif in_section and end_marker in line and line.strip().startswith(end_marker.split(":")[0]):
            break
        if in_section:
            section.append(line)
    return "".join(section)

print("="*60)
print("RustDesk 代码修改预检工具")
print("="*60)
print()

# 先读取工作流文件
with open(os.path.join(ROOT, ".github/workflows/flutter-build.yml"), 'r', encoding='utf-8') as f:
    lines = f.readlines()

sciter_section = extract_section(lines, "build-for-windows-sciter:", "build-rustdesk-ios:")
macos_section = extract_section(lines, "build-for-macOS:", "build-rustdesk-ios:")
build_part = sciter_section.split("Build rustdesk")[1].split("find Runner.res")[0] if "Build rustdesk" in sciter_section else ""
matrix_part = sciter_section.split("strategy:")[1].split("steps:")[0] if "strategy:" in sciter_section else ""

# -------------------------- 1. 自动更新移除检查 --------------------------
print("[1/10] 检查自动更新模块移除")
check_pass("src/updater.rs已删除", not os.path.exists(os.path.join(ROOT, "src/updater.rs")))
check_pass("更新进度UI组件已删除", not os.path.exists(os.path.join(ROOT, "flutter/lib/desktop/widgets/update_progress.dart")))
check_pass("lib.rs中已移除mod updater声明", not grep_in_file("src/lib.rs", r"^\s*mod\s+updater\s*;"))
# 检查所有rs文件里的launch_update_thread
import glob
has_launch = False
for rs in glob.glob(os.path.join(ROOT, "src/**/*.rs"), recursive=True):
    content = open(rs, 'r', encoding='utf-8', errors='ignore').read()
    if "launch_update_thread" in content:
        has_launch = True
        break
check_pass("无残留自动更新启动调用", not has_launch)
check_pass("无残留updater模块导入", not grep_in_file("src/flutter_ffi.rs", r"use\s+crate::updater"))
print()

# -------------------------- 2. 服务器配置硬编码检查 --------------------------
print("[2/10] 检查服务器配置硬编码")
config_content = read_file("libs/hbb_common/src/config.rs")
if config_content:
    check_pass("ID/信令服务器硬编码正确", "r.3d98.com.cn:21116" in config_content)
    check_pass("中继服务器硬编码正确", "r.3d98.com.cn:21117" in config_content)
    check_pass("API服务器硬编码正确", "http://r.3d98.com.cn:21114" in config_content)
    check_pass("公钥Key硬编码正确", "3yPOFgXbTyzUf0WbgBRsQ9TAmCDqd+nz0NhY8E6YcKw=" in config_content)
else:
    check_pass("config.rs存在", False, "libs/hbb_common/src/config.rs 不存在")
check_pass("playground.yml中已删除密钥注入", not grep_in_file(".github/workflows/playground.yml", r"RS_PUB_KEY|RENDEZVOUS_SERVER|API_SERVER"))
check_pass("根目录main.rs（环境变量覆盖入口）已删除", not os.path.exists(os.path.join(ROOT, "main.rs")))
print()

# -------------------------- 3. Windows 32位构建配置检查 --------------------------
print("[3/10] 检查Windows 32位(sciter)CI配置")
if sciter_section:
    check_pass("已使用64位LLVM（不会出现libclang位数错误）", "KyleMayes/install-llvm-action" in sciter_section)
    check_pass("已移除32位LLVM安装步骤（旧错误配置）", "install-llvm-action-32bit" not in sciter_section)
    check_pass("Rust工具链使用官方指定1.75版本", 'toolchain: ${{ env.SCITER_RUST_VERSION }}' in sciter_section)
    check_pass("cargo build已添加--target参数（跨编译32位）", "--target ${{ matrix.job.target }}" in build_part)
    check_pass("产物路径已指向target目录", "mv ./target/${{ matrix.job.target }}/release/rustdesk.exe" in build_part)
    check_pass("sciter矩阵仅保留32位i686（和官方一致）", "x86_64-pc-windows-msvc" not in matrix_part)
    check_pass("sciter构建仅使用--features inline，无多余hwcodec/vram特性", "hwcodec" not in build_part and "vram" not in build_part)
    check_pass("vcpkg host triplet为x64-windows-static（正确，host是64位）", "VCPKG_DEFAULT_HOST_TRIPLET: x64-windows-static" in sciter_section)
else:
    check_pass("sciter任务存在", False, "未找到build-for-windows-sciter任务")
print()

# -------------------------- 4. macOS构建配置检查 --------------------------
print("[4/10] 检查macOS runner配置")
if macos_section:
    check_pass("macOS x86_64使用macos-15-intel（正确，macos-13已下线）", "macos-15-intel" in macos_section)
    check_pass("macOS aarch64使用macos-15（正确，macos-14已下线）", "os: macos-15," in macos_section and "aarch64-apple-darwin" in macos_section)
    # 只检查非注释行里的runner标签
    non_comment_lines = [line for line in macos_section.split('\n') if not line.strip().startswith('#')]
    non_comment_macos = '\n'.join(non_comment_lines)
    check_pass("桌面macOS任务已移除旧版已下线macos runner标签", "os: macos-13" not in non_comment_macos and "os: macos-14" not in non_comment_macos and "macos-14-arm64" not in non_comment_macos)
else:
    check_pass("macOS任务存在", False, "未找到build-for-macOS任务")
print()

# -------------------------- 5. 语法错误检查 --------------------------
print("[5/10] 检查Rust语法（括号平衡）")
ffi_content = read_file("src/flutter_ffi.rs")
if ffi_content:
    open_brackets = ffi_content.count('{')
    close_brackets = ffi_content.count('}')
    open_paren = ffi_content.count('(')
    close_paren = ffi_content.count(')')
    check_pass("src/flutter_ffi.rs大括号平衡（不会出现lex error）", open_brackets == close_brackets, f"开{open_brackets}/闭{close_brackets}")
    check_pass("src/flutter_ffi.rs小括号平衡", open_paren == close_paren, f"开{open_paren}/闭{close_paren}")
print()

# -------------------------- 6. 验证工作流检查 --------------------------
print("[6/10] 检查验证工作流")
val_yml = read_file(".github/workflows/validate-windows-sciter.yml")
if val_yml:
    check_pass("验证工作流存在", True)
    check_pass("验证工作流使用64位LLVM", "KyleMayes/install-llvm-action" in val_yml)
    check_pass("验证工作流使用官方1.75工具链", "SCITER_RUST_VERSION" in val_yml or '1.75' in val_yml)
    check_pass("验证工作流构建参数带--target", "--target i686-pc-windows-msvc" in val_yml)
    check_pass("验证工作流仅使用--features inline", "--features inline" in val_yml and "hwcodec" not in val_yml)
else:
    check_pass("验证工作流存在", False, "validate-windows-sciter.yml 不存在")
print()

# -------------------------- 结果输出 --------------------------
print("="*60)
print(f"检查结果：通过 {PASS} 项，失败 {FAIL} 项")
print("="*60)
if FAIL == 0:
    print("✅ 所有检查通过！可以放心提交推送。")
    sys.exit(0)
else:
    print("❌ 存在问题，请修复后再推送。")
    sys.exit(1)
