/**
 * 桌面快捷方式创建模块（仅 Windows）
 * ====================================
 *
 * 首次启动时自动在用户桌面创建指向当前应用的 .lnk 快捷方式。
 *
 * 设计要点：
 *   1. 仅 Windows + 打包后生效（开发环境 process.execPath 是 electron.exe，无意义）
 *   2. 用文件存在性检测而非 settings 标志位 —— 兼具恢复能力：
 *      用户误删快捷方式后下次启动自动重建，无需改 settings.ts 的只读约定
 *   3. 不传 icon 参数 —— .lnk 默认继承目标 exe 的内嵌图标（electron-builder 已将
 *      build/icon.ico 嵌入 exe），无需额外把 ico 复制到 resources
 *   4. 静默失败 —— 创建失败不阻塞应用启动（如桌面目录无写权限）
 *
 * @module shortcut
 */
import { app, shell } from 'electron';
import * as path from 'node:path';
import * as fs from 'node:fs';

/** 桌面快捷方式文件名（不含扩展名，shell.writeShortcutLink 会自动补 .lnk） */
const SHORTCUT_NAME = 'Illusion Agent';

/**
 * 若桌面不存在快捷方式则创建（仅 Windows 打包后生效）。
 *
 * 调用时机：主窗口显示后调用，避免阻塞首屏。操作本身极快（写一个 lnk 文件）。
 * 任何异常均静默吞掉，不影响应用正常启动。
 */
export function createDesktopShortcutIfAbsent(): void {
  // 非 Windows 或开发环境直接跳过
  if (process.platform !== 'win32') return;
  if (!app.isPackaged) return;

  try {
    const desktopDir = app.getPath('desktop');
    const lnkPath = path.join(desktopDir, `${SHORTCUT_NAME}.lnk`);

    // 已存在则跳过（用户可能已手动创建或上次已生成）
    if (fs.existsSync(lnkPath)) return;

    // 创建快捷方式：指向当前 exe，工作目录设为 exe 所在目录
    // 不传 icon → 继承 exe 内嵌图标；不传 args → 正常启动（不走单实例二次启动分支）
    shell.writeShortcutLink(lnkPath, 'create', {
      target: process.execPath,
      cwd: path.dirname(process.execPath),
      description: 'Illusion Agent 桌面版',
    });
  } catch {
    // 静默失败：桌面目录不可写、权限不足等情况下不干扰应用启动
  }
}
