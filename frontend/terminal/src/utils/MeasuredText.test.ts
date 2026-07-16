import {describe, it} from 'node:test';
import assert from 'node:assert/strict';
import {MeasuredText} from './MeasuredText.js';

describe('MeasuredText', () => {
	it('单行文本不换行', () => {
		const mt = new MeasuredText('hello', 80);
		assert.equal(mt.lineCount, 1);
		assert.deepEqual(mt.getWrappedText(), ['hello']);
	});

	it('长文本按宽度换行', () => {
		const mt = new MeasuredText('Hello world test', 5);
		const lines = mt.getWrappedText();
		// wrap-ansi 会将文本按5列宽换行
		assert.ok(lines.length > 1);
	});

	it('多行文本（含 \\n）', () => {
		const mt = new MeasuredText('line1\nline2', 80);
		assert.equal(mt.lineCount, 2);
		assert.deepEqual(mt.getWrappedText(), ['line1', 'line2']);
	});

	it('offset → position → offset 往返一致', () => {
		const mt = new MeasuredText('Hello world test', 80);
		const pos = mt.getPositionFromOffset(6);
		assert.equal(pos.line, 0);
		const offset = mt.getOffsetFromPosition(pos);
		assert.equal(offset, 6);
	});

	it('CJK 宽字符显示宽度正确', () => {
		const mt = new MeasuredText('你好世界', 80);
		// offset 1 = '好' 的位置，显示宽度 = 2（前一个字符'你'占2列）
		const pos = mt.getPositionFromOffset(1);
		assert.equal(pos.column, 2);
		// offset 2 = '世' 的位置，显示宽度 = 4（'你'+'好' 各2列）
		const pos2 = mt.getPositionFromOffset(2);
		assert.equal(pos2.column, 4);
	});

	it('wrapped 续行的 precededByNewline 标记', () => {
		const mt = new MeasuredText('aaaa\nbbbb', 3);
		const lines = mt.getWrappedLines();
		// 第一行 precededByNewline=true
		assert.equal(lines[0]!.precededByNewline, true);
	});

	it('空行处理', () => {
		const mt = new MeasuredText('a\n\nb', 80);
		assert.equal(mt.lineCount, 3);
		const lines = mt.getWrappedText();
		assert.equal(lines[1], '');
	});
});
