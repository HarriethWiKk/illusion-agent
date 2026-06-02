/**
 * @fileoverview Web 前端应用入口模块
 *
 * 本模块是 IllusionCode Web 前端的入口点，负责：
 * 1. 创建 React 根节点
 * 2. 渲染根组件 App
 * 3. 启用 React 严格模式以进行开发时检查
 *
 * @module main
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

/**
 * 创建 React 根节点并渲染应用
 *
 * 使用 React 18 的 createRoot API 创建根节点，
 * 并在严格模式下渲染 App 组件。
 */
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
