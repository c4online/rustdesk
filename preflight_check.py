#!/usr/bin/env python3
import os
import re
import sys

def check_file_exists(path, fail_msg, pass_msg):
    if os.path.exists(path):
        print(f"[PASS] {pass_msg}")
        return True
    else:
        print(f"[FAIL] {fail_msg}")
        return False

def check_file_not_exists(path, fail_msg, pass_msg):
    if not os.path.exists(path):
        print(f"[PASS] {pass_msg}")
        return True
    else:
        print(f"[FAIL] {fail_msg}")
        return False

def check_file_content(path, pattern, fail_msg, pass_msg, flags=0):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if re.search(pattern, content, flags):
            print(f"[PASS] {pass_msg}")
            return True
        else:
            print(f"[FAIL] {fail_msg}")
            return False
    except Exception as e:
        print(f"[FAIL] 无法读取 {path}: {e}")
        return False

def check_no_file_content(path, pattern, fail_msg, pass_msg, flags=0):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if not re.search(pattern, content, flags):
            print(f"[PASS] {pass_msg}")
            return True
        else:
            print(f"[FAIL] {fail_msg}")
            return False
    except Exception as e:
        print(f"[FAIL] 无法读取 {path}: {e}")
        return False

def check_bracket_balance(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        open_count = content.count('{')
        close_count = content.count('}')
        if open_count == close_count:
            print(f"[PASS] {path} 括号平衡（{open_count}开/{close_count}闭），无语法错误")
            return True
        else:
            print(f"[FAIL] {path} 括号不平衡！开括号{open_count}个，闭括号{close_count}个，会导致lex error")
            return False
    except Exception as e:
        print(f"[FAIL] 无法读取 {path}: {e}")
        return False

def check_git_status():
    import subprocess
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, encoding='utf-8')
        changed = [line[3:] for line in result.stdout.strip().split('\n') if line.strip()]
        if not changed:
            print(f"[PASS] 所有修改已提交，可以推送")
            return True
        else:
            print(f"[FAIL] 还有{len(changed)}个文件修改未提交：{', '.join(changed[:5])}{'...' if len(changed) > 5 else ''}")
            return False
    except Exception as e:
        print(f"[WARN] 无法检查git状态：{e}（跳过）")
        return True

def main():
    print("=== RustDesk 构建预检脚本 v2 ===")
    all_pass = True
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 1. 自动更新核心文件删除
    all_pass &= check_file_not_exists("src/updater.rs",
        "src/updater.rs 仍然存在，自动更新核心模块未删除",
        "src/updater.rs 已删除")
    all_pass &= check_file_not_exists("flutter/lib/desktop/widgets/update_progress.dart",
        "update_progress.dart 仍然存在，更新进度UI未删除",
        "update_progress.dart 已删除")

    # 2. Rust模块声明移除
    all_pass &= check_no_file_content("src/lib.rs", r"mod\s+updater\s*;",
        "src/lib.rs 中仍然存在 mod updater; 声明",
        "src/lib.rs 已移除mod updater声明")

    # 3. CI LLVM配置
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"build-for-windows-sciter[\s\S]*?KyleMayes/install-llvm-action",
        "sciter任务仍在使用32位LLVM，会导致libclang invalid DLL错误",
        "sciter任务已使用64位LLVM，不会出现libclang位数不匹配")

    # 4. Rust工具链配置
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"toolchain:\s*nightly-2023-10-13\s*#",
        "sciter任务工具链仍拼接target后缀，会导致i686宿主无法运行错误",
        "Rust工具链配置正确（64位宿主+32位target交叉编译）")

    # 5. 64位+32位sciter双架构都开启
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"target:\s*x86_64-pc-windows-msvc[\s\S]*?arch:\s*x86_64[\s\S]*?target:\s*i686-pc-windows-msvc",
        "sciter任务未同时开启x86_64和i686双架构编译",
        "sciter已开启x86/x64双架构编译，和官方一致")

    # 6. vcpkg host triplet配置正确（跨编译32位时用x64构建工具）
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"build-for-windows-sciter[\s\S]*?VCPKG_DEFAULT_HOST_TRIPLET:\s*x64-windows-static",
        "sciter 32位任务vcpkg host triplet配置错误，构建工具会无法运行",
        "vcpkg host triplet配置正确（64位构建工具+32位目标库）")

    # 7. macOS runner标签正确（macos-13 / macos-14 均已被 GitHub 下线）
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"target:\s*x86_64-apple-darwin[\s\S]*?os:\s*macos-15-intel",
        "macOS x86_64 runner标签错误，应为 macos-15-intel（macos-13 已下线）",
        "macOS x86_64 runner标签正确（macos-15-intel）")
    all_pass &= check_no_file_content(".github/workflows/flutter-build.yml",
        r"os:\s*macos-(13|14)\s*[,\n]",
        "仍有 macos-13 / macos-14 标签，这两个镜像已被 GitHub 下线，job 会无法启动",
        "无已下线的 macos-13 / macos-14 runner 标签")

    # 7.1 sciter产物名唯一，避免与flutter任务的同名artifact冲突
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"rustdesk-unsigned-windows-\$\{\{\s*matrix\.job\.arch\s*\}\}-sciter",
        "sciter任务产物名与flutter任务重名，会导致artifact上传冲突失败",
        "sciter任务产物名已加 -sciter 后缀，不会与flutter任务冲突")

    # 8. 32/64位sciter分支判断和dll下载逻辑
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"if \[.*i686-pc-windows-msvc.*\]; then[\s\S]*?dyn_x86[\s\S]*?x32/sciter\.dll[\s\S]*?else[\s\S]*?x64/sciter\.dll",
        "sciter构建分支判断错误，32位/64位dll下载不匹配",
        "sciter构建分支正确，32位用x32 dll，64位用x64 dll")

    # 9. cargo build带--target参数
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"cargo build[\s\S]*--target\s*\$\{\{\s*matrix\.job\.target\s*\}\}",
        "cargo build缺少--target参数，无法正确交叉编译",
        "cargo build已添加--target参数")

    # 10. 产物路径带target目录
    all_pass &= check_file_content(".github/workflows/flutter-build.yml",
        r"target/\$\{\{\s*matrix\.job\.target\s*\}\}/release",
        "产物路径未指向target目录，构建后会找不到exe",
        "产物路径已正确指向target目录")

    # 11. flutter_ffi.rs括号平衡
    all_pass &= check_bracket_balance("src/flutter_ffi.rs")

    # 12. 无残留自动更新核心调用
    import glob
    has_update = False
    for rs_file in glob.glob("src/**/*.rs", recursive=True):
        try:
            with open(rs_file, 'r', encoding='utf-8') as f:
                if 'launch_update_thread' in f.read():
                    has_update = True
                    print(f"[FAIL] 文件 {rs_file} 中仍存在launch_update_thread自动更新调用")
                    break
        except:
            pass
    if not has_update:
        print(f"[PASS] 无残留自动更新核心调用")
        all_pass &= True
    else:
        all_pass &= False

    # 13. git状态检查
    all_pass &= check_git_status()

    print("\n" + "="*50)
    if all_pass:
        print("✅ 所有检查通过！放心提交推送即可。")
        return 0
    else:
        print("❌ 存在以上问题，请修复后再推送。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
