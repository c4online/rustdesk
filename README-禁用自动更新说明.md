# c4Desk 定制版修改说明

本包基于 c4Desk（c4online/rustdesk）原始仓库，做了以下修改：

## 一、自动更新已禁用

- `src/updater.rs`：`TX_MSG` 后台更新线程不再启动，`start_auto_update` / `manually_check_update` / `stop_auto_update` 改为空操作。
- `src/common.rs::check_software_update()`：启动时自动检查更新首行 return，原代码保留作参考。
- `src/rendezvous_mediator.rs`：服务模式下的 `start_auto_update()` 调用注释掉；`ConfigureUpdate` 消息里的服务器下发加白名单过滤。
- `flutter/lib/desktop/pages/desktop_setting_page.dart`：移除"启动时检查更新"和"自动更新"两个 UI 开关。
- `flutter/lib/mobile/pages/settings_page.dart`：移除移动端"启动时检查更新"开关。

> 手动点 Update 的入口保留但不做任何事，不会再向官方 RustDesk 服务器下载并覆盖成官方客户端。

## 二、更新检查地址改为自建

- `libs/hbb_common/src/lib.rs`：`https://api.rustdesk.com/version/latest` → `https://r.3d98.com.cn/version/latest`。

## 三、服务器锁死到 r.3d98.com.cn

- `libs/hbb_common/src/config.rs`：`update_latency` 加白名单，非 `r.3d98.com.cn` 的地址不会写入缓存。
- `src/common.rs`：`get_rendezvous_server` / `get_custom_rendezvous_server` / `get_api_server_` 三处去掉通过 exe 文件名注入第三方服务器的逻辑；api 默认兜底改为 `http://r.3d98.com.cn:21114`。
- `src/platform/windows.rs`：`bootstrap()` 不再从 exe 名写入 `EXE_RENDEZVOUS_SERVER`；`get_license()` 直接返回 None，不再从 exe 名/注册表读取 host/key/api。

## 四、CI 修复

- `.github/workflows/flutter-build.yml` 第 418 行：Windows x86 sciter 任务工具链从 `nightly-2023-10-13-i686-pc-windows-msvc`（i686 宿主，rustup 拒绝安装）改为 `nightly-2023-10-13-x86_64-pc-windows-msvc` + `targets: i686-pc-windows-msvc` 交叉编译。这是 `i686-pc-windows-msvc (windows-2022) exit code 1` 的直接原因。
- `.github/workflows/flutter-build.yml` 第 669 行：macOS arm64 任务从退役的 `macos-14` 改为 `macos-15`。
- `.github/workflows/playground.yml` 第 42/52/62/72 行：macOS Intel 任务从退役的 `macos-13` 改为 `macos-15-intel`。
- 修复跨平台编译错误：所有 Windows-only 的 `get_license_from_exe_name` 占位调用都加了 `#[cfg(windows)]`，linux-sciter 任务不再因找不到该函数而 exit code 101。

## 五、内联 hbb_common 子模块

- 删除 `.gitmodules`、`.github/dependabot.yml`。
- 删除 `libs/hbb_common/.git`，hbb_common 成为主仓库普通目录，不再需要单独推送或维护 commit 指针。

## 推送方法

```bash
cd rustdesk
git add -A
git commit -m "禁用自动更新；锁死服务器 r.3d98.com.cn；修复 CI 工具链与 runner 标签；内联 hbb_common"
git push
```
