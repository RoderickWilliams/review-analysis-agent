/**
 * dsh-review-agent —— 把 ReviewAgent 的采集、分析、小红书洞察、Trust Report 挂成 DSH 工具。
 *
 * 进程执行走宿主 subprocess 服务（argv 数组，无 shell）；插件自身零运行时依赖。
 * Python 侧由 lib/bridge.py 承接，只回一行 JSON；未装 reviewagent 或未配 Key 时工具在
 * execute 阶段报带指引的错误，插件照常加载。
 *
 * @module dsh-review-agent
 */
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';

export const name = 'review-agent';
export const inject = ['subprocess', 'tools'];

const BRIDGE = fileURLToPath(new URL('./bridge.py', import.meta.url));
const DEFAULT_WORKDIR = 'E:\\DeepSeek\\review-agent';
const DEFAULT_PYTHON = 'E:\\DeepSeek\\review-agent\\.venv\\Scripts\\python.exe';
const COLLECT_BYTES = 8 * 1024 * 1024;

function resolveConfig(config) {
  const raw = config && typeof config === 'object' ? config : {};
  const num = (value, fallback) => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback);
  const str = (value, fallback) => (typeof value === 'string' && value.trim() !== '' ? value.trim() : fallback);
  return {
    pythonPath: str(raw.pythonPath, DEFAULT_PYTHON),
    workdir: resolve(str(raw.workdir, DEFAULT_WORKDIR)),
    timeoutMs: num(raw.timeoutMs, 900000),
    graceMs: num(raw.graceMs, 3000),
  };
}

function createRunner(spawn, cfg) {
  return {
    async run(argv, options) {
      const timeoutMs = options?.timeoutMs ?? cfg.timeoutMs;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new Error('review-agent tool timed out')), timeoutMs);
      const signal = options?.signal === undefined ? controller.signal : AbortSignal.any([options.signal, controller.signal]);
      try {
        const handle = spawn({
          argv,
          cwd: cfg.workdir,
          stdio: {
            stdin: 'ignore',
            stdout: { maxBytes: COLLECT_BYTES },
            stderr: { maxBytes: COLLECT_BYTES },
          },
          graceMs: cfg.graceMs,
          signal,
        });
        const outcome = await handle.done;
        if (signal.aborted) throw signal.reason;
        const out = handle.collected.stdout?.readFrom(0);
        const err = handle.collected.stderr?.readFrom(0);
        return {
          exitCode: outcome.exitCode,
          signal: outcome.signal,
          stdout: out?.text ?? '',
          stderr: err?.text ?? '',
        };
      } finally {
        clearTimeout(timer);
      }
    },
  };
}

function asRecord(value) {
  return typeof value === 'object' && value !== null ? value : {};
}

function optionalString(args, key) {
  return typeof args[key] === 'string' && args[key].trim() !== '' ? args[key].trim() : undefined;
}

function optionalNumber(args, key) {
  return typeof args[key] === 'number' && Number.isFinite(args[key]) ? args[key] : undefined;
}

function optionalBool(args, key) {
  return args[key] === true ? true : args[key] === false ? false : undefined;
}

function stringArray(args, key) {
  const value = args[key];
  if (!Array.isArray(value)) return undefined;
  const items = value.filter((item) => typeof item === 'string' && item.trim() !== '').map((item) => item.trim());
  return items.length > 0 ? items : undefined;
}

function buildTextRenderer(lines) {
  return (args, value) => [{ type: 'text', text: lines(args, asRecord(value)).join('\n') }];
}

function executionCwd(exec) {
  return exec?.agent?.session?.header?.cwd || process.cwd();
}

function tail(text, lines) {
  const parts = String(text ?? '').trim().split(/\r?\n/).filter((line) => line.trim() !== '');
  return parts.slice(-lines).join(' | ');
}

export function buildReviewAgentTools(cfg, runner) {
  const tmpRoot = join(cfg.workdir, '.dsh-tmp');

  async function runBridge(mode, payload, exec) {
    mkdirSync(tmpRoot, { recursive: true });
    const payloadPath = join(tmpRoot, 'review-agent-' + randomUUID() + '.json');
    writeFileSync(payloadPath, JSON.stringify(payload), 'utf8');
    try {
      const result = await runner.run([cfg.pythonPath, BRIDGE, mode, payloadPath], { signal: exec?.signal });
      const parse = () => {
        try {
          return JSON.parse(result.stdout);
        } catch {
          throw new Error(
            'review-agent 桥接返回的不是 JSON（退出码 ' + String(result.exitCode) + '）：' +
              (tail(result.stderr, 6) || tail(result.stdout, 6) || '无输出'),
          );
        }
      };
      const value = parse();
      if (value.ok === false) {
        const hint = value.hint ? ' ' + value.hint : '';
        throw new Error((value.error_type || 'ReviewAgentError') + '：' + (value.error || '调用失败') + hint);
      }
      return value;
    } finally {
      try {
        rmSync(payloadPath, { force: true });
      } catch {
        /* 临时文件清理失败不影响结果 */
      }
    }
  }

  const analyze = {
    name: 'review_analyze',
    description:
      '对商品评论跑完整 ReviewAgent 流水线：情绪识别、反讽与刷单检测、Trust Report、HTML 报告与历史记录。数据来源三选一：url（自动采集，默认关闭需先开采集）、csv（需 review_text 列）、demo（5 条演示评论，仍需配置大模型 Key）。返回终端摘要与报告路径。',
    parameters: {
      type: 'object',
      properties: {
        url: { type: 'string', description: '商品链接（自动采集，需 REVIEWAGENT_ENABLE_SCRAPING=1）。' },
        csv: { type: 'string', description: 'CSV 文件绝对路径，至少包含 review_text 列。' },
        demo: { type: 'boolean', description: '用内置 5 条演示评论跑通链路。' },
        max_reviews: { type: 'integer', description: '自动采集时的最大条数，默认 50。' },
        save_history: { type: 'boolean', description: '是否写入历史记录，默认 true。' },
      },
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '分析完成')]),
    },
    timeoutMs: cfg.timeoutMs,
    async execute(rawArgs, exec) {
      const args = asRecord(rawArgs);
      const payload = {
        url: optionalString(args, 'url'),
        csv: optionalString(args, 'csv'),
        demo: optionalBool(args, 'demo'),
        max_reviews: optionalNumber(args, 'max_reviews'),
        save_history: optionalBool(args, 'save_history'),
      };
      if (!payload.url && !payload.csv && !payload.demo) {
        throw new Error('请提供 url、csv 或 demo 之一。');
      }
      if (payload.csv) {
        const fsPath = resolve(executionCwd(exec), payload.csv);
        payload.csv = fsPath;
      }
      return runBridge('analyze', payload, exec);
    },
  };

  const xhs = {
    name: 'review_xhs',
    description:
      '小红书只读采集 + 洞察分析：笔记正文、评论、图片文字一起进模型，输出六章报告（总览、情绪与可信度、用户痛点、改进方向、宣传选题、内容生产包）。内容生产包给主图卖点与比例、详情页 8 段、15 秒分镜、英文清单、素材索引、风格卡与宣称边界，不生成图片。来源四选一：keyword（需登录）、user（博主主页链接，需带 xsec_token）、links（一篇或多篇笔记链接）、run_dir（复用已采集目录）。默认调用大模型；capture_only=true 只采集不分析。',
    parameters: {
      type: 'object',
      properties: {
        keyword: { type: 'string', description: '搜索关键词，需要先扫码登录。' },
        user: { type: 'string', description: '博主主页链接，需带 xsec_token，需要登录。' },
        links: { type: 'array', items: { type: 'string' }, description: '一篇或多篇笔记链接；单篇链接要带 xsec_token。' },
        run_dir: { type: 'string', description: '复用已有采集目录，跳过采集。' },
        limit: { type: 'integer', description: '最多读几篇，默认 20，上限 50。' },
        sort: { type: 'string', description: '综合 / 最新 / 最多点赞 / 最多评论 / 最多收藏。' },
        sweep: { type: 'boolean', description: '轮换四种排序再合并去重。' },
        note_type: { type: 'string', description: '只要 视频 或 图文。' },
        with_comments: { type: 'boolean', description: '是否读评论，默认 true。' },
        with_ocr: { type: 'boolean', description: '是否识别图片文字，默认 true。' },
        max_images: { type: 'integer', description: '每篇最多下载几张图。' },
        capture_only: { type: 'boolean', description: '只采集，不调用大模型分析。' },
        save_history: { type: 'boolean', description: '是否写入历史记录，默认 true。' },
        product_name: { type: 'string', description: '报告里的产品名，缺省取首篇笔记标题。' },
      },
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '小红书分析完成')]),
    },
    timeoutMs: cfg.timeoutMs,
    async execute(rawArgs, exec) {
      const args = asRecord(rawArgs);
      const payload = {
        keyword: optionalString(args, 'keyword'),
        user: optionalString(args, 'user'),
        links: stringArray(args, 'links'),
        run_dir: optionalString(args, 'run_dir'),
        limit: optionalNumber(args, 'limit'),
        sort: optionalString(args, 'sort'),
        sweep: optionalBool(args, 'sweep'),
        note_type: optionalString(args, 'note_type'),
        with_comments: optionalBool(args, 'with_comments'),
        with_ocr: optionalBool(args, 'with_ocr'),
        max_images: optionalNumber(args, 'max_images'),
        capture_only: optionalBool(args, 'capture_only'),
        save_history: optionalBool(args, 'save_history'),
        product_name: optionalString(args, 'product_name'),
      };
      if (!payload.keyword && !payload.user && !payload.links && !payload.run_dir) {
        throw new Error('请提供 keyword、user、links 或 run_dir 之一。');
      }
      return runBridge('xhs', payload, exec);
    },
  };

  const xhsStatus = {
    name: 'review_xhs_status',
    description: '检查小红书采集端是否可用、登录状态与 cookie 有效期；搜索或博主主页前先跑一次。',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '')]),
    },
    timeoutMs: 60000,
    async execute(_rawArgs, exec) {
      return runBridge('xhs_status', {}, exec);
    },
  };

  const susu = {
    name: 'review_susu',
    description:
      '把一次小红书采集转成 susu-insight 的观众研究报告：观众认知、讨论主题、内容选题与代表评论，生成离线 HTML。输入 run_dir（采集目录）或 analysis（已有 analysis.json，只重新渲染）。不传 use_llm 时默认调用大模型细分主题；未配置 Key 就只做按笔记的确定性归类。',
    parameters: {
      type: 'object',
      properties: {
        run_dir: { type: 'string', description: '小红书采集目录（含 notes.json）。' },
        analysis: { type: 'string', description: '已有 analysis.json 路径，只渲染不重新分析。' },
        account: { type: 'string', description: '报告里的账号名，缺省取首篇笔记作者。' },
        out_dir: { type: 'string', description: '报告输出目录，缺省 output/susu。' },
        use_llm: { type: 'boolean', description: '是否调用大模型细分主题，默认 true。' },
      },
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '')]),
    },
    timeoutMs: cfg.timeoutMs,
    async execute(rawArgs, exec) {
      const args = asRecord(rawArgs);
      const payload = {
        run_dir: optionalString(args, 'run_dir'),
        analysis: optionalString(args, 'analysis'),
        account: optionalString(args, 'account'),
        out_dir: optionalString(args, 'out_dir'),
        use_llm: optionalBool(args, 'use_llm'),
      };
      if (!payload.run_dir && !payload.analysis) {
        throw new Error('review_susu 需要 run_dir 或 analysis 之一。');
      }
      const cwd = executionCwd(exec);
      if (payload.run_dir) payload.run_dir = resolve(cwd, payload.run_dir);
      if (payload.analysis) payload.analysis = resolve(cwd, payload.analysis);
      if (payload.out_dir) payload.out_dir = resolve(cwd, payload.out_dir);
      return runBridge('susu', payload, exec);
    },
  };

  const trust = {
    name: 'review_trust_report',
    description:
      '只对一份 CSV 评论算 Trust Report，不调用大模型：时间突发、近重复、评分与文本矛盾、长度均匀度等统计信号，给出综合信任分、风险等级与 95% 区间。CSV 至少包含 review_text 列。',
    parameters: {
      type: 'object',
      properties: {
        csv: { type: 'string', description: 'CSV 文件路径（必填），至少包含 review_text 列。' },
      },
      required: ['csv'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '')]),
    },
    timeoutMs: 180000,
    async execute(rawArgs, exec) {
      const args = asRecord(rawArgs);
      const csv = optionalString(args, 'csv');
      if (!csv) throw new Error('review_trust_report 需要 csv 参数。');
      return runBridge('trust', { csv: resolve(executionCwd(exec), csv) }, exec);
    },
  };

  const history = {
    name: 'review_history',
    description: '查看 ReviewAgent 历史分析记录，或清空它们（清空要同时传 yes=true）。',
    parameters: {
      type: 'object',
      properties: {
        limit: { type: 'integer', description: '最多返回几条，默认 20。' },
        clear: { type: 'boolean', description: '清空全部历史记录。' },
        yes: { type: 'boolean', description: '清空确认，必须与 clear 一起用。' },
      },
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '')]),
    },
    timeoutMs: 60000,
    async execute(rawArgs, exec) {
      const args = asRecord(rawArgs);
      return runBridge(
        'history',
        { limit: optionalNumber(args, 'limit'), clear: optionalBool(args, 'clear'), yes: optionalBool(args, 'yes') },
        exec,
      );
    },
  };

  const doctor = {
    name: 'review_doctor',
    description: 'ReviewAgent 环境自检：依赖、模型配置、数据目录、采集后端、小红书登录状态与数据库记录数。工具报错时先跑它。',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: buildTextRenderer((_args, value) => [String(value.summary ?? '')]),
    },
    timeoutMs: 120000,
    async execute(_rawArgs, exec) {
      return runBridge('doctor', {}, exec);
    },
  };

  return [analyze, xhs, susu, xhsStatus, trust, history, doctor];
}

export function apply(ctx, config) {
  const cfg = resolveConfig(config);
  const runner = createRunner((spec) => ctx.subprocess.spawn(spec), cfg);
  const disposers = [];
  for (const definition of buildReviewAgentTools(cfg, runner)) {
    disposers.push(ctx.tools.register(definition));
  }
  if (typeof ctx.on === 'function') {
    ctx.on('dispose', () => {
      for (const dispose of disposers) dispose();
    });
  }
}
