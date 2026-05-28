import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface MessageBubbleProps {
  item: TranscriptItem;
}

export default function MessageBubble({ item }: MessageBubbleProps) {
  if (item.role === 'user') {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="max-w-[70%] bg-blue-50 text-gray-900 rounded-lg px-4 py-2 text-sm">
          {item.text}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    return (
      <div className="px-4 py-2">
        <div className="max-w-[85%] text-gray-900 text-sm prose prose-sm prose-gray max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {item.text}
          </ReactMarkdown>
          {item.reasoning && (
            <details className="mt-2 text-xs text-gray-500">
              <summary className="cursor-pointer">Thinking...</summary>
              <div className="mt-1 p-2 bg-gray-50 rounded text-gray-600 whitespace-pre-wrap">
                {item.reasoning}
              </div>
            </details>
          )}
        </div>
      </div>
    );
  }

  if (item.role === 'tool' || item.role === 'tool_result') {
    const isError = item.is_error;
    return (
      <div className="px-4 py-1">
        <details className={`text-xs rounded-md ${isError ? 'bg-red-50' : 'bg-gray-50'}`}>
          <summary className="cursor-pointer px-3 py-1.5 font-mono text-gray-600">
            {item.tool_name || item.role}
          </summary>
          <div className="px-3 py-2 border-t border-gray-200 whitespace-pre-wrap font-mono text-gray-700 max-h-60 overflow-y-auto">
            {item.text}
          </div>
        </details>
      </div>
    );
  }

  return (
    <div className="px-4 py-1 text-xs text-gray-500 italic">
      {item.text}
    </div>
  );
}

export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  return (
    <div className="px-4 py-1">
      <div className="flex items-center gap-2 text-xs text-gray-500 font-mono">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
        {call.tool_name}
        {call.tool_input && Object.keys(call.tool_input).length > 0 && (
          <span className="text-gray-400 truncate max-w-[400px]">
            {JSON.stringify(call.tool_input)}
          </span>
        )}
      </div>
    </div>
  );
}

export function StreamingBuffer({ text }: { text: string }) {
  return (
    <div className="px-4 py-2">
      <div className="max-w-[85%] text-gray-900 text-sm prose prose-sm prose-gray max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {text || '▍'}
        </ReactMarkdown>
      </div>
    </div>
  );
}
