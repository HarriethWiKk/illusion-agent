/**
 * 预加载脚本
 * ============
 *
 * 在渲染进程加载前执行，通过 contextBridge 暴露安全 API。
 *
 * 暴露内容（window.illusionDesktop）：
 *   - version：Electron 版本，渲染进程可据此判断是否在桌面壳内
 *   - platform：运行平台，用于顶部栏交通灯/自定义按钮的差异处理
 *   - minimize / toggleMaximize / close：窗口控制，通过 IPC 转发主进程
 *
 * 浏览器直接访问 Web 端时本脚本不执行，window.illusionDesktop 为 undefined。
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('illusionDesktop', {
  /** Electron 版本 */
  version: process.versions.electron,
  /** 运行平台：win32 / darwin / linux */
  platform: process.platform,
  /** 最小化窗口 */
  minimize: () => ipcRenderer.send('window-minimize'),
  /** 切换最大化/还原 */
  toggleMaximize: () => ipcRenderer.send('window-toggle-maximize'),
  /** 最大化窗口（仅最大化，不切换；用于连接成功后自动最大化） */
  maximize: () => ipcRenderer.send('window-maximize'),
  /** 关闭窗口（主进程 close 事件 → 最小化到托盘） */
  close: () => ipcRenderer.send('window-close'),
});
