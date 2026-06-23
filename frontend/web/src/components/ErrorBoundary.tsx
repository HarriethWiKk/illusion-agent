/**
 * @fileoverview React 错误边界组件
 *
 * 捕获子组件树中的渲染错误，防止整个应用白屏崩溃。
 * 显示友好的错误提示和重新加载按钮。
 *
 * @module ErrorBoundary
 */

import { Component, type ReactNode } from 'react';

/**
 * ErrorBoundary 组件属性接口
 */
interface ErrorBoundaryProps {
  /** 子组件 */
  children: ReactNode;
}

/**
 * ErrorBoundary 组件状态接口
 */
interface ErrorBoundaryState {
  /** 是否有错误 */
  hasError: boolean;
  /** 错误信息 */
  error: Error | null;
}

/**
 * 错误边界组件
 *
 * 捕获子组件树中的渲染错误，显示友好的错误提示，
 * 防止整个应用白屏崩溃。
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[ErrorBoundary] 捕获渲染错误:', error, errorInfo);
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen bg-surface-main">
          <div className="text-center max-w-md px-6">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-lg font-semibold text-content-primary mb-2">
              页面渲染出错
            </h2>
            <p className="text-sm text-content-secondary mb-4">
              {this.state.error?.message || '发生了未知错误'}
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 text-sm text-content-secondary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer border border-border-light"
              >
                重试
              </button>
              <button
                onClick={this.handleReload}
                className="px-4 py-2 text-sm text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors cursor-pointer"
              >
                重新加载页面
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
