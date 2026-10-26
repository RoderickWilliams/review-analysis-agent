import { buildReviewAgentTools, name, inject } from 'file:///E:/DeepSeek/review-agent/plugins/dsh-review-agent/lib/index.js';
import { spawnSync } from 'node:child_process';

const cfg = {
  pythonPath: 'E:/DeepSeek/review-agent/.venv/Scripts/python.exe',
  workdir: 'E:/DeepSeek/review-agent',
  timeoutMs: 120000,
};
const runner = {
  async run(argv) {
    const r = spawnSync(argv[0], argv.slice(1), { encoding: 'utf8', timeout: 120000, windowsHide: true });
    return { exitCode: r.status, stdout: r.stdout || '', stderr: r.stderr || '' };
  },
};
const tools = buildReviewAgentTools(cfg, runner);
const byName = Object.fromEntries(tools.map((t) => [t.name, t]));
const checks = [];
checks.push(['name', name === 'review-agent']);
checks.push(['inject', Array.isArray(inject) && inject.includes('tools')]);
checks.push(['seven tools', tools.length === 7]);
checks.push(['schemas', tools.every((t) => t.parameters?.type === 'object' && typeof t.execute === 'function')]);
const doctor = await byName.review_doctor.execute({}, {});
checks.push(['doctor runs', doctor.ok === true && typeof doctor.summary === 'string' && doctor.summary.length > 20]);
const status = await byName.review_xhs_status.execute({}, {});
checks.push(['xhs status runs', typeof status.available === 'boolean']);
let badArg = false;
try { await byName.review_analyze.execute({}, {}); } catch (e) { badArg = /url、csv 或 demo/.test(String(e)); }
checks.push(['argument guard', badArg]);
let badSusu = false;
try { await byName.review_susu.execute({}, {}); } catch (e) { badSusu = /run_dir 或 analysis/.test(String(e)); }
checks.push(['susu argument guard', badSusu]);
const susu = await byName.review_susu.execute(
  { run_dir: 'E:/DeepSeek/tmp/xhs-run-test', out_dir: 'E:/DeepSeek/tmp/susu-verify', use_llm: false },
  {},
);
checks.push(['susu renders', susu.ok === true && /susu-insight 报告已生成/.test(String(susu.summary))]);
const failed = checks.filter(([, ok]) => !ok);
console.log(JSON.stringify({ passed: checks.length - failed.length, total: checks.length, failed: failed.map(([n]) => n) }, null, 2));
process.exit(failed.length === 0 ? 0 : 1);
