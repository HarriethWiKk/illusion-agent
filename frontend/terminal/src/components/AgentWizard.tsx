/**
 * @fileoverview Agent 分步创建向导组件
 *
 * 在 /agent create 时触发，串联 SelectModal / MultilineTextInput / 单行输入，
 * 引导用户逐步填写 agent 配置并提交到后端。
 *
 * 步骤：
 * 1. scope（user / project）— SelectModal 单选
 * 2. method（generate / manual）— SelectModal 单选
 * 3a. describe（generate 路径）→ onGenerate → spinner → generated 填充
 * 3b. name + system_prompt（manual 路径）
 * 4. 确认生成结果（generate 路径）
 * 5. description（when_to_use）
 * 6. 默认 model — SelectModal 单选（含 inherit）
 * 7. tools — 可切换多选 + Done
 * 8. effort — SelectModal 单选（含跳过）
 * 9. permission_mode — SelectModal 单选（含跳过）
 * 10. max_turns — 单行数字输入（可跳过）
 * 11. confirm → onSubmit
 *
 * 自管 useInput：SelectModal 步骤处理上下导航/Enter/Esc；
 * 文本步骤仅处理 Esc（取消），其余按键交由 TextInput/MultilineTextInput 内部处理。
 *
 * @module AgentWizard
 */

import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Box, Text, useInput} from 'ink';
import TextInput from 'ink-text-input';

import MultilineTextInput from './MultilineTextInput.js';
import {SelectModal, type SelectOption} from './SelectModal.js';
import {Spinner} from './Spinner.js';
import {useTerminalSize} from '../hooks/useTerminalSize.js';
import {t, UiLanguage} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';

/** 工具项类型 */
type ToolOption = {name: string; description: string};
/** 模型项类型 */
type ModelOption = {name: string; label: string};
/** LLM 生成的 agent 草稿类型 */
type GeneratedAgent = {identifier: string; when_to_use: string; system_prompt: string};
/** 提交结果类型 */
type WizardResult = {success: boolean; path?: string; errors?: string[]; error?: string};

/** 向导步骤标识 */
type Step =
	| 'scope'
	| 'method'
	| 'describe'
	| 'generating'
	| 'generateFailed'
	| 'generateConfirm'
	| 'name'
	| 'systemPrompt'
	| 'description'
	| 'model'
	| 'tools'
	| 'effort'
	| 'permission'
	| 'maxTurns'
	| 'confirm'
	| 'submitting'
	| 'done'
	| 'failed';

/** 累积的 agent 字段 */
type Fields = {
	scope: 'user' | 'project';
	method: 'generate' | 'manual';
	identifier: string;
	when_to_use: string;
	system_prompt: string;
	model: string;
	tools: string[];
	effort?: string;
	permission_mode?: string;
	max_turns?: number;
};

/** 组件属性 */
interface AgentWizardProps {
	/** 当前 UI 语言 */
	language: UiLanguage;
	/** 可选工具列表（来自 agent_wizard_init_response） */
	tools: ToolOption[] | null;
	/** 可选模型列表（来自 agent_wizard_init_response） */
	models: ModelOption[] | null;
	/** LLM 生成的草稿（来自 agent_generate_response） */
	generated: GeneratedAgent | null;
	/** 是否正在生成 */
	generateLoading: boolean;
	/** 生成错误文本 */
	generateError: string | null;
	/** 提交结果（来自 agent_wizard_result） */
	result: WizardResult | null;
	/** 请求初始化（拉取工具/模型列表） */
	onInit: () => void;
	/** 请求 LLM 生成草稿 */
	onGenerate: (prompt: string, model: string) => void;
	/** 提交表单 */
	onSubmit: (fields: Record<string, unknown>, scope: 'user' | 'project') => void;
	/** 取消/关闭向导 */
	onCancel: () => void;
}

/** effort 选项值列表 */
const EFFORT_VALUES = ['low', 'medium', 'high', 'xhigh', 'max'];
/** permission_mode 选项值列表 */
const PERMISSION_VALUES = ['default', 'plan', 'full_auto'];

/**
 * Agent 分步创建向导组件
 *
 * @param props - 组件属性
 * @returns 返回向导的 JSX 元素
 */
export function AgentWizard(props: AgentWizardProps): React.JSX.Element {
	const {
		language, tools, models, generated, generateLoading, generateError, result,
		onInit, onGenerate, onSubmit, onCancel,
	} = props;
	const theme = useTheme();
	const {columns} = useTerminalSize();

	const [step, setStep] = useState<Step>('scope');
	const [fields, setFields] = useState<Fields>({
		scope: 'project',
		method: 'generate',
		identifier: '',
		when_to_use: '',
		system_prompt: '',
		model: 'inherit',
		tools: [],
	});
	const [selectedIndex, setSelectedIndex] = useState(0);
	const [singleValue, setSingleValue] = useState('');
	const [singleError, setSingleError] = useState<string | null>(null);
	const [multilineValue, setMultilineValue] = useState('');
	const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set());

	// 防止已处理过的 generated/error/result 在重新进入步骤时被重复消费
	const lastHandledGeneratedRef = useRef<GeneratedAgent | null>(null);
	const lastHandledErrorRef = useRef<string | null>(null);
	const lastHandledResultRef = useRef<WizardResult | null>(null);

	// 挂载时请求初始化工具/模型列表
	useEffect(() => {
		onInit();
	}, [onInit]);

	// 收到生成草稿：从 generating/generateFailed 推进到 generateConfirm
	useEffect(() => {
		if (!generated) return;
		if (generated === lastHandledGeneratedRef.current) return;
		lastHandledGeneratedRef.current = generated;
		if (step !== 'generating' && step !== 'generateFailed') return;
		setFields((f) => ({
			...f,
			identifier: generated.identifier,
			when_to_use: generated.when_to_use,
			system_prompt: generated.system_prompt,
		}));
		setStep('generateConfirm');
	}, [generated, step]);

	// 收到生成错误：从 generating 推进到 generateFailed
	useEffect(() => {
		if (!generateError) return;
		if (generateError === lastHandledErrorRef.current) return;
		lastHandledErrorRef.current = generateError;
		if (step !== 'generating') return;
		setStep('generateFailed');
	}, [generateError, step]);

	// 收到提交结果
	useEffect(() => {
		if (!result) return;
		if (result === lastHandledResultRef.current) return;
		lastHandledResultRef.current = result;
		if (step !== 'submitting') return;
		if (result.success) {
			setStep('done');
		} else {
			setStep('failed');
		}
	}, [result, step]);

	// ====== SelectModal 选项构建 ======

	const scopeOptions = useMemo<SelectOption[]>(() => [
		{value: 'project', label: t(language, 'agentWizardScopeProject')},
		{value: 'user', label: t(language, 'agentWizardScopeUser')},
	], [language]);

	const methodOptions = useMemo<SelectOption[]>(() => [
		{value: 'generate', label: t(language, 'agentWizardMethodGenerate')},
		{value: 'manual', label: t(language, 'agentWizardMethodManual')},
	], [language]);

	const modelOptions = useMemo<SelectOption[]>(() => {
		const opts: SelectOption[] = [
			{value: 'inherit', label: 'inherit', description: t(language, 'agentWizardInherit')},
		];
		for (const m of models ?? []) {
			opts.push({value: m.name, label: m.label, description: m.name});
		}
		return opts;
	}, [language, models]);

	const toolsOptions = useMemo<SelectOption[]>(() => {
		const opts: SelectOption[] = (tools ?? []).map((tool) => ({
			value: tool.name,
			label: `${selectedTools.has(tool.name) ? theme.icons.check + ' ' : '  '}${tool.name}`,
			description: tool.description,
		}));
		opts.push({value: '__done__', label: t(language, 'agentWizardDone'), description: ''});
		return opts;
	}, [tools, selectedTools, theme.icons.check, language]);

	const effortOptions = useMemo<SelectOption[]>(() => {
		const opts = EFFORT_VALUES.map((v) => ({value: v, label: v}));
		opts.push({value: '__skip__', label: t(language, 'agentWizardSkip')});
		return opts;
	}, [language]);

	const permissionOptions = useMemo<SelectOption[]>(() => {
		const opts = PERMISSION_VALUES.map((v) => ({value: v, label: v}));
		opts.push({value: '__skip__', label: t(language, 'agentWizardSkip')});
		return opts;
	}, [language]);

	/** 当前 select 步骤对应的选项列表 */
	const currentSelectOptions = (): SelectOption[] => {
		switch (step) {
			case 'scope': return scopeOptions;
			case 'method': return methodOptions;
			case 'model': return modelOptions;
			case 'tools': return toolsOptions;
			case 'effort': return effortOptions;
			case 'permission': return permissionOptions;
			default: return [];
		}
	};

	// ====== 提交辅助 ======

	/** 提交描述（generate 路径），触发后端 LLM 生成 */
	const submitDescribe = (v: string): void => {
		const s = v.trim();
		if (!s) return;
		onGenerate(s, 'inherit');
		setStep('generating');
	};

	/** 提交 name（manual 路径） */
	const submitName = (v: string): void => {
		const s = v.trim();
		if (!s) return;
		setFields((f) => ({...f, identifier: s}));
		setMultilineValue('');
		setStep('systemPrompt');
	};

	/** 提交 system_prompt（manual 路径） */
	const submitSystemPrompt = (v: string): void => {
		const s = v.trim();
		if (!s) return;
		setFields((f) => ({...f, system_prompt: s}));
		setSingleValue('');
		setStep('description');
	};

	/** 提交 description（when_to_use） */
	const submitDescription = (v: string): void => {
		const s = v.trim();
		if (!s) return;
		setFields((f) => ({...f, when_to_use: s}));
		setSelectedIndex(0);
		setStep('model');
	};

	/** 提交 max_turns（留空跳过） */
	const submitMaxTurns = (v: string): void => {
		const s = v.trim();
		if (s === '') {
			setStep('confirm');
			return;
		}
		if (!/^\d+$/.test(s) || parseInt(s, 10) <= 0) {
			setSingleError(t(language, 'agentWizardMaxTurnsInvalid'));
			return;
		}
		setFields((f) => ({...f, max_turns: parseInt(s, 10)}));
		setStep('confirm');
	};

	/** 提交完整表单 */
	const submitForm = (): void => {
		// 后端 validate_agent_definition / write_agent_definition 期望字段名为
		// name / description（与 AgentDefinition frontmatter 一致）；
		// 向导内部沿用 identifier / when_to_use 是为了与 agent_generate_response
		// 返回字段保持一致，便于直接填充。提交时映射到后端期望的字段名。
		const payload: Record<string, unknown> = {
			name: fields.identifier,
			description: fields.when_to_use,
			system_prompt: fields.system_prompt,
			model: fields.model || 'inherit',
			tools: fields.tools,
		};
		if (fields.effort) payload.effort = fields.effort;
		if (fields.permission_mode) payload.permission_mode = fields.permission_mode;
		if (fields.max_turns != null) payload.max_turns = fields.max_turns;
		onSubmit(payload, fields.scope);
		setStep('submitting');
	};

	/** SelectModal 选项被选中时的处理 */
	const handleSelect = (value: string): void => {
		switch (step) {
			case 'scope':
				setFields((f) => ({...f, scope: value as 'user' | 'project'}));
				setSelectedIndex(0);
				setStep('method');
				break;
			case 'method': {
				const m = value as 'generate' | 'manual';
				setFields((f) => ({...f, method: m}));
				setSelectedIndex(0);
				if (m === 'generate') {
					setMultilineValue('');
					setStep('describe');
				} else {
					setSingleValue('');
					setSingleError(null);
					setStep('name');
				}
				break;
			}
			case 'model':
				setFields((f) => ({...f, model: value}));
				setSelectedIndex(0);
				setStep('tools');
				break;
			case 'tools':
				if (value === '__done__') {
					setFields((f) => ({...f, tools: Array.from(selectedTools)}));
					setSelectedIndex(0);
					setStep('effort');
				} else {
					setSelectedTools((prev) => {
						const next = new Set(prev);
						if (next.has(value)) next.delete(value);
						else next.add(value);
						return next;
					});
				}
				break;
			case 'effort':
				if (value !== '__skip__') {
					setFields((f) => ({...f, effort: value}));
				}
				setSelectedIndex(0);
				setStep('permission');
				break;
			case 'permission':
				if (value !== '__skip__') {
					setFields((f) => ({...f, permission_mode: value}));
				}
				setSelectedIndex(0);
				setSingleValue('');
				setSingleError(null);
				setStep('maxTurns');
				break;
			default:
				break;
		}
	};

	// ====== 键盘输入处理 ======
	useInput((chunk, key) => {
		// done 状态：任意键关闭
		if (step === 'done') {
			onCancel();
			return;
		}
		// generating / submitting：等待后端响应，忽略输入（生成同步进行，不可中途取消 — 简化）
		if (step === 'generating' || step === 'submitting') {
			return;
		}
		// 文本输入步骤：仅处理 Esc（取消），其余交给 TextInput/MultilineTextInput
		if (step === 'describe' || step === 'name' || step === 'systemPrompt'
			|| step === 'description' || step === 'maxTurns') {
			if (key.escape) {
				onCancel();
			}
			return;
		}
		// 生成失败：Enter/R 重试，Esc/B 返回方法选择
		if (step === 'generateFailed') {
			if (key.return || chunk === 'r' || chunk === 'R') {
				setMultilineValue('');
				setStep('describe');
			} else if (key.escape || chunk === 'b' || chunk === 'B') {
				setSelectedIndex(0);
				setStep('method');
			}
			return;
		}
		// 生成结果确认：Enter 接受，Esc 返回 describe 编辑
		if (step === 'generateConfirm') {
			if (key.return) {
				setSingleValue(fields.when_to_use);
				setSingleError(null);
				setStep('description');
			} else if (key.escape) {
				setStep('describe');
			}
			return;
		}
		// 失败结果：Enter/Esc 返回 confirm 以便重新提交
		if (step === 'failed') {
			if (key.return || key.escape) {
				setStep('confirm');
			}
			return;
		}
		// confirm：Enter 提交，Esc 返回 maxTurns
		if (step === 'confirm') {
			if (key.return) {
				submitForm();
			} else if (key.escape) {
				setSingleValue(fields.max_turns != null ? String(fields.max_turns) : '');
				setSingleError(null);
				setStep('maxTurns');
			}
			return;
		}
		// ---- SelectModal 步骤：上下导航 + Enter 选择 + Esc 取消 ----
		const options = currentSelectOptions();
		if (options.length === 0) return;
		if (key.upArrow) {
			setSelectedIndex((i) => Math.max(0, i - 1));
			return;
		}
		if (key.downArrow) {
			setSelectedIndex((i) => Math.min(options.length - 1, i + 1));
			return;
		}
		if (key.escape) {
			onCancel();
			return;
		}
		if (key.return) {
			const opt = options[selectedIndex];
			if (opt) handleSelect(opt.value);
			return;
		}
	});

	// ====== 渲染 ======

	/** 渲染带标签的单行输入 */
	const renderSingleInput = (prompt: string, placeholder: string, submit: (v: string) => void): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.illusion}>{theme.icons.pointer} </Text>
				<Text color={theme.colors.illusionShimmer} bold>{prompt} </Text>
				<TextInput
					value={singleValue}
					onChange={(v) => { setSingleValue(v); setSingleError(null); }}
					placeholder={placeholder}
					focus={true}
					showCursor={true}
					onSubmit={submit}
				/>
			</Box>
			{singleError ? (
				<Box marginTop={1}>
					<Text color={theme.colors.error}>{singleError}</Text>
				</Box>
			) : null}
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'questionHintCancel')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'questionHintSubmit')}</Text>
				</Text>
			</Box>
		</Box>
	);

	/** 渲染带标签的多行输入 */
	const renderMultilineInput = (prompt: string, placeholder: string, submit: (v: string) => void): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.illusion}>{theme.icons.pointer} </Text>
				<Text bold>{prompt}</Text>
			</Box>
			<Box>
			<Text>  </Text>
			<MultilineTextInput
					value={multilineValue}
					onChange={setMultilineValue}
					onSubmit={submit}
					columns={Math.max(20, columns - 2)}
					placeholder={placeholder}
				/>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'questionHintCancel')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'questionHintSubmit')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>ctrl+j {t(language, 'newline')}</Text>
				</Text>
			</Box>
		</Box>
	);

	/** 渲染 SelectModal 步骤 */
	const renderSelectStep = (title: string, options: SelectOption[]): React.JSX.Element => (
		<SelectModal title={title} options={options} selectedIndex={selectedIndex} />
	);

	/** 渲染生成中 */
	const renderGenerating = (): React.JSX.Element => (
		<Box marginTop={1}>
			<Spinner language={language} label={t(language, 'agentWizardGenerating')} />
		</Box>
	);

	/** 渲染生成失败 */
	const renderGenerateFailed = (): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.error}>{theme.icons.error} </Text>
				<Text color={theme.colors.error} bold>{t(language, 'agentWizardGenerateFailed')}</Text>
			</Box>
			{generateError ? (
				<Box>
					<Text color={theme.colors.error}>{generateError}</Text>
				</Box>
			) : null}
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'agentWizardRetry')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'agentWizardBack')}</Text>
				</Text>
			</Box>
		</Box>
	);

	/** 渲染生成结果确认 */
	const renderGenerateConfirm = (): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.illusion}>{theme.icons.pointer} </Text>
				<Text bold>{t(language, 'agentWizardGenerateConfirm')}</Text>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>{t(language, 'agentWizardNameLabel')}: </Text>
				<Text color={theme.colors.suggestion}>{fields.identifier}</Text>
			</Box>
			<Box>
				<Text dimColor>{t(language, 'agentWizardDescriptionLabel')}: </Text>
				<Text color={theme.colors.suggestion}>{fields.when_to_use}</Text>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>{t(language, 'agentWizardReviewHint')}</Text>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'questionHintSubmit')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'questionHintCancel')}</Text>
				</Text>
			</Box>
		</Box>
	);

	/** 渲染提交中 */
	const renderSubmitting = (): React.JSX.Element => (
		<Box marginTop={1}>
			<Spinner language={language} label={t(language, 'agentWizardSubmitting')} />
		</Box>
	);

	/** 渲染确认摘要 */
	const renderConfirm = (): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.illusion}>{theme.icons.pointer} </Text>
				<Text bold>{t(language, 'agentWizardConfirmTitle')}</Text>
			</Box>
			<Text dimColor>{t(language, 'agentWizardScopeLabel')}: {fields.scope}</Text>
			<Text dimColor>{t(language, 'agentWizardNameLabel')}: {fields.identifier}</Text>
			<Text dimColor>{t(language, 'agentWizardDescriptionLabel')}: {fields.when_to_use}</Text>
			<Text dimColor>{t(language, 'agentWizardModelLabel')}: {fields.model}</Text>
			<Text dimColor>{t(language, 'agentWizardToolsLabel')}: {fields.tools.length ? fields.tools.join(', ') : t(language, 'agentWizardSkip')}</Text>
			{fields.effort ? <Text dimColor>{t(language, 'agentWizardEffortLabel')}: {fields.effort}</Text> : null}
			{fields.permission_mode ? <Text dimColor>{t(language, 'agentWizardPermissionLabel')}: {fields.permission_mode}</Text> : null}
			{fields.max_turns != null ? <Text dimColor>{t(language, 'agentWizardMaxTurnsLabel')}: {fields.max_turns}</Text> : null}
			<Box marginTop={1}>
				<Text dimColor>{t(language, 'agentWizardReviewHint')}</Text>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'questionHintSubmit')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'questionHintCancel')}</Text>
				</Text>
			</Box>
		</Box>
	);

	/** 渲染成功 */
	const renderDone = (): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.success}>{theme.icons.success} </Text>
				<Text color={theme.colors.success} bold>{t(language, 'agentWizardSuccess')}</Text>
			</Box>
			{result?.path ? (
				<Box>
					<Text dimColor>{result.path}</Text>
				</Box>
			) : null}
			<Box marginTop={1}>
				<Text dimColor>{t(language, 'agentWizardPressAnyKey')}</Text>
			</Box>
		</Box>
	);

	/** 渲染失败 */
	const renderFailed = (): React.JSX.Element => (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.error}>{theme.icons.error} </Text>
				<Text color={theme.colors.error} bold>{t(language, 'agentWizardFailed')}</Text>
			</Box>
			{result?.error ? (
				<Box>
					<Text color={theme.colors.error}>{result.error}</Text>
				</Box>
			) : null}
			{result?.errors?.length ? (
				<Box flexDirection="column">
					{result.errors.map((e, i) => (
						<Text key={i} color={theme.colors.error}>- {e}</Text>
					))}
				</Box>
			) : null}
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>{t(language, 'questionHintSubmit')}</Text>
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>{t(language, 'questionHintCancel')}</Text>
				</Text>
			</Box>
		</Box>
	);

	switch (step) {
		case 'scope':
			return renderSelectStep(t(language, 'agentWizardScopeTitle'), scopeOptions);
		case 'method':
			return renderSelectStep(t(language, 'agentWizardMethodTitle'), methodOptions);
		case 'describe':
			return renderMultilineInput(
				t(language, 'agentWizardDescribePrompt'),
				t(language, 'agentWizardDescribePlaceholder'),
				submitDescribe,
			);
		case 'generating':
			return renderGenerating();
		case 'generateFailed':
			return renderGenerateFailed();
		case 'generateConfirm':
			return renderGenerateConfirm();
		case 'name':
			return renderSingleInput(
				t(language, 'agentWizardNamePrompt'),
				t(language, 'agentWizardNamePlaceholder'),
				submitName,
			);
		case 'systemPrompt':
			return renderMultilineInput(
				t(language, 'agentWizardSystemPromptPrompt'),
				'',
				submitSystemPrompt,
			);
		case 'description':
			return renderSingleInput(
				t(language, 'agentWizardDescriptionPrompt'),
				t(language, 'agentWizardDescriptionPlaceholder'),
				submitDescription,
			);
		case 'model':
			return renderSelectStep(t(language, 'agentWizardModelTitle'), modelOptions);
		case 'tools':
			return renderSelectStep(t(language, 'agentWizardToolsTitle'), toolsOptions);
		case 'effort':
			return renderSelectStep(t(language, 'agentWizardEffortTitle'), effortOptions);
		case 'permission':
			return renderSelectStep(t(language, 'agentWizardPermissionTitle'), permissionOptions);
		case 'maxTurns':
			return renderSingleInput(
				t(language, 'agentWizardMaxTurnsPrompt'),
				t(language, 'agentWizardMaxTurnsPlaceholder'),
				submitMaxTurns,
			);
		case 'confirm':
			return renderConfirm();
		case 'submitting':
			return renderSubmitting();
		case 'done':
			return renderDone();
		case 'failed':
			return renderFailed();
		default:
			return <Box><Text>?</Text></Box>;
	}
}
