// 强制 chalk 输出颜色码（测试环境无 TTY）
process.env.FORCE_COLOR = '1';

import {describe, it} from 'node:test';
import assert from 'node:assert/strict';
import chalk from 'chalk';
import {Cursor} from './Cursor.js';

describe('Cursor', () => {
	it('基础导航: left/right', () => {
		const c = Cursor.fromText('hello', 80, 2);
		assert.equal(c.left().offset, 1);
		assert.equal(c.right().offset, 3);
	});

	it('边界: offset 钳位', () => {
		const c = Cursor.fromText('ab', 80, 0);
		assert.equal(c.left().offset, 0);
		assert.equal(c.right().right().right().offset, 2);
	});

	it('up/down 在单行不移动', () => {
		const c = Cursor.fromText('hello', 80, 2);
		assert.equal(c.up().offset, 2);
		assert.equal(c.down().offset, 2);
	});

	it('up/down 跨 display line 移动', () => {
		// 宽度5，文本"Hello World" 会 wrap
		const c = Cursor.fromText('Hello World', 5, 7);
		const up = c.up();
		assert.notEqual(up.offset, 7);
	});

	it('up/down 跨 logical line 移动', () => {
		const c = Cursor.fromText('line1\nline2', 80, 8);
		const up = c.up();
		assert.ok(up.offset < 6);
	});

	it('insert 在光标处插入', () => {
		const c = Cursor.fromText('hello', 80, 2);
		const result = c.insert('XX');
		assert.equal(result.text, 'heXXllo');
		assert.equal(result.offset, 4);
	});

	it('backspace 删除前一个字符', () => {
		const c = Cursor.fromText('hello', 80, 2);
		const result = c.backspace();
		assert.equal(result.text, 'hllo');
		assert.equal(result.offset, 1);
	});

	it('deleteToLogicalLineStart 删除光标到行首的内容', () => {
		// 'line1\nline2' offset 8 = 'n' in 'line2'
		// logicalStart = 6 (after \n), 删除 offset 6~8 = 'li'
		const c = Cursor.fromText('line1\nline2', 80, 8);
		const result = c.deleteToLogicalLineStart();
		assert.equal(result.text, 'line1\nne2');
		assert.equal(result.offset, 6);
	});

	it('deleteToLogicalLineStart 在文本起始(offset=0)不删除', () => {
		const c = Cursor.fromText('line1\nline2', 80, 0);
		const result = c.deleteToLogicalLineStart();
		assert.equal(result.offset, 0);
	});

	it('deleteToLogicalLineStart 光标在 \\n 之后时删除该 \\n', () => {
		// 'line1\nline2\n' 光标在 offset 12（末尾，紧跟最后的 \n 之后）
		// 此时 text[11] = '\n'，应该删除该 \n
		const c = Cursor.fromText('line1\nline2\n', 80, 12);
		const result = c.deleteToLogicalLineStart();
		assert.equal(result.text, 'line1\nline2');
		assert.equal(result.offset, 11);
	});

	it('startOfLine / endOfLine', () => {
		const c = Cursor.fromText('Hello World', 5, 7);
		const start = c.startOfLine();
		const end = c.endOfLine();
		assert.notEqual(start.offset, c.offset);
		assert.notEqual(end.offset, c.offset);
	});

	it('getViewportStartLine 在短文本返回 0', () => {
		const c = Cursor.fromText('hello', 80, 2);
		assert.equal(c.getViewportStartLine(10), 0);
	});

	it('render 包含反色光标', () => {
	chalk.level = 1;
		const c = Cursor.fromText('hi', 80, 0);
		const rendered = c.render(' ', 0);
		// chalk.level=1 使用基本 ANSI 码 \x1b[7m
		assert.ok(rendered.includes('\x1b[7m'), `rendered=${JSON.stringify(rendered)}`);
	});

	it('render 光标在行尾显示反色空格', () => {
		chalk.level = 1;
		const c = Cursor.fromText('hi', 80, 2);
		const rendered = c.render(' ', 0);
		assert.ok(rendered.includes('\x1b[7m'), `rendered=${JSON.stringify(rendered)}`);
	});
});
